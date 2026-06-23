"""Winnowing fingerprint extraction engine.

Implements a Stanford MOSS–style document-fingerprinting pipeline.
Flow: Tokenize → K-gram → Rolling Hash → Winnow → Fingerprint Set

Core guarantee:
    **Density guarantee** -- if two documents share a common substring of
    >= (W + K - 1) tokens, at least one common fingerprint is produced.
    With the current settings (K=5, W=4), any shared run of >= 8 tokens is
    guaranteed to be detected.

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
from typing import Sequence

from diffinite.models import FingerprintEntry

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# 핵심 상수
# ──────────────────────────────────────────────────────────────────────
DEFAULT_K: int = 5
"""K-gram 크기. grid search(SQLite 250K-line, AOSP Java)에서 최적값 도출.
K=5: Jaccard 0.9904, 최고 속도, line-level ratio 대비 gap < 12pp.
K↑ = 정밀도↑ 재현율↓ (긴 공유 시퀀스만 탐지), K↓ = 재현율↑ 정밀도↓ (노이즈 증가)."""

DEFAULT_W: int = 4
"""Winnowing 윈도우 크기. W=4 → 밀도 보장 길이 = W+K-1 = 8 토큰.
W↑ = 핑거프린트 수↓ (속도↑ 정밀도↓), W↓ = 핑거프린트 수↑ (속도↓ 정밀도↑)."""

HASH_BASE: int = 257
"""Rabin 다항식 해시의 밑(base). 소수 사용으로 분포 균일성 확보."""

HASH_MOD: int = (1 << 61) - 1
"""해시 모듈러. Mersenne 소수 2^61-1 사용 — Python의 `pow(base, exp, mod)`로
효율적 모듈러 지수 연산 가능. 충돌 확률 ≈ 1/2^61."""

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
TOKEN_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?|\w+|[^\s]")


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
def _normalize_with_keywords(
    raw_tokens: list[str], keywords: frozenset[str]
) -> list[str]:
    """정규식 토큰열을 주어진 키워드 세트로 Type-2 정규화한다.

    식별자→``ID``, 숫자→``LIT``, 문자열 구분자→``STR``, 키워드/연산자는 유지.
    ``keywords`` 만 바꿔 끼우면 기본(언어 무관) 정규화와 언어 인식 Tier-1 정규화를
    같은 코드로 처리할 수 있다.
    """
    result: list[str] = []
    for tok in raw_tokens:
        if tok in keywords:
            result.append(tok)           # 키워드 — 유지
        elif tok[0].isalpha() or tok[0] == '_':
            result.append("ID")          # 식별자 → ID
        elif tok[0].isdigit():
            result.append("LIT")         # 숫자 → LIT
        elif tok in ('"', "'", '`'):
            result.append("STR")         # 문자열 구분자 → STR
        else:
            result.append(tok)           # 연산자/구두점 — 유지
    return result


def _lang_keywords(ext: str | None) -> frozenset[str]:
    """언어 인식 Tier-1 키워드 세트.

    확장자에 등록된 ``LangSpec.keywords`` 를 쓰고, 없으면 전 언어 키워드 합집합
    (``all_keywords()``)으로 폴백한다 — 미지 확장자에 대한 최선의 추정.
    """
    spec = _get_spec(ext) if ext else None
    return spec.keywords if spec is not None else _all_keywords()


def _normalize_lang_aware(source: str, ext: str | None) -> list[str] | None:
    """언어 인식 Tier-2 정규화: Pygments lexer 토큰 타입으로 분류한다.

    ``Keyword*``(``i32``·``pub``·``fn``·``func``·``fun`` 등 타입/선언 키워드 포함)는
    원문 보존, ``Name*``→``ID``, ``Number``→``LIT``, ``String``→``STR``, 주석은 폐기.
    이로써 함수 선언이 식별자와 구분되어, 비-JVM/Python/JS 언어의 위양성을 줄인다.

    ``ext`` 가 없거나, Pygments lexer를 찾지 못하거나, 렉싱 중 어떤 예외라도 나면
    ``None`` 을 반환하여 호출쪽이 Tier-1(레지스트리 키워드)로 폴백하게 한다 —
    포렌식 실행이 파일 하나의 렉서 오류로 중단되지 않도록.
    """
    if not ext:
        return None
    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.token import Token
    except ImportError:
        return None
    try:
        lexer = get_lexer_for_filename("a" + ext)
    except Exception:  # noqa: BLE001 — no lexer for this ext: expected, silent
        return None                          # → Tier-1 (registry keywords)

    out: list[str] = []
    try:
        for tok_type, val in lexer.get_tokens(source):
            s = val.strip()
            if not s:
                continue                     # 공백/개행
            if tok_type in Token.Comment:
                continue                     # 주석 폐기 (입력이 미정제여도 안전)
            if tok_type in Token.Keyword:
                out.append(s)                # 키워드(타입·선언 포함) — 유지
            elif tok_type in Token.Name:
                out.append("ID")             # 식별자/함수명 → ID
            elif tok_type in Token.Literal.Number:
                out.append("LIT")            # 숫자 리터럴 → LIT
            elif tok_type in Token.Literal.String:
                out.append("STR")            # 문자열 리터럴 → STR
            else:
                out.append(s)                # 연산자/구두점/기타 — 유지
    except Exception:  # noqa: BLE001 — lexer EXISTS but failed mid-stream
        # This file falls back to Tier-1 while its same-extension siblings may use
        # Tier-2 — a different token alphabet, risking a silent false negative. A
        # forensic run must not abort, but the inconsistency must be observable.
        logger.warning(
            "lang-aware lexing failed for extension %r; this file uses the Tier-1 "
            "fallback (different token alphabet than lexed files)", ext)
        return None
    return out


def tokenize(
    source: str,
    *,
    normalize: bool = False,
    ext: str | None = None,
    lang_aware: bool = False,
) -> list[str]:
    """소스코드를 토큰 시퀀스로 분할한다.

    ``normalize=False`` (기본):
        원문 토큰 그대로 반환. raw_winnowing 채널에 사용. ``lang_aware`` 는 무시된다
        (원문 토큰은 본래 언어 무관).

    ``normalize=True``:
        Type-2 클론 탐지용 정규화:
        - 식별자 → ``"ID"`` (변수명 변경 무력화)
        - 숫자 리터럴 → ``"LIT"``
        - 문자열 **구분자**(따옴표) → ``"STR"``
        - 키워드/연산자 → 원문 보존

    ``lang_aware=True`` (``normalize`` 와 함께일 때만 의미 있음):
        하드코딩된 ``_COMMON_KEYWORDS`` 대신 **언어별** 키워드 인식을 쓴다.
        Tier-2(Pygments lexer)를 우선 시도하고, 해당 ``ext`` 의 lexer가 없으면
        Tier-1(레지스트리 ``LangSpec.keywords``)로 폴백한다. **opt-in 전용**이며
        기본 경로의 핑거프린트(기존 보고서 재현성)는 바뀌지 않는다.

    주의:
        문자열 **내용**은 정규화하지 않는다 — 따옴표만 ``STR``로 바뀌고 그 사이
        문자는 일반 식별자/리터럴로 토큰화된다. 따라서 문자열 값만 바뀐 클론은
        정규화 후에도 서로 다른 핑거프린트를 가질 수 있다(식별자 변경에는 둔감).

        입력 ``source``는 이미 주석이 제거된 텍스트여야 한다.
        ``parser.strip_comments()``를 먼저 호출할 것.
    """
    raw_tokens = TOKEN_RE.findall(source)
    if not normalize:
        return raw_tokens

    if lang_aware:
        tier2 = _normalize_lang_aware(source, ext)
        if tier2 is not None:
            return tier2
        return _normalize_with_keywords(raw_tokens, _lang_keywords(ext))

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
        source: 주석 제거된 소스코드.
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
    if k < 1:
        raise ValueError(f"k-gram size must be >= 1, got {k}")
    if w < 1:
        raise ValueError(f"winnowing window must be >= 1, got {w}")

    tokens = tokenize(source, normalize=normalize, ext=ext, lang_aware=lang_aware)
    hashes = rolling_hash(tokens, k)
    return winnow(hashes, w)
