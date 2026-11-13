"""2-Pass 휴리스틱 주석 제거 엔진.

정규식 기반 주석 제거의 한계 — 문자열 리터럴 내부의 ``//``나 ``http://``를
주석으로 오탐하는 문제 — 를 극복하기 위해, 확장자 기반 사전 필터와
문자 단위 상태 머신 파서를 결합한 2-pass 전략을 사용한다.

Pass 1 (Fast-path):
    ``CODE`` 상태에서 주석 마커를 포함하지 않는 라인은 즉시 통과.
    대부분의 코드 라인이 이 경로를 타므로 성능 오버헤드가 최소화된다.

Pass 2 (Slow-path):
    주석 마커가 있는 라인(또는 비-CODE 상태를 상속받은 라인)만
    문자 단위 상태 머신을 통과시켜, 문자열 내부의 주석 마커를 정확히 구별.

의존:
    - ``languages/``: 확장자별 ``CommentSpec`` 제공 (``_RegistryProxy``로 위임)
    - ``models.CommentSpec``: 주석 마커 사양 VO

호출관계:
    ``pipeline.run_pipeline()`` → ``strip_comments()``
    ``deep_compare._extract_one()`` → ``strip_comments()``

주의:
    이 모듈은 소스코드의 라인 번호 보존을 기본 원칙으로 한다.
    ``squash_blanks=True``는 라인 번호를 변경하므로 포렌식 보고서에서 사용 금지.
"""

from __future__ import annotations

import enum
import logging
import re
from typing import Optional

from collections.abc import Iterable, Iterator, Mapping

from diffinite.models import CommentSpec

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# 언어 레지스트리 위임
# ──────────────────────────────────────────────────────────────────────
from diffinite.languages import get_spec, all_extensions  # noqa: E402


class _RegistryProxy(Mapping):
    """``COMMENT_SPECS[ext]`` → ``get_spec(ext).comment`` 프록시.

    v0.3 이전의 dict 기반 ``COMMENT_SPECS`` 접근 패턴과 완전 호환.
    ``[]``, ``.get()``, ``in``, ``len()``, ``iter()`` 모두 지원.

    설계 의도:
        ``parser.py``의 기존 코드와 하위 호환을 유지하면서,
        실제 데이터 소스를 ``languages/`` 레지스트리로 이관.
    """

    def __getitem__(self, ext: str) -> CommentSpec:
        spec = get_spec(ext)
        if spec is None:
            raise KeyError(ext)
        return spec.comment

    def __iter__(self) -> Iterator[str]:
        return iter(all_extensions())

    def __len__(self) -> int:
        return len(all_extensions())

    def __contains__(self, ext: object) -> bool:  # type: ignore[override]
        return get_spec(ext) is not None if isinstance(ext, str) else False

    def __repr__(self) -> str:
        return f"_RegistryProxy({len(self)} extensions)"


COMMENT_SPECS: Mapping[str, CommentSpec] = _RegistryProxy()
"""확장자 → CommentSpec 매핑. 읽기 전용.
내부적으로 ``languages/`` 레지스트리에 위임한다."""


def _has_ifdef_zero(ext: str) -> bool:
    """C/C++ 계열에서 ``#if 0`` 전처리 블록 지원 여부를 확인한다."""
    spec = get_spec(ext)
    return spec.has_ifdef_zero if spec else False


# 레거시 호환: C-family 확장자 집합 (외부 코드에서 참조 가능)
_C_FAMILY_EXTS = frozenset(
    ext for ext in all_extensions() if (s := get_spec(ext)) is not None and s.has_ifdef_zero
)


# ──────────────────────────────────────────────────────────────────────
# #if 0 전처리 블록 제거 (C-family 전용)
# ──────────────────────────────────────────────────────────────────────
# 뒤따르는 주석(`#if 0 // disabled`, `#if 0 /* ... */`)도 허용한다.
_IF0_PATTERN = re.compile(
    r"^\s*#\s*if\s+0\s*(?://.*|/\*.*)?$",
    re.MULTILINE,
)
_ENDIF_PATTERN = re.compile(
    r"^\s*#\s*endif\b",
    re.MULTILINE,
)
# 중첩 깊이를 올리는 모든 조건부 지시문 (#if / #ifdef / #ifndef)
_IF_OPEN_PATTERN = re.compile(r"#\s*if(?:n?def)?\b")
# 바깥 `#if 0` 의 죽은 분기를 끝내는 지시문 — 이후 분기는 살아 있는 코드
_ELSE_PATTERN = re.compile(r"#\s*(?:else|elif)\b")


