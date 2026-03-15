"""Winnowing 핑거프린트 추출 엔진.

Stanford MOSS 스타일 문서 핑거프린팅 파이프라인을 구현한다.
전체 흐름: Tokenize → K-gram → Rolling Hash → Winnow → Fingerprint Set

핵심 보장:
    **밀도 보장 (Density Guarantee)** — 두 문서가 ≥ (W + K − 1) 토큰의
    공통 부분 문자열을 공유하면, 반드시 1개 이상의 공통 핑거프린트가 생성된다.
    현재 설정(K=5, W=4)에서 ≥ 8 토큰 공유 시 탐지 보장.

참조:
    Schleimer, Wilkerson, Aiken. "Winnowing: Local Algorithms for Document
    Fingerprinting". SIGMOD 2003.

의존:
    - ``models.FingerprintEntry``: 핑거프린트 결과 VO
    - ``languages/``: 키워드 세트 (토큰 정규화용)
    - ``ast_normalizer``: AST/PDG 모드에서 lazy import

호출관계:
    ``deep_compare._extract_one()`` / ``_extract_multi()`` → ``extract_fingerprints()``
    ``extract_fingerprints()`` → ``tokenize()`` → ``rolling_hash()`` → ``winnow()``
"""

from __future__ import annotations

import re
from typing import Sequence

from diffinite.models import FingerprintEntry

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

# 토크나이저 정규식 — 식별자, 숫자, 개별 구두점을 각각 토큰으로 분리.
# 공백은 버린다. ``_TOKEN_RE``는 evidence.py에서도 참조됨.
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|[0-9]+(?:\.[0-9]+)?|[^\s]")


# ──────────────────────────────────────────────────────────────────────
# 키워드 세트 (토큰 정규화용)
# ──────────────────────────────────────────────────────────────────────
# Phase 3 전략: 기존 키워드 세트를 그대로 유지하여 **기존 포렌식 보고서와의
# 핑거프린트 호환성**을 보장한다. languages 레지스트리의 per-language 키워드로
# 전환하면 해시값이 달라져 기존 보고서를 재현할 수 없게 되므로 신중해야 한다.
from diffinite.languages import all_keywords as _all_keywords  # noqa: E402

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
def tokenize(source: str, *, normalize: bool = False) -> list[str]:
    """소스코드를 토큰 시퀀스로 분할한다.

    ``normalize=False`` (기본):
        원문 토큰 그대로 반환. raw_winnowing 채널에 사용.

    ``normalize=True``:
        Type-2 클론 탐지용 정규화:
        - 식별자 → ``"ID"`` (변수명 변경 무력화)
        - 숫자 리터럴 → ``"LIT"``
        - 문자열 구분자 → ``"STR"``
        - 키워드/연산자 → 원문 보존

    주의:
        입력 ``source``는 이미 주석이 제거된 텍스트여야 한다.
        ``parser.strip_comments()``를 먼저 호출할 것.
    """
    raw_tokens = _TOKEN_RE.findall(source)
    if not normalize:
        return raw_tokens

    result: list[str] = []
    for tok in raw_tokens:
        if tok in _COMMON_KEYWORDS:
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
        th = hash(tokens[i]) & 0x7FFFFFFFFFFFFFFF  # 양수 보장
        h = (h * HASH_BASE + th) % HASH_MOD
    hashes.append(h)

    # 롤링: 가장 오래된 토큰 제거 + 새 토큰 추가
    for i in range(k, n):
        old_th = hash(tokens[i - k]) & 0x7FFFFFFFFFFFFFFF
        new_th = hash(tokens[i]) & 0x7FFFFFFFFFFFFFFF
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


# Java import/package 문 제거 정규식
_IMPORT_RE = re.compile(r"^(import|package)\s+.*;\s*$", re.MULTILINE)


def extract_fingerprints(
    source: str,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    *,
    normalize: bool = False,
    mode: str = "token",
    extension: str = "",
    filter_imports: bool = False,
) -> list[FingerprintEntry]:
    """소스코드에서 핑거프린트를 추출하는 통합 API.

    내부적으로 ``tokenize → rolling_hash → winnow`` 파이프라인을 실행하되,
    ``mode``에 따라 토크나이저를 전환한다:

    - ``"token"``: Phase 1 flat 토큰 정규화 (기본). 빠르고 안정적.
    - ``"ast"``: Phase 2 tree-sitter AST 선형화. 구조 정보 보존.
    - ``"pdg"``: Phase 4 PDG 정규화. dead code 필터 + 의존성 재정렬.

    AST/PDG 실패 시 자동으로 token 모드로 폴백한다.
    tree-sitter 미설치 환경에서도 안전하게 동작.

    Args:
        filter_imports: True이면 Java import/package 문 제거.
                        공유 import로 인한 위양성(FP)을 줄이는 데 유효.
    """
    if filter_imports:
        source = _IMPORT_RE.sub("", source)

    tokens: list[str] | None = None

    # AST/PDG 모드: tree-sitter 기반 토크나이징 시도
    if mode in ("ast", "pdg"):
        try:
            from diffinite.ast_normalizer import ast_tokenize, pdg_tokenize

            if mode == "pdg":
                tokens = pdg_tokenize(source, extension)
            if tokens is None:
                tokens = ast_tokenize(source, extension)
        except ImportError:
            pass  # tree-sitter 미설치 → token 모드 폴백

    # 폴백: Phase 1 flat 토큰 정규화
    if tokens is None:
        tokens = tokenize(source, normalize=normalize)

    hashes = rolling_hash(tokens, k)
    return winnow(hashes, w)
