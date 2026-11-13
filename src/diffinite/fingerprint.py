"""Winnowing fingerprint extraction engine.

Implements a Stanford MOSS–style document-fingerprinting pipeline.
Flow: Tokenize → K-gram → Rolling Hash → Winnow → Fingerprint Set

Core guarantee:
    **Density guarantee** -- if two documents share a common substring of
    >= (W + K - 1) tokens, at least one common fingerprint is produced.
    With the current settings (K=5, W=4), any shared run of >= 8 tokens yields
    a shared fingerprint. Whether the file pair is *reported* still depends on
    the Deep Compare threshold.

Reference:
    Schleimer, Wilkerson, Aiken. "Winnowing: Local Algorithms for Document
    Fingerprinting". SIGMOD 2003.

Depends on:
    - ``models.FingerprintEntry``: fingerprint result value object
    - ``languages/``: keyword sets (for token normalization)

Call graph:
    ``deep_compare._extract_one()`` → ``extract_fingerprints()``
    ``extract_fingerprints()`` → ``tokenize()`` → ``rolling_hash()`` → ``winnow()``
"""

from __future__ import annotations

import logging
import re
import sys
import unicodedata
from typing import Sequence

from diffinite.models import FingerprintEntry

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# 핵심 상수
# ──────────────────────────────────────────────────────────────────────
DEFAULT_K: int = 5
"""K-gram 크기 (noise threshold: K 토큰 미만의 공유 구간은 매칭되지 않는다).
근거: Schleimer 2003은 코드용 k 값을 정하지 않고 문서 집합별 실험 선택을 권한다(§5).
K=5는 IR-Plag 보정 프로파일(calibration.NORMALIZE_CALIBRATION_K)에 고정된 값이다 —
과거 grid search 산출물은 저장소에 남아 있지 않으므로 근거로 인용하지 않는다.
K↑ = 정밀도↑ 재현율↓ (긴 공유 시퀀스만 탐지), K↓ = 재현율↑ 정밀도↓ (노이즈 증가)."""

DEFAULT_W: int = 4
"""Winnowing 윈도우 크기. W=4 → 밀도 보장 길이 = W+K-1 = 8 토큰 (Schleimer 2003 §3).
W↑ = 핑거프린트 수↓ (속도↑ 정밀도↓), W↓ = 핑거프린트 수↑ (속도↓ 정밀도↑)."""

HASH_BASE: int = 257
"""Karp-Rabin 다항식 롤링 해시의 밑(base). 토큰 해시 알파벳보다 크기만 하면 되며 튜닝 대상이 아니다."""

HASH_MOD: int = (1 << 61) - 1
"""해시 모듈러. Mersenne 소수 2^61-1 사용 — Python의 `pow(base, exp, mod)`로
효율적 모듈러 지수 연산 가능. 밑이 고정이므로 확률적 보장은 없으며, 일반(비적대적)
입력에서 충돌이 무시할 수준이라는 뜻이다 — 암호학적 보장이 아니다."""

# FNV offset basis and prime for 64-bit (Fowler-Noll-Vo, 1991).
_FNV1A_OFFSET = 0xcbf29ce484222325
_FNV1A_PRIME = 0x100000001b3
_FNV1A_MASK = 0xFFFFFFFFFFFFFFFF


def _fnv1a_64(s: str) -> int:
    """FNV-1a 64-bit 결정적 해시 — 프로세스 간 재현성을 보장한다.

    Python 내장 ``hash()``는 3.3+ 에서 프로세스별 랜덤 시드(PYTHONHASHSEED)를
    사용하므로, ``ProcessPoolExecutor`` spawn 워커 간에 같은 문자열이 다른
    해시값을 생성하여 Jaccard 비교를 오염시킨다.
    FNV-1a는 결정적이고, 짧은 문자열(토큰)에서 고속이며, 충돌 분포가 균일하다.
    """
    h = _FNV1A_OFFSET
    for b in s.encode('utf-8'):
        h ^= b
        h = (h * _FNV1A_PRIME) & _FNV1A_MASK
    return h

