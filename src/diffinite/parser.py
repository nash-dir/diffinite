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
    ``deep_compare._extract_multi()`` → ``strip_comments()``

주의:
    이 모듈은 소스코드의 라인 번호 보존을 기본 원칙으로 한다.
    ``squash_blanks=True``는 라인 번호를 변경하므로 포렌식 보고서에서 사용 금지.
"""

from __future__ import annotations

import enum
import re
from typing import Optional

from collections.abc import Iterator, Mapping

from diffinite.models import CommentSpec

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
    ext for ext in all_extensions()
    if (s := get_spec(ext)) is not None and s.has_ifdef_zero
)


# ──────────────────────────────────────────────────────────────────────
# #if 0 전처리 블록 제거 (C-family 전용)
# ──────────────────────────────────────────────────────────────────────
_IF0_PATTERN = re.compile(
    r"^\s*#\s*if\s+0\s*$",    re.MULTILINE,
)
_ENDIF_PATTERN = re.compile(
    r"^\s*#\s*endif\b",       re.MULTILINE,
)


def _strip_ifdef_zero(text: str) -> str:
    """``#if 0 … #endif`` 블록을 제거한다. 라인 수는 보존 (빈 줄로 대체).

    중첩 ``#if``/``#endif``를 depth 카운터로 추적하여
    가장 바깥쪽 ``#if 0`` 블록만 제거한다.

    Note:
        ``#if 0``은 "코드를 주석 처리하는 관용적 방법"으로,
        ``/* ... */``와 달리 중첩이 가능하다.
        이 함수가 없으면 ``#if 0`` 내부의 코드가 유사도 계산에 포함되어
        위양성이 증가한다.
    """
    result: list[str] = []
    lines = text.split("\n")
    depth = 0  # #if 0 내부 중첩 깊이
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        if depth == 0:
            if _IF0_PATTERN.match(line):
                depth = 1
                result.append("")  # 라인 수 보존
            else:
                result.append(line)
        else:
            # #if 0 블록 내부
            if stripped.startswith("#") and re.match(r"#\s*if\b", stripped):
                depth += 1
            elif stripped.startswith("#") and re.match(r"#\s*endif\b", stripped):
                depth -= 1
            result.append("")  # 항상 빈 줄 (라인 수 보존)

        i += 1
    return "\n".join(result)


# ──────────────────────────────────────────────────────────────────────
# 상태 머신
# ──────────────────────────────────────────────────────────────────────
class _State(enum.Enum):
    """2-pass 파서의 5가지 상태.

    ``CODE`` → ``IN_STRING``: 문자열 구분자(``"``, ``'``) 만남
    ``CODE`` → ``IN_TEMPLATE_LITERAL``: 백틱(`` ` ``) 만남 (JS 템플릿 리터럴)
    ``CODE`` → ``IN_LINE_COMMENT``: 라인 주석 마커 만남
    ``CODE`` → ``IN_BLOCK_COMMENT``: 블록 주석 시작 만남
    ``IN_LINE_COMMENT`` → ``CODE``: 줄 바꿈
    ``IN_BLOCK_COMMENT`` → ``CODE``: 블록 주석 종료 마커 만남
    ``IN_STRING`` → ``CODE``: 닫는 구분자 만남
    ``IN_TEMPLATE_LITERAL`` → ``CODE``: ``${`` 진입 (depth증가 후 CODE로) / 백틱 닫힘
    ``CODE`` → ``IN_TEMPLATE_LITERAL``: ``}`` with template_depth > 0
    """
    CODE = "CODE"
    IN_STRING = "IN_STRING"
    IN_LINE_COMMENT = "IN_LINE_COMMENT"
    IN_BLOCK_COMMENT = "IN_BLOCK_COMMENT"
    IN_TEMPLATE_LITERAL = "IN_TEMPLATE_LITERAL"


def _has_any_marker(line: str, spec: CommentSpec) -> bool:
    """Fast-path 판별: 이 라인이 slow-path 스캔이 필요한지 확인.

    주석 마커 외에 **문자열 구분자**(``"``, ``'``, `` ` ``)도 체크한다.
    문자열이 열리/닫히면 후속 라인의 상태가 바뀌기 때문.
    """
    for m in spec.line_markers:
        if m in line:
            return True
    if spec.block_start and spec.block_start in line:
        return True
    if spec.block_end and spec.block_end in line:
        return True
    # 문자열 구분자는 크로스-라인 상태에 영향 (예: 트리플-쿼트)
    if '"' in line or "'" in line or '`' in line:
        return True
    return False


def strip_comments(
    text: str,
    extension: str,
    *,
    squash_blanks: bool = False,
) -> str:
    """소스코드에서 주석을 제거한다.

    C-family 확장자에서는 ``#if 0 … #endif`` 블록을 사전 제거한 후
    2-pass 주석 제거를 수행한다.

    Args:
        squash_blanks: True이면 3줄 이상의 연속 빈 줄을 1줄로 축소.
                       **주의**: 라인 번호가 변경되므로 포렌식 추적에 부적합.

    Returns:
        주석이 제거된 텍스트. 확장자에 대한 주석 사양이 없으면 원문 그대로 반환.
    """
    spec = COMMENT_SPECS.get(extension)
    if spec is None:
        return text

    if not spec.line_markers and not spec.block_start:
        return text

    # Pre-pass: C-family #if 0 블록 제거
    if _has_ifdef_zero(extension):
        text = _strip_ifdef_zero(text)

    result = _strip_2pass(text, spec)

    if squash_blanks:
        result = _squash_blank_lines(result)

    return result


def _strip_2pass(text: str, spec: CommentSpec) -> str:
    """최적화된 2-pass 주석 제거기.

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
    escaped = False                      # 이전 문자가 백슬래시인지
    template_depth = 0                   # JS 템플릿 리터럴 중첩 깊이

    line_markers = spec.line_markers
    block_start = spec.block_start or ""
    block_end = spec.block_end or ""

    for line_idx, line in enumerate(lines):
        # ── Fast-path ──
        if state is _State.CODE and not _has_any_marker(line, spec):
            out_parts.append(line)
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
                if block_end and line[pos: pos + len(block_end)] == block_end:
                    pos += len(block_end)
                    state = _State.CODE
                else:
                    pos += 1
                continue

            # ── IN_STRING: 이스케이프 및 닫힘 처리 ──
            if state is _State.IN_STRING:
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
                # 트리플-쿼트 닫힘 (""" 또는 ''')
                if len(string_delim) == 3 and line[pos: pos + 3] == string_delim:
                    line_out.append(string_delim)
                    pos += 3
                    state = _State.CODE
                    string_delim = None
                    continue
                # 단일 구분자 닫힘
                if len(string_delim) == 1 and ch == string_delim:
                    line_out.append(ch)
                    pos += 1
                    state = _State.CODE
                    string_delim = None
                    continue
                line_out.append(ch)
                pos += 1
                continue

            # ── IN_TEMPLATE_LITERAL: ${} 및 닫힘 처리 ──
            if state is _State.IN_TEMPLATE_LITERAL:
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
                # ${} 표현식 진입 → CODE로 전환, depth 증가
                if ch == "$" and pos + 1 < length and line[pos + 1] == "{":
                    line_out.append("${")
                    pos += 2
                    template_depth += 1
                    state = _State.CODE
                    continue
                # 백틱 닫힘 → CODE 복귀
                if ch == "`":
                    line_out.append(ch)
                    pos += 1
                    state = _State.CODE
                    continue
                line_out.append(ch)
                pos += 1
                continue

            # ── CODE: 문자열 열림 감지 ──
            if ch in ('"', "'"):
                triple = ch * 3
                if line[pos: pos + 3] == triple:
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

            # 백틱 템플릿 리터럴 (JS/Go)
            if ch == "`":
                line_out.append(ch)
                pos += 1
                state = _State.IN_TEMPLATE_LITERAL
                continue

            # 중괄호 닫힘: 템플릿 리터럴 내 ${} 표현식 종료 → 템플릿으로 복귀
            if ch == "}" and template_depth > 0:
                template_depth -= 1
                line_out.append(ch)
                pos += 1
                state = _State.IN_TEMPLATE_LITERAL
                continue

            # ── CODE: 블록 주석 시작 ──
            if block_start and line[pos: pos + len(block_start)] == block_start:
                state = _State.IN_BLOCK_COMMENT
                pos += len(block_start)
                continue

            # ── CODE: 라인 주석 시작 ──
            marker_matched = False
            for marker in line_markers:
                if line[pos: pos + len(marker)] == marker:
                    state = _State.IN_LINE_COMMENT
                    pos += len(marker)
                    marker_matched = True
                    break
            if marker_matched:
                continue

            # 일반 코드 문자
            line_out.append(ch)
            pos += 1

        # 라인 종료: IN_LINE_COMMENT → CODE 복귀
        if state is _State.IN_LINE_COMMENT:
            state = _State.CODE

        out_parts.append("".join(line_out))

    return "\n".join(out_parts)


# 3줄 이상 연속 빈 줄 → 단일 빈 줄로 축소
_BLANK_EXPLOSION_RE = re.compile(r"(\n[ \t]*){3,}")


def _squash_blank_lines(text: str) -> str:
    """블록 주석 제거 후 발생하는 빈 줄 폭증을 방지한다.

    3줄 이상의 연속 빈 줄(공백/탭만 있는 줄 포함)을 단일 빈 줄로 축소.

    Note:
        이 함수는 라인 번호를 변경한다. 포렌식 보고서에서는 사용하지 말 것.
    """
    return _BLANK_EXPLOSION_RE.sub("\n\n", text)