def _strip_ifdef_zero(text: str, code_starts: Optional[list[bool]] = None) -> str:
    """``#if 0 … #endif`` 블록을 제거한다. 라인 수는 보존 (빈 줄로 대체).

    중첩 ``#if``/``#ifdef``/``#ifndef``/``#endif``를 depth 카운터로 추적하여
    가장 바깥쪽 ``#if 0`` 블록만 제거한다. 바깥 블록의 ``#else``/``#elif``
    이후 분기는 컴파일되는 코드이므로 보존한다 (지시문 줄 자체도 원문 유지).

    Note:
        ``#if 0``은 "코드를 주석 처리하는 관용적 방법"으로,
        ``/* ... */``와 달리 중첩이 가능하다.
        이 함수가 없으면 ``#if 0`` 내부의 코드가 유사도 계산에 포함되어
        위양성이 증가한다.

    Args:
        code_starts: ``_strip_2pass_states``가 돌려준 줄별 플래그. False인 줄은
            문자열(C# 축자 ``@"`` 문자열, 원시 문자열, 백슬래시로 이어진 문자열 등) 안에서 시작하므로
            어떤 지시문(``#if``/``#else``/``#endif``)으로도 보지 않는다.
    """
    result: list[str] = []
    lines = text.split("\n")
    depth = 0  # #if 0 내부 중첩 깊이
    block_start = -1  # 현재 바깥 #if 0 블록이 시작된 줄 번호
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if code_starts is not None and i < len(code_starts) and not code_starts[i]:
            # 문자열 안에서 시작한 줄 — 지시문이 아니라 문자열 내용이다.
            result.append(line if depth == 0 else "")
            i += 1
            continue

        if depth == 0:
            if _IF0_PATTERN.match(line):
                depth = 1
                block_start = i
                result.append("")  # 라인 수 보존
            else:
                result.append(line)
        else:
            # #if 0 블록 내부
            if _IF_OPEN_PATTERN.match(stripped):
                depth += 1
            elif _ENDIF_PATTERN.match(stripped):
                depth -= 1
            elif depth == 1 and _ELSE_PATTERN.match(stripped):
                depth = 0
                result.append(line)  # 살아 있는 분기 시작 — 원문 유지
                i += 1
                continue
            result.append("")  # 항상 빈 줄 (라인 수 보존)

        i += 1
    if depth > 0:
        # 닫히지 않은 #if 0 (예: 주석 안의 예시 텍스트)은 지시문으로 확신할 수
        # 없으므로 원문을 그대로 둔다 — 파일 끝까지 지우면 살아 있는 코드가 사라진다.
        result[block_start:] = lines[block_start:]
    return "\n".join(result)


# ──────────────────────────────────────────────────────────────────────
# 상태 머신
# ──────────────────────────────────────────────────────────────────────
class _State(enum.Enum):
    """2-pass 파서의 6가지 상태.

    ``CODE`` → ``IN_STRING``: 문자열 구분자(``"``, ``'``) 만남
    ``CODE`` → ``IN_TEMPLATE_LITERAL``: 백틱(`` ` ``) 만남 (JS 템플릿 리터럴)
    ``CODE`` → ``IN_LINE_COMMENT``: 라인 주석 마커 만남
    ``CODE`` → ``IN_BLOCK_COMMENT``: 블록 주석 시작 만남
    ``CODE`` → ``IN_REGEX``: 식이 올 자리의 ``/`` 만남 (JS 정규식 리터럴)
    ``IN_LINE_COMMENT`` → ``CODE``: 줄 바꿈
    ``IN_BLOCK_COMMENT`` → ``CODE``: 블록 주석 종료 마커 만남
    ``IN_STRING`` → ``CODE``: 닫는 구분자 만남
    ``IN_TEMPLATE_LITERAL`` → ``CODE``: ``${`` 진입 (depth증가 후 CODE로) / 백틱 닫힘
    ``IN_REGEX`` → ``CODE``: 닫는 ``/`` 만남 (문자 클래스 ``[...]`` 밖)
    ``CODE`` → ``IN_TEMPLATE_LITERAL``: active ``${...}`` at brace depth zero
    """

    CODE = "CODE"
    IN_STRING = "IN_STRING"
    IN_LINE_COMMENT = "IN_LINE_COMMENT"
    IN_BLOCK_COMMENT = "IN_BLOCK_COMMENT"
    IN_TEMPLATE_LITERAL = "IN_TEMPLATE_LITERAL"
    IN_REGEX = "IN_REGEX"