# 토크나이저 정규식 — 식별자, 숫자, 개별 구두점을 각각 토큰으로 분리. 공백은 버린다.
# 식별자는 유니코드 인식(``\w+``) — CJK·키릴 등 비ASCII 식별자를 글자당 토큰으로
# 쪼개지 않고 하나의 토큰으로 묶는다(비ASCII 소스의 핑거프린트 개수·밀도가
# ASCII와 비교 가능해진다). 숫자(소수 포함)를 먼저 매칭해 식별자 규칙이 숫자를
# 삼키지 않게 한다. 결과적으로 순수 ASCII 코드의 토큰화는 종전과 동일하다.
# Python 의 ``\w`` 는 결합 문자(유니코드 범주 Mn/Mc/Me — 데바나가리 비라마·모음 기호,
# NFD 악센트 등)를 매칭하지 않으므로, 식별자 대안에 결합 문자 클래스를 더해
# ``नमस्ते`` 같은 식별자가 한 토큰으로 남게 한다. 클래스는 실행 중인 Python 의
# ``unicodedata`` 데이터에서 만들어진다(``\w`` 자체와 같은 출처).
def _combining_mark_class() -> str:
    ranges: list[tuple[int, int]] = []
    for cp in range(sys.maxunicode + 1):
        if unicodedata.category(chr(cp))[0] != "M":
            continue
        if ranges and ranges[-1][1] == cp - 1:
            ranges[-1] = (ranges[-1][0], cp)
        else:
            ranges.append((cp, cp))
    return "".join(
        re.escape(chr(a)) if a == b else f"{re.escape(chr(a))}-{re.escape(chr(b))}"
        for a, b in ranges
    )


TOKEN_RE = re.compile(
    r"[0-9]+(?:\.[0-9]+)?|(?:\w|[" + _combining_mark_class() + r"])+|[^\s]"
)


def _nfc(source: str) -> str:
    """NFC 정규화 — NFC/NFD 표기 차이(예: macOS 저장본)가 토큰을 바꾸지 않게 한다."""
    if unicodedata.is_normalized("NFC", source):
        return source
    return unicodedata.normalize("NFC", source)


# ──────────────────────────────────────────────────────────────────────
# 키워드 세트 (토큰 정규화용)
# ──────────────────────────────────────────────────────────────────────
# Phase 3 전략: 기존 키워드 세트를 그대로 유지하여 **기존 포렌식 보고서와의
# 핑거프린트 호환성**을 보장한다. languages 레지스트리의 per-language 키워드로
# 전환하면 해시값이 달라져 기존 보고서를 재현할 수 없게 되므로 신중해야 한다.
# Per-language keyword data, used only by the opt-in language-aware channel
# (``lang_aware=True``). The DEFAULT normalize path keeps ``_COMMON_KEYWORDS``
# untouched so existing forensic-report fingerprints remain reproducible (see
# note above); switching the default off it would change emitted hashes.
from diffinite.languages import (  # noqa: E402
    all_keywords as _all_keywords,
    get_spec as _get_spec,
)

_COMMON_KEYWORDS = frozenset({
    # 제어 흐름
    "if", "else", "for", "while", "do", "switch", "case", "break",
    "continue", "return", "try", "catch", "finally", "throw", "throws",
    # 선언
    "class", "interface", "enum", "struct", "typedef", "extends",
    "implements", "import", "package", "from", "def", "function",
    "var", "let", "const", "static", "final", "abstract",
    # 타입
    "void", "int", "long", "float", "double", "char", "boolean",
    "bool", "string", "byte", "short",
    # 접근 제어
    "public", "private", "protected", "default",
    # 논리
    "true", "false", "null", "None", "this", "self", "super",
    "new", "delete", "instanceof", "typeof", "sizeof",
    # Python 전용
    "lambda", "yield", "async", "await", "with", "as", "in",
    "not", "and", "or", "is", "pass", "raise", "nonlocal", "global",
})


# ──────────────────────────────────────────────────────────────────────
# 토크나이징
# ──────────────────────────────────────────────────────────────────────
def _is_identifier_start(ch: str) -> bool:
    # Letters, '_' and letter-numbers (category Nl, e.g. 'Ⅻ'): Unicode UAX #31
    # lists Nl among identifier-start characters.
    return ch.isalpha() or ch == "_" or unicodedata.category(ch) == "Nl"


def _normalize_with_keywords(
    raw_tokens: list[str], keywords: frozenset[str], *, fold_case: bool = False
) -> list[str]:
    """정규식 토큰열을 주어진 키워드 세트로 Type-2 정규화한다.

    식별자→``ID``, 10진 숫자열(선택적 ``.소수부`` 포함)→``LIT``, 문자열 구분자→``STR``,
    키워드/연산자는 유지. 16진·지수·접미사 리터럴(``0xFF``, ``1e10``, ``1.5f``)은
    ``LIT`` 다음에 ``ID`` 가 붙는 두 토큰이 된다 — 리터럴 전체 정규화는 ``--lang-aware``.
    ``keywords`` 만 바꿔 끼우면 기본(언어 무관) 정규화와 언어 인식 Tier-1 정규화를
    같은 코드로 처리할 수 있다.
    ``fold_case=True`` 이면(대소문자 무시 언어) 키워드를 소문자로 비교·출력한다.
    """
    result: list[str] = []
    for tok in raw_tokens:
        if fold_case and tok.lower() in keywords:
            result.append(tok.lower())   # 대소문자 무시 언어의 키워드 — 소문자로 통일
        elif tok in keywords:
            result.append(tok)           # 키워드 — 유지
        elif _is_identifier_start(tok[0]):
            result.append("ID")          # 식별자 → ID
        elif tok[0].isdigit():
            result.append("LIT")         # 숫자 → LIT
        elif tok in ('"', "'", '`'):
            result.append("STR")         # 문자열 구분자 → STR
        else:
            result.append(tok)           # 연산자/구두점 — 유지
    return result


# Registry language → Pygments lexer alias, used where a bare-filename lookup
# picks another language. Measured with Pygments 2.20.0: ".r" → REBOL,
# ".pl" → Prolog, ".pm" → Promela, while the registry says R and Perl
# (audit 2026-11-10 #2). Choosing by language keeps the lexer tied to the
# registry entry the rest of the tool uses for that extension.
_PYGMENTS_ALIAS_BY_LANG: dict[str, str] = {
    "R": "r",
    "Perl": "perl",
}

# Registry languages whose keywords are case-insensitive, so ``SELECT`` and
# ``select`` are the same keyword. Sources: ISO/IEC 9075 (SQL key words),
# PHP manual "List of Keywords" (keywords are case-insensitive), WHATWG HTML
# (tag and attribute names are ASCII case-insensitive), CSS Syntax Level 3
# (keywords and property names are ASCII case-insensitive; SCSS/LESS inherit).
_CASE_INSENSITIVE_LANGS: frozenset[str] = frozenset({
    "SQL", "PHP", "HTML", "CSS", "SCSS", "LESS",
})

TIER2_PREFIX = "pygments:"
"""``tokenize_lang_aware`` 의 tier 값이 Tier-2 일 때의 접두사 (뒤에 lexer alias)."""
TIER1_PREFIX = "registry:"
"""``tokenize_lang_aware`` 의 tier 값이 Tier-1 폴백일 때의 접두사 (뒤에 폴백 사유)."""


def pygments_version() -> str | None:
    """설치된 Pygments 버전 (미설치면 ``None``).

    ``--lang-aware`` 지문은 Pygments lexer 가 내는 토큰 타입에 좌우되므로,
    보고서·증거 매니페스트가 이 값을 기록해야 재실행 차이를 설명할 수 있다.
    """
    try:
        import pygments
    except ImportError:
        return None
    return getattr(pygments, "__version__", None)


def _lang_keywords(ext: str | None) -> frozenset[str]:
    """언어 인식 Tier-1 키워드 세트.

    확장자에 등록된 ``LangSpec.keywords`` 를 쓰고, 없으면 전 언어 키워드 합집합
    (``all_keywords()``)으로 폴백한다 — 미지 확장자에 대한 최선의 추정.
    """
    spec = _get_spec(ext) if ext else None
    return spec.keywords if spec is not None else _all_keywords()