# JS에서 ``/`` 직전 토큰이 아래에 속하면 식이 올 자리 → 정규식 리터럴로 본다.
# (그렇지 않으면 나눗셈 연산자.) 표준 토크나이저 휴리스틱.
_REGEX_PREV_CHARS = frozenset("(,;{}[=+-*%&|^!~<>?:")
_REGEX_PREV_KEYWORDS = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "do",
        "else",
        "yield",
        "await",
        "case",
    }
)

# These tokens can be followed by an object literal expression.  Tracking the
# matching brace lets a following slash be classified as division, while a
# slash after a statement block can still open a regular-expression literal.
_OBJECT_LITERAL_PREV_CHARS = frozenset("(,[=:+-*/%&|^!~?")
_OBJECT_LITERAL_PREV_KEYWORDS = frozenset({"return", "yield", "case", "throw"})


# Rust 문자 리터럴 'x', '\n', '\x7f', '\u{1F600}' (Rust Reference, "Character literals":
# \x takes exactly 2 hex digits; \u{} takes up to 6 hex digits, '_' allowed, hence {1,8}).
_RUST_CHAR_LITERAL = re.compile(r"'(?:\\u\{[0-9A-Fa-f_]{1,8}\}|\\x[0-9A-Fa-f]{2}|\\.|[^'\\\n])'")

# C++11 raw string opener (C++ standard [lex.string]): optional encoding prefix,
# R", a d-char-sequence of at most 16 chars (no space, parens, backslash,
# tab/vtab/formfeed/newline), then '('.
_CPP_RAW_STRING_OPEN = re.compile(r'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(')


def _marker_allowed(
    line: str,
    pos: int,
    boundary: Optional[str],
    not_after: str,
    exceptions: tuple[str, ...],
) -> bool:
    """``line[pos]``에서 시작하는 라인 주석 마커가 그 언어에서 실제 주석인지."""
    prev = line[pos - 1] if pos > 0 else ""
    if prev and prev in not_after:
        return False
    if boundary is not None and prev and not prev.isspace() and prev not in boundary:
        return False
    return not any(line.startswith(e, pos) for e in exceptions)


def _is_word_char(ch: str) -> bool:
    """식별자/숫자 토큰을 이루는 문자인지 (``\\w`` 또는 ``$``)."""
    return ch.isalnum() or ch in "_$"


def _regex_allowed(prev_sig: str, prev_word: str) -> bool:
    """직전 유의미 토큰을 보고 ``/`` 가 정규식 리터럴을 여는 위치인지 판정한다."""
    if prev_word in _REGEX_PREV_KEYWORDS:
        return True
    if prev_sig == "":  # 입력/문맥 시작 — 식이 올 자리
        return True
    return prev_sig in _REGEX_PREV_CHARS


def _object_literal_allowed(prev_sig: str, prev_word: str) -> bool:
    """Return whether an opening brace is in an expression-value position."""
    return prev_word in _OBJECT_LITERAL_PREV_KEYWORDS or prev_sig in _OBJECT_LITERAL_PREV_CHARS


def _has_any_marker(line: str, spec: CommentSpec) -> bool:
    """Fast-path 판별: 이 라인이 slow-path 스캔이 필요한지 확인.

    주석 마커 외에 **문자열/템플릿 구분자**와 (JS 계열의) ``/`` 도 체크한다.
    문자열·정규식이 열리/닫히면 후속 라인의 상태가 바뀌기 때문이다.
    구분자는 언어 사양(``spec``)에서 가져오므로, HTML/CSS처럼 따옴표를
    데이터로 두는 언어에서는 따옴표만으로 slow-path를 타지 않는다.
    """
    for m in spec.line_markers:
        if m in line:
            return True
    if spec.block_start and spec.block_start in line:
        return True
    if spec.block_end and spec.block_end in line:
        return True
    for d in spec.string_delims:
        if d in line:
            return True
    for d in spec.template_delims:
        if d in line:
            return True
    # Braces affect whether a later slash is division or a regex opener, so JS
    # brace lines also need the stateful scan even when they contain no comment.
    if spec.has_regex_literals and any(marker in line for marker in ("/", "{", "}")):
        return True
    return False