def _registry_case_insensitive(ext: str | None) -> bool:
    spec = _get_spec(ext) if ext else None
    return spec is not None and spec.name in _CASE_INSENSITIVE_LANGS


def _tier1(raw_tokens: list[str], ext: str | None) -> list[str]:
    """Tier-1 (레지스트리 키워드) 정규화."""
    return _normalize_with_keywords(
        raw_tokens, _lang_keywords(ext), fold_case=_registry_case_insensitive(ext))


class _LexerErrorToken(ValueError):
    """Pygments 가 ``Token.Error`` 를 냈다 — 이 파일은 렉싱에 실패한 것으로 본다."""


def _pick_lexer(ext: str):
    """확장자에 대한 Pygments lexer — 등록 언어에 별칭이 있으면 그 언어로 고른다.

    Returns:
        ``(lexer, None)`` 또는 ``(None, fallback_reason)``.
    """
    try:
        import pygments.lexers as _lexers
    except ImportError:
        return None, "pygments-not-installed"
    spec = _get_spec(ext)
    alias = _PYGMENTS_ALIAS_BY_LANG.get(spec.name) if spec is not None else None
    try:
        if alias is not None:
            return _lexers.get_lexer_by_name(alias), None
        return _lexers.get_lexer_for_filename("a" + ext), None
    except Exception:  # noqa: BLE001 — no lexer for this ext: expected, silent
        return None, "no-lexer"


def _normalize_lang_aware(source: str, ext: str | None) -> tuple[list[str] | None, str]:
    """언어 인식 Tier-2 정규화: Pygments lexer 토큰 타입으로 분류한다.

    ``Keyword*``(``i32``·``pub``·``fn``·``func``·``fun`` 등 타입/선언 키워드 포함)는
    원문 보존(대소문자 무시 언어는 소문자로 통일), ``Name*``→``ID``, ``Number``→``LIT``,
    연속된 ``String`` 하위 토큰(따옴표·본문·이스케이프)은 **하나의** ``STR``
    (docstring 포함; 보간식 안의 이름 등 다른 토큰이 끼면 거기서 끊긴다),
    주석은 ``--strip-comments`` 설정과 무관하게 **항상 폐기**.
    ``Text``/``Other``/``Generic`` 덩어리(예: ``.txt``·``.html`` 본문)는 통째로 한 토큰이
    되지 않도록 Tier-1 토크나이저·정규화(언어 키워드 세트)를 거친다.

    lexer 는 레지스트리 언어로 고른다(``_PYGMENTS_ALIAS_BY_LANG``) — 파일 이름만으로
    고르면 ``.r``/``.pl``/``.pm`` 이 다른 언어의 lexer 로 간다.

    Returns:
        ``(tokens, tier)``. Tier-2 성공이면 ``tier`` 는 ``"pygments:<alias>"``.
        ``ext`` 가 없거나, Pygments/lexer 가 없거나, lexer 가 ``Token.Error`` 를 내거나
        렉싱 중 예외가 나면 ``(None, "registry:<사유>")`` — 호출쪽이 Tier-1 로 폴백한다.
        lexer 가 존재하는데 실패한 경우는 경고 로그도 남긴다(같은 확장자의 다른
        파일과 토큰 알파벳이 달라지므로).
    """
    if not ext:
        return None, TIER1_PREFIX + "no-extension"
    lexer, reason = _pick_lexer(ext)
    if lexer is None:
        return None, TIER1_PREFIX + str(reason)
    try:
        from pygments.token import Token
    except ImportError:
        return None, TIER1_PREFIX + "pygments-not-installed"

    spec = _get_spec(ext)
    if spec is not None:
        fold_case = spec.name in _CASE_INSENSITIVE_LANGS
    else:
        # Unregistered extension: the lexer's own regex flags say whether its
        # author treated the language's keywords as case-insensitive.
        fold_case = bool(getattr(lexer, "flags", 0) & re.IGNORECASE)
    aliases = getattr(lexer, "aliases", None) or [type(lexer).__name__]
    tier = TIER2_PREFIX + aliases[0]

    out: list[str] = []
    tier1_keywords = _lang_keywords(ext)
    in_str = False
    try:
        for tok_type, val in lexer.get_tokens(source):
            s = val.strip()
            if not s:
                continue                     # 공백/개행 (문자열 연속 상태 유지)
            if tok_type in Token.Comment:
                continue                     # 주석 폐기 (입력이 미정제여도 안전)
            if tok_type in Token.Error:
                # Error tokens mean the lexer could not lex this text (e.g. the
                # Kotlin/C#/Ruby lexers on Hangul identifiers); keeping them raw
                # would silently skip normalization for the rest of the line.
                raise _LexerErrorToken(s)
            if tok_type in Token.Literal.String:
                if not in_str:
                    out.append("STR")        # 연속 문자열 하위 토큰 → STR 하나
                in_str = True
                continue
            in_str = False
            if tok_type in Token.Keyword:
                out.append(s.lower() if fold_case else s)  # 키워드 — 유지
            elif tok_type in Token.Name:
                out.append("ID")             # 식별자/함수명 → ID
            elif tok_type in Token.Literal.Number:
                out.append("LIT")            # 숫자 리터럴 → LIT
            elif (tok_type in Token.Text or tok_type in Token.Other
                  or tok_type in Token.Generic):
                # 분류되지 않은 텍스트 덩어리 — 한 토큰으로 붙이면 파일이 K 미만
                # 토큰으로 뭉개져 지문이 0개가 된다. Tier-1 로 쪼개 정규화한다.
                out.extend(_normalize_with_keywords(
                    TOKEN_RE.findall(s), tier1_keywords, fold_case=fold_case))
            else:
                out.append(s)                # 연산자/구두점/기타 — 유지
    except Exception as exc:  # noqa: BLE001 — lexer EXISTS but failed mid-stream
        # This file falls back to Tier-1 while its same-extension siblings may use
        # Tier-2 — a different token alphabet, risking a silent false negative. A
        # forensic run must not abort, but the inconsistency must be observable:
        # it is logged here and returned as the tier for the caller to record.
        reason = "lexer-error-token" if isinstance(exc, _LexerErrorToken) else "lexer-exception"
        logger.warning(
            "--lang-aware lexing failed for extension %r (%s); this file uses the "
            "registry keyword fallback, whose tokens differ from lexed files", ext, reason)
        return None, TIER1_PREFIX + reason
    return out, tier


def tokenize_lang_aware(source: str, ext: str | None) -> tuple[list[str], str]:
    """``--lang-aware`` 정규화 토큰과, 실제로 쓰인 tier 를 함께 돌려준다.

    Returns:
        ``(tokens, tier)`` — ``tier`` 는 ``"pygments:<lexer alias>"`` (Tier-2) 또는
        ``"registry:<폴백 사유>"`` (Tier-1). 호출쪽(Deep Compare)이 파일별로 어떤
        tier 가 쓰였는지 보고서에 기록할 수 있게 한다.
    """
    source = _nfc(source)
    tier2, tier = _normalize_lang_aware(source, ext)
    if tier2 is not None:
        return tier2, tier
    return _tier1(TOKEN_RE.findall(source), ext), tier


def tokenize(
    source: str,
    *,
    normalize: bool = False,
    ext: str | None = None,
    lang_aware: bool = False,
) -> list[str]:
    """소스코드를 토큰 시퀀스로 분할한다.

    입력은 먼저 NFC 로 정규화된다(NFC/NFD 표기만 다른 같은 식별자가 같은 토큰).

    ``normalize=False`` (기본):
        원문 토큰 그대로 반환. raw_winnowing 채널에 사용. ``lang_aware`` 는 무시된다
        (원문 토큰은 본래 언어 무관).

    ``normalize=True``:
        Type-2 클론 탐지용 정규화:
        - 식별자 → ``"ID"`` (변수명 변경 무력화)
        - 10진 숫자열(선택적 ``.소수부``) → ``"LIT"`` — ``0xFF``·``1e10``·``1.5f`` 같은
          16진·지수·접미사 리터럴은 ``"LIT"`` + ``"ID"`` 두 토큰이 된다
          (리터럴 전체 정규화는 ``lang_aware=True`` 의 Tier-2 경로)
        - 문자열 **구분자**(따옴표) → ``"STR"``
        - 키워드/연산자 → 원문 보존

    ``lang_aware=True`` (``normalize`` 와 함께일 때만 의미 있음):
        하드코딩된 ``_COMMON_KEYWORDS`` 대신 **언어별** 키워드 인식을 쓴다.
        Tier-2(Pygments lexer)를 우선 시도하고, 해당 ``ext`` 의 lexer가 없거나 lexer 가
        ``Token.Error`` 를 내면 Tier-1(레지스트리 ``LangSpec.keywords``)로 폴백한다.
        **opt-in 전용**이며 기본 경로의 핑거프린트는 바뀌지 않는다.
        Tier-2 는 ``--strip-comments`` 와 무관하게 lexer 주석 토큰을 **항상 버리고**,
        연속된 문자열 리터럴(docstring 포함)을 ``STR`` 하나로 접는다. 대소문자 무시
        언어(SQL·PHP·HTML·CSS 계열)는 두 tier 모두 키워드를 소문자로 통일한다.
        사용된 tier 가 필요하면 :func:`tokenize_lang_aware` 를 쓴다.

    주의:
        문자열 **내용**은 정규화하지 않는다 — 따옴표만 ``STR``로 바뀌고 그 사이
        문자는 일반 식별자/리터럴로 토큰화된다. 따라서 문자열 값만 바뀐 클론은
        정규화 후에도 서로 다른 핑거프린트를 가질 수 있다(식별자 변경에는 둔감).

        기본 경로(및 Tier-1 폴백)는 주석을 여기서 제거하지 않는다. 입력에 남은 주석은
        코드처럼 지문에 포함되므로, 제외하려면 ``parser.strip_comments()``를 먼저
        호출할 것. 단 ``lang_aware=True`` 의 Tier-2 경로는 주석을 항상 버린다.
    """
    if normalize and lang_aware:
        return tokenize_lang_aware(source, ext)[0]

    raw_tokens = TOKEN_RE.findall(_nfc(source))
    if not normalize:
        return raw_tokens
    return _normalize_with_keywords(raw_tokens, _COMMON_KEYWORDS)