def has_comment_rules(extension: str) -> bool:
    """이 확장자에 ``strip_comments``가 적용할 주석 규칙이 있는지.

    False이면 ``strip_comments``는 원문을 그대로 돌려준다 — 보고서는 이런
    파일의 주석이 남았음을 밝혀야 한다(``models.stripped_comment_mode``).
    """
    spec = COMMENT_SPECS.get(extension)
    return spec is not None and bool(spec.line_markers or spec.block_start)


def extensions_without_comment_rules(extensions: Iterable[str]) -> list[str]:
    """주석 규칙이 없는 확장자들을 정렬·중복 제거해 반환한다 (보고서 공개용)."""
    return sorted({ext for ext in extensions if not has_comment_rules(ext)})


def comment_extensions_for_pair(ext_a: str, ext_b: str) -> tuple[str, str]:
    """매칭된 파일 쌍의 각 쪽에 적용할 주석 규칙의 확장자를 고른다.

    각 파일은 자기 언어의 규칙으로 제거한다(.py vs .js 쌍을 상대 문법으로
    파싱하지 않도록). 한쪽 확장자에만 규칙이 없으면(``Foo.java`` vs
    ``Foo.java.orig``) 그쪽은 상대의 확장자를 빌려 쓴다 — 라인 채널과 Deep
    Compare 채널이 같은 쌍에 같은 규칙을 쓰도록 두 채널 모두 이 함수를 쓴다.
    양쪽 모두 규칙이 없으면 그대로 반환한다(``strip_comments``가 원문 유지).
    """
    rules_a = has_comment_rules(ext_a)
    rules_b = has_comment_rules(ext_b)
    if not rules_a and rules_b:
        return ext_b, ext_b
    if not rules_b and rules_a:
        return ext_a, ext_a
    return ext_a, ext_b


def strip_comments(
    text: str,
    extension: str,
    *,
    squash_blanks: bool = False,
) -> str:
    """소스코드에서 주석을 제거한다.

    2-pass 주석 제거 후, C/C++/C# 확장자에서는 ``#if 0 … #endif`` 블록을
    추가로 제거한다(주석 안의 ``#if 0``은 지시문이 아니므로 주석 제거가 먼저).

    Args:
        squash_blanks: True이면 3줄 이상의 연속 빈 줄을 1줄로 축소.
                       **주의**: 라인 번호가 변경되므로 포렌식 추적에 부적합.

    Returns:
        주석이 제거된 텍스트. 확장자에 대한 주석 사양이 없으면 원문 그대로 반환.
    """
    if not has_comment_rules(extension):
        return text
    spec = COMMENT_SPECS[extension]

    result, code_starts = _strip_2pass_states(text, spec)

    # Post-pass: C/C++/C# #if 0 블록 제거. 주석 제거 *후*에 실행한다 — C 번역
    # 단계 3(주석 → 공백)이 단계 4(전처리 지시문)보다 먼저이므로, 주석 안에
    # 적힌 '#if 0' 예시는 지시문이 아니다. 두 단계 모두 라인 수를 보존한다.
    if _has_ifdef_zero(extension):
        result = _strip_ifdef_zero(result, code_starts)

    if squash_blanks:
        result = _squash_blank_lines(result)

    return result


def _strip_2pass(text: str, spec: CommentSpec) -> str:
    """주석을 제거한 텍스트만 돌려준다 (``_strip_2pass_states`` 참조)."""
    return _strip_2pass_states(text, spec)[0]