# ──────────────────────────────────────────────────────────────────────
# 롤링 해시 (Rabin fingerprint)
# ──────────────────────────────────────────────────────────────────────
def rolling_hash(tokens: Sequence[str], k: int = DEFAULT_K) -> list[int]:
    """토큰 시퀀스에 대해 Rabin 롤링 해시를 계산한다.

    각 K-gram (크기 k의 연속 토큰 부분열)에 대해 하나의 해시를 생성.
    ``O(n)`` — 슬라이딩 윈도우로 이전 해시에서 점진적 계산.

    Returns:
        길이 = ``len(tokens) - k + 1`` 의 해시 리스트.
        ``len(tokens) < k`` 이면 빈 리스트.
    """
    n = len(tokens)
    if n < k:
        return []

    hashes: list[int] = []
    h: int = 0
    # BASE^(k-1) mod MOD — 가장 오래된 토큰 제거 시 사용
    base_pow = pow(HASH_BASE, k - 1, HASH_MOD)

    # 첫 번째 윈도우 시드
    for i in range(k):
        th = _fnv1a_64(tokens[i])
        h = (h * HASH_BASE + th) % HASH_MOD
    hashes.append(h)

    # 롤링: 가장 오래된 토큰 제거 + 새 토큰 추가
    for i in range(k, n):
        old_th = _fnv1a_64(tokens[i - k])
        new_th = _fnv1a_64(tokens[i])
        h = ((h - old_th * base_pow) * HASH_BASE + new_th) % HASH_MOD
        hashes.append(h)

    return hashes