def _strip_2pass_states(text: str, spec: CommentSpec) -> tuple[str, list[bool]]:
    """최적화된 2-pass 주석 제거기.

    Returns:
        (주석 제거 텍스트, 줄별 플래그). 플래그는 그 줄이 일반 코드 상태(문자열·
        템플릿·블록 주석·보간 바깥)에서 시작했는지이다 — ``#if 0`` 후처리가 문자열
        안의 ``#if 0`` 줄을 지시문으로 오인하지 않도록 쓴다.

    라인 단위로 분할하여:
    1. ``CODE`` 상태 + 마커 없음 → 즉시 통과 (fast-path)
    2. 마커 있음 또는 비-CODE 상태 상속 → 문자 단위 스캔 (slow-path)

    상태는 라인 간에 유지된다:
    - 블록 주석이 여러 줄에 걸칠 수 있음
    - 트리플-쿼트 문자열이 여러 줄에 걸칠 수 있음
    """
    lines = text.split("\n")
    out_parts: list[str] = []
    state = _State.CODE
    string_delim: Optional[str] = None  # 현재 열린 문자열 구분자
    escaped = False  # 이전 문자가 백슬래시인지
    # One brace-depth counter per active ${...} interpolation. Object/block
    # braces inside an interpolation must close before its delimiter can do so.
    template_brace_depths: list[int] = []
    template_brace_values: list[list[bool]] = []
    # Outside template interpolations, distinguish value-producing object
    # literals from statement blocks so a slash after ``{}`` is unambiguous.
    code_brace_values: list[bool] = []
    regex_in_class = False  # IN_REGEX: 문자 클래스 [...] 내부 여부
    # 정규식 vs 나눗셈 판별을 위한 직전 유의미 토큰 추적
    prev_sig = ""  # 직전 비공백 코드 문자
    cur_word = ""  # 직전(또는 현재) 식별자 토큰
    in_word = False  # 현재 식별자 토큰을 이어가는 중인지
    prev_word_line = -1  # keyword context must not cross ASI newline

    line_markers = spec.line_markers
    block_start = spec.block_start or ""
    block_end = spec.block_end or ""
    string_delims = spec.string_delims
    template_delims = spec.template_delims
    has_regex = spec.has_regex_literals
    block_anchored = spec.block_markers_line_anchored
    nested_blocks = spec.nested_block_comments
    triple_delims = spec.triple_quote_delims
    template_escapes = spec.template_escapes
    char_strict = spec.char_literals_strict
    marker_boundary = spec.line_marker_boundary
    marker_not_after = spec.line_marker_not_after
    marker_exceptions = spec.line_marker_exceptions
    block_depth = 0  # IN_BLOCK_COMMENT 중첩 깊이 (nested_block_comments 언어)
    # LanguageCommentSpec 확장 필드 (일반 CommentSpec이면 종전 동작).
    template_interp = getattr(spec, "template_interpolation", True)
    verbatim_prefixes: tuple[str, ...] = getattr(spec, "verbatim_string_prefixes", ())
    verbatim = False  # IN_STRING이 C# @"..." (이스케이프 없음, "" = 따옴표, 여러 줄)
    cpp_raw = getattr(spec, "cpp_raw_strings", False)
    # IN_STRING이 C++ 원시 문자열이면 그 닫는 시퀀스 ``)delim"`` (아니면 None).
    raw_close: Optional[str] = None
    code_starts: list[bool] = []

    def _value_end():
        # 문자열/정규식/템플릿은 '값'이므로 이후 / 는 나눗셈이다.
        nonlocal prev_sig, cur_word, in_word
        prev_sig = ")"
        cur_word = ""
        in_word = False

    for line_idx, line in enumerate(lines):
        code_starts.append(state is _State.CODE and not template_brace_depths)
        # ── Fast-path ──
        if state is _State.CODE and not template_brace_depths and not _has_any_marker(line, spec):
            out_parts.append(line)
            # JS 정규식 판별 정확도를 위해 통과한 코드의 끝 토큰을 기록한다
            # (다음 줄 첫 토큰이 정규식인지 판단할 때 필요).
            if has_regex:
                s = line.rstrip()
                if s:
                    prev_sig = s[-1]
                    j = len(s)
                    while j > 0 and (s[j - 1].isalnum() or s[j - 1] in "_$"):
                        j -= 1
                    cur_word = s[j:]
                    in_word = False
                    if cur_word:
                        prev_word_line = line_idx
            continue

        # ── Slow-path: 문자 단위 상태 머신 ──
        line_out: list[str] = []
        pos = 0
        length = len(line)

        while pos < length:
            ch = line[pos]

            # ── IN_LINE_COMMENT: 줄 끝까지 소비 ──
            if state is _State.IN_LINE_COMMENT:
                break

            # ── IN_BLOCK_COMMENT: 종료 마커 탐색 ──
            if state is _State.IN_BLOCK_COMMENT:
                if nested_blocks and block_start and line.startswith(block_start, pos):
                    block_depth += 1
                    pos += len(block_start)
                    continue
                if (
                    block_end
                    and (not block_anchored or pos == 0)
                    and line[pos : pos + len(block_end)] == block_end
                ):
                    pos += len(block_end)
                    block_depth -= 1
                    if nested_blocks and block_depth > 0:
                        continue
                    state = _State.CODE
                    # 컴파일러처럼 주석을 공백으로 취급한다: 'int/*x*/y' 가 존재하지
                    # 않는 식별자 'inty' 로 붙지 않도록, 양쪽이 모두 단어 문자일 때만
                    # 공백 하나를 남긴다(그 외 줄 내용·줄 번호는 종전과 동일).
                    # Markup (<!-- -->) is excluded: there a comment is not whitespace,
                    # and "foo<!-- c -->bar" renders as the single word "foobar".
                    in_word = False
                    if (
                        spec.block_start != "<!--"
                        and line_out
                        and pos < length
                        and _is_word_char(line_out[-1][-1])
                        and _is_word_char(line[pos])
                    ):
                        line_out.append(" ")
                else:
                    pos += 1
                continue

            # ── IN_REGEX: 정규식 리터럴 내부 (코드로 보존) ──
            if state is _State.IN_REGEX:
                if escaped:
                    line_out.append(ch)
                    escaped = False
                    pos += 1
                    continue
                if ch == "\\":
                    escaped = True
                    line_out.append(ch)
                    pos += 1
                    continue
                if ch == "[":
                    regex_in_class = True
                    line_out.append(ch)
                    pos += 1
                    continue
                if ch == "]":
                    regex_in_class = False
                    line_out.append(ch)
                    pos += 1
                    continue
                if ch == "/" and not regex_in_class:
                    line_out.append(ch)
                    pos += 1
                    state = _State.CODE
                    _value_end()
                    continue
                line_out.append(ch)
                pos += 1
                continue

            # ── IN_STRING: 이스케이프 및 닫힘 처리 ──
            if state is _State.IN_STRING:
                assert string_delim is not None
                if raw_close is not None:
                    # C++ 원시 문자열: 이스케이프 없음, )delim" 에서만 닫힌다.
                    end = line.find(raw_close, pos)
                    if end < 0:
                        line_out.append(line[pos:])
                        pos = length
                        continue
                    end += len(raw_close)
                    line_out.append(line[pos:end])
                    pos = end
                    state = _State.CODE
                    string_delim = None
                    raw_close = None
                    _value_end()
                    continue
                if verbatim:
                    if ch == '"' and line.startswith('""', pos):
                        line_out.append('""')  # 이중 따옴표 = 문자 그대로의 따옴표
                        pos += 2
                        continue
                    line_out.append(ch)
                    pos += 1
                    if ch == '"':
                        state = _State.CODE
                        string_delim = None
                        verbatim = False
                        _value_end()
                    continue
                if escaped:
                    line_out.append(ch)
                    pos += 1
                    # CRLF 파일: 줄 끝의 백슬래시 다음 CR 은 줄 이음이다 (CR 은 줄바꿈의 일부).
                    escaped = ch == "\r" and pos == length
                    continue
                if ch == "\\":
                    escaped = True
                    line_out.append(ch)
                    pos += 1
                    continue
                # 트리플-쿼트 닫힘 (""" 또는 ''')
                if len(string_delim) == 3 and line[pos : pos + 3] == string_delim:
                    line_out.append(string_delim)
                    pos += 3
                    state = _State.CODE
                    string_delim = None
                    _value_end()
                    continue
                # 단일 구분자 닫힘
                if len(string_delim) == 1 and ch == string_delim:
                    line_out.append(ch)
                    pos += 1
                    state = _State.CODE
                    string_delim = None
                    _value_end()
                    continue
                line_out.append(ch)
                pos += 1
                continue

            # ── IN_TEMPLATE_LITERAL: ${} 및 닫힘 처리 ──
            if state is _State.IN_TEMPLATE_LITERAL:
                if escaped:
                    line_out.append(ch)
                    pos += 1
                    escaped = ch == "\r" and pos == length  # CRLF 줄 이음 (위와 동일)
                    continue
                if ch == "\\" and template_escapes:
                    escaped = True
                    line_out.append(ch)
                    pos += 1
                    continue
                # ${} 표현식 진입 → CODE로 전환, depth 증가
                if template_interp and ch == "$" and pos + 1 < length and line[pos + 1] == "{":
                    line_out.append("${")
                    pos += 2
                    template_brace_depths.append(0)
                    template_brace_values.append([])
                    state = _State.CODE
                    # Interpolation starts in expression position.  Using an
                    # opening-paren sentinel lets an immediate ``{}`` be
                    # recognized as an object literal rather than a block.
                    prev_sig = "("
                    cur_word = ""
                    in_word = False
                    continue
                # 닫는 구분자(백틱) → CODE 복귀
                if ch in template_delims:
                    line_out.append(ch)
                    pos += 1
                    state = _State.CODE
                    _value_end()
                    continue
                line_out.append(ch)
                pos += 1
                continue

            # ── CODE: C# 축자 문자열 @"..." 열림 ──
            if verbatim_prefixes and any(line.startswith(vp, pos) for vp in verbatim_prefixes):
                vp = next(vp for vp in verbatim_prefixes if line.startswith(vp, pos))
                line_out.append(vp)
                pos += len(vp)
                state = _State.IN_STRING
                string_delim = '"'
                verbatim = True
                continue

            # ── CODE: C++ 원시 문자열 R"delim( 열림 ──
            # 접두사 앞이 식별자 문자이면(예: fooR"...") 원시 문자열 접두사가 아니다.
            if (
                cpp_raw
                and ch in "uULR"
                and not (pos > 0 and _is_word_char(line[pos - 1]))
                and (m := _CPP_RAW_STRING_OPEN.match(line, pos))
            ):
                line_out.append(m.group(0))
                pos = m.end()
                state = _State.IN_STRING
                string_delim = '"'
                raw_close = ")" + m.group(1) + '"'
                continue

            # ── CODE: 문자열 열림 감지 ──
            if ch in string_delims:
                triple = ch * 3
                if ch in triple_delims and line[pos : pos + 3] == triple:
                    line_out.append(triple)
                    pos += 3
                    state = _State.IN_STRING
                    string_delim = triple
                    continue
                line_out.append(ch)
                pos += 1
                state = _State.IN_STRING
                string_delim = ch
                continue

            # Rust: 완전한 문자 리터럴('x', '\n', '\u{..}')만 리터럴로 통째로 보존하고,
            # 그 외의 ' (라이프타임 'a, 레이블 'outer)는 일반 코드 문자로 둔다.
            if char_strict and ch == "'":
                m = _RUST_CHAR_LITERAL.match(line, pos)
                if m:
                    line_out.append(m.group(0))
                    pos = m.end()
                    _value_end()
                    continue

            # 백틱 템플릿 리터럴 (JS/Go)
            if ch in template_delims:
                line_out.append(ch)
                pos += 1
                state = _State.IN_TEMPLATE_LITERAL
                continue

            # Interpolation-local object/block braces do not end ${...}.
            if ch == "{" and template_brace_depths:
                prev_word = cur_word if prev_word_line == line_idx else ""
                template_brace_values[-1].append(_object_literal_allowed(prev_sig, prev_word))
                line_out.append(ch)
                pos += 1
                template_brace_depths[-1] += 1
                prev_sig = ch
                cur_word = ""
                in_word = False
                continue

            # Only a '}' at interpolation brace depth zero returns to template
            # text; nested object/block closers stay in CODE.
            if ch == "}" and template_brace_depths:
                line_out.append(ch)
                pos += 1
                if template_brace_depths[-1] > 0:
                    template_brace_depths[-1] -= 1
                    is_value = template_brace_values[-1].pop()
                    prev_sig = ")" if is_value else ch
                    cur_word = ""
                    in_word = False
                else:
                    template_brace_depths.pop()
                    template_brace_values.pop()
                    state = _State.IN_TEMPLATE_LITERAL
                continue

            # Outside ${...}, remember whether a brace opened an object value
            # or a statement block.  Both look identical character-by-character
            # but only an object value can be the left operand of division.
            if has_regex and ch == "{":
                prev_word = cur_word if prev_word_line == line_idx else ""
                code_brace_values.append(_object_literal_allowed(prev_sig, prev_word))
                line_out.append(ch)
                pos += 1
                prev_sig = ch
                cur_word = ""
                in_word = False
                continue

            if has_regex and ch == "}":
                is_value = code_brace_values.pop() if code_brace_values else False
                line_out.append(ch)
                pos += 1
                prev_sig = ")" if is_value else ch
                cur_word = ""
                in_word = False
                continue

            # ── CODE: JS 정규식 리터럴 시작 (식이 올 자리의 / ) ──
            if has_regex and ch == "/":
                nxt = line[pos + 1] if pos + 1 < length else ""
                if nxt not in ("/", "*") and _regex_allowed(prev_sig, cur_word):
                    line_out.append(ch)
                    pos += 1
                    state = _State.IN_REGEX
                    regex_in_class = False
                    continue
                # 그 외(//, /*, 또는 나눗셈)는 아래 주석/코드 처리로 진행

            # ── CODE: 블록 주석 시작 ──
            if (
                block_start
                and (not block_anchored or pos == 0)
                and line[pos : pos + len(block_start)] == block_start
            ):
                state = _State.IN_BLOCK_COMMENT
                block_depth = 1
                pos += len(block_start)
                continue

            # ── CODE: 라인 주석 시작 ──
            marker_matched = False
            for marker in line_markers:
                if line[pos : pos + len(marker)] == marker and _marker_allowed(
                    line, pos, marker_boundary, marker_not_after, marker_exceptions
                ):
                    state = _State.IN_LINE_COMMENT
                    pos += len(marker)
                    marker_matched = True
                    break
            if marker_matched:
                continue

            # 일반 코드 문자 — 정규식 판별용 토큰 추적
            line_out.append(ch)
            if ch.isspace():
                in_word = False  # 단어 경계 (cur_word는 직전 토큰으로 유지)
            elif ch.isalnum() or ch in "_$":
                cur_word = (cur_word + ch) if in_word else ch
                in_word = True
                prev_sig = ch
                prev_word_line = line_idx
            else:
                prev_sig = ch
                cur_word = ""
                in_word = False
            pos += 1

        # 라인 종료: IN_LINE_COMMENT → CODE 복귀
        if state is _State.IN_LINE_COMMENT:
            state = _State.CODE

        # 줄 끝의 백슬래시는 다음 줄 첫 문자를 이스케이프하지 않는다: 문자열/템플릿
        # 안이면 줄 이음(C 번역 단계 2, Python·JS 동일)이고, 그 외에는 의미가 없다.
        line_continued = escaped
        escaped = False

        # C1 안전장치: 닫히지 않은 단일 구분자 문자열은 줄 끝에서 복구
        # 트리플-쿼트(""", ''') 문자열은 여러 줄에 걸치므로 예외.
        # 깨진 소스코드에서 이후 전체 라인의 주석 제거가 무효화되는 것을 방지.
        # 단, 백슬래시로 이어진 줄(line_continued)은 문자열이 다음 줄로 계속된다.
        if (
            state is _State.IN_STRING
            and string_delim is not None
            and len(string_delim) == 1
            and not line_continued
            and not verbatim
            and raw_close is None
        ):
            _logger.debug(
                "Unclosed string (delim=%r) at end of line %d; resetting the parser to code state.",
                string_delim,
                line_idx + 1,
            )
            state = _State.CODE
            string_delim = None

        # 정규식 리터럴은 한 줄을 넘지 않는다 — 줄 끝에서 미닫힘이면 CODE로 복구.
        if state is _State.IN_REGEX:
            state = _State.CODE
            regex_in_class = False
            _value_end()

        out_parts.append("".join(line_out))

    return "\n".join(out_parts), code_starts


# 3줄 이상 연속 빈 줄 → 단일 빈 줄로 축소
_BLANK_EXPLOSION_RE = re.compile(r"(\n[ \t]*){3,}")


def _squash_blank_lines(text: str) -> str:
    """블록 주석 제거 후 발생하는 빈 줄 폭증을 방지한다.

    3줄 이상의 연속 빈 줄(공백/탭만 있는 줄 포함)을 단일 빈 줄로 축소.

    Note:
        이 함수는 라인 번호를 변경한다. 포렌식 보고서에서는 사용하지 말 것.
    """
    return _BLANK_EXPLOSION_RE.sub("\n\n", text)