# ──────────────────────────────────────────────────────────────────────
# Winnowing 알고리즘
# ──────────────────────────────────────────────────────────────────────
def winnow(
    hash_values: list[int],
    w: int = DEFAULT_W,
) -> list[FingerprintEntry]:
    """해시 스트림에서 대표 핑거프린트를 선택한다.

    각 슬라이딩 윈도우(크기 w) 내에서 **최소 해시**를 선택.
    동점 시 **가장 오른쪽** 값을 선택하여 전방 진행을 유도한다.
    연속 중복 선택은 억제(deduplicate).

    이 알고리즘이 밀도 보장을 제공하는 핵심 메커니즘이다:
    ``w`` 크기의 모든 윈도우에서 반드시 1개 이상의 핑거프린트가 선택되므로,
    ``w + k - 1`` 토큰 이상의 공유 부분열은 반드시 공통 핑거프린트를 갖는다.

    Returns:
        중복 제거된 ``FingerprintEntry`` 리스트.
    """
    n = len(hash_values)
    if n == 0:
        return []
    if n <= w:
        # 윈도우 1개 — 전체에서 최소값 선택
        min_val = min(hash_values)
        min_pos = len(hash_values) - 1 - hash_values[::-1].index(min_val)
        return [FingerprintEntry(hash_value=min_val, position=min_pos)]

    fingerprints: list[FingerprintEntry] = []
    prev_pos = -1  # 중복 억제용 이전 선택 위치

    for start in range(n - w + 1):
        window = hash_values[start: start + w]
        min_val = min(window)
        # 가장 오른쪽 최소값 위치 (reversed index 트릭)
        local_pos = w - 1 - window[::-1].index(min_val)
        global_pos = start + local_pos

        if global_pos != prev_pos:
            fingerprints.append(
                FingerprintEntry(hash_value=min_val, position=global_pos)
            )
            prev_pos = global_pos

    return fingerprints


def extract_fingerprints(
    source: str,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    *,
    normalize: bool = False,
    ext: str | None = None,
    lang_aware: bool = False,
) -> list[FingerprintEntry]:
    """소스코드에서 핑거프린트를 추출하는 통합 API.

    ``tokenize → rolling_hash → winnow`` 파이프라인을 실행한다.

    Args:
        source: 소스코드 (주석 제거 여부는 호출자가 결정한다).
        k: K-gram 크기 (>= 1).
        w: Winnowing 윈도우 크기 (>= 1).
        normalize: True이면 Type-2 클론 탐지용 토큰 정규화 적용.
        ext: 파일 확장자(예: ``".rs"``). ``lang_aware`` 정규화의 lexer/키워드
            선택에 사용. ``lang_aware=False`` 이면 무시된다.
        lang_aware: True이면 언어 인식 정규화(Tier-2 Pygments → Tier-1 레지스트리
            폴백)를 적용한다. **opt-in**: 기본 경로의 핑거프린트는 불변.

    Raises:
        ValueError: ``k`` 또는 ``w`` 가 1 미만일 때. (k=0은 모듈러 역원으로 인해
            모든 파일을 동일 핑거프린트로 만들어 유사도를 조작하므로 조용히
            통과시키지 않는다.)
    """
    return extract_fingerprints_with_tier(
        source, k, w, normalize=normalize, ext=ext, lang_aware=lang_aware)[0]


def extract_fingerprints_with_tier(
    source: str,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    *,
    normalize: bool = False,
    ext: str | None = None,
    lang_aware: bool = False,
) -> tuple[list[FingerprintEntry], str | None]:
    """:func:`extract_fingerprints` 와 같되, ``--lang-aware`` 에서 실제로 쓰인 tier
    (``"pygments:<alias>"`` 또는 ``"registry:<사유>"``)도 돌려준다.
    ``normalize and lang_aware`` 가 아니면 tier 는 ``None``.
    """
    if k < 1:
        raise ValueError(f"k-gram size must be >= 1, got {k}")
    if w < 1:
        raise ValueError(f"winnowing window must be >= 1, got {w}")

    tier: str | None = None
    if normalize and lang_aware:
        tokens, tier = tokenize_lang_aware(source, ext)
    else:
        tokens = tokenize(source, normalize=normalize)
    hashes = rolling_hash(tokens, k)
    return winnow(hashes, w), tier
