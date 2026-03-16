"""Diffinite 유사도 메트릭.

두 파일의 유사도를 계산하는 함수 2개를 제공한다:
- jaccard_similarity: Winnowing 핑거프린트 기반 (Schleimer 2003)
- identifier_cosine: 식별자 빈도 벡터 코사인 유사도

이 모듈은 "얼마나 비슷한가"만 계산한다.
"어떤 유형의 복제인가"는 판단하지 않는다 (감정인의 몫).

의존:
    - ``fingerprint.py``: ``_COMMON_KEYWORDS``, ``TOKEN_RE``
"""

from __future__ import annotations

import math
from collections import Counter

from diffinite.fingerprint import _COMMON_KEYWORDS, TOKEN_RE

# ── 식별자 필터링 (scènes à faire 제거) ──────────────────────────────

# Java 표준 타입명 — scènes à faire(필수적 표현) 원칙에 따라
# 유사도 계산에서 제외. 모든 Java 코드에 등장하는 필수 타입이므로
# 유사도를 부풀리지만 저작물 고유 표현을 나타내지 않는다.
_JAVA_TYPE_STOPWORDS = frozenset({
    "String", "Object", "Integer", "Long", "Double", "Float",
    "Boolean", "Character", "Byte", "Short", "Number",
    "Void", "Class", "Comparable", "Iterable", "Iterator",
    "Serializable", "Cloneable", "Exception", "Throwable",
    "Override", "Deprecated", "SuppressWarnings",
})

# Java/Kotlin/Scala/Groovy 확장자 — 타입명 필터링 적용 범위 제한.
_JAVA_FAMILY_EXTS = frozenset({".java", ".kt", ".scala", ".groovy"})


def _is_noise_identifier(token: str, extension: str = ".java") -> bool:
    """노이즈 식별자 판별.

    단일 문자 변수(i, j, k, T, V 등)와 Java 표준 타입명은
    유사도에 기여하지만 SSO를 나타내지 않으므로 제외한다.
    """
    if len(token) == 1:
        return True
    if extension in _JAVA_FAMILY_EXTS and token in _JAVA_TYPE_STOPWORDS:
        return True
    return False


def _extract_identifiers(source: str, extension: str = ".java") -> list[str]:
    """소스코드에서 식별자 토큰을 추출한다.

    언어 키워드, 단일 문자 변수, Java 표준 타입명을 필터링하여
    저작물 고유 식별자만 반환한다.

    Args:
        source: 주석 제거된 소스코드.
        extension: 언어별 필터링용 파일 확장자.

    Returns:
        식별자 문자열 리스트.
    """
    tokens = TOKEN_RE.findall(source)
    return [
        t for t in tokens
        if t not in _COMMON_KEYWORDS
        and (t[0].isalpha() or t[0] == '_')
        and not _is_noise_identifier(t, extension)
    ]


# ── 공개 API ─────────────────────────────────────────────────────────

def jaccard_similarity(fp_a: set[int], fp_b: set[int]) -> float:
    """Winnowing 핑거프린트 Jaccard 유사도. |A∩B| / |A∪B|.

    "두 파일의 코드 지문 중 N%가 일치합니다" 형태로 보고서에 표시.
    양쪽 모두 빈 집합이면 0.0 반환.
    """
    if not fp_a and not fp_b:
        return 0.0
    intersection = len(fp_a & fp_b)
    union = len(fp_a | fp_b)
    return intersection / union if union else 0.0


def identifier_cosine(
    source_a: str, source_b: str,
    extension: str = ".java",
) -> float:
    """식별자 빈도 벡터의 코사인 유사도.

    높은 점수: 동일 변수/함수명을 유사 비율로 사용 — 복사 증거.
    낮은 점수 + 높은 Jaccard: 의도적 식별자 변경(Type-2 클론) 시사.

    Args:
        source_a: 주석 제거된 소스 A.
        source_b: 주석 제거된 소스 B.
        extension: 언어별 필터링용 파일 확장자.

    Returns:
        코사인 유사도 ∈ [0.0, 1.0].
    """
    ids_a = Counter(_extract_identifiers(source_a, extension))
    ids_b = Counter(_extract_identifiers(source_b, extension))

    if not ids_a or not ids_b:
        return 0.0

    all_keys = set(ids_a) | set(ids_b)
    dot = sum(ids_a.get(k, 0) * ids_b.get(k, 0) for k in all_keys)
    mag_a = math.sqrt(sum(v * v for v in ids_a.values()))
    mag_b = math.sqrt(sum(v * v for v in ids_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def compute_similarity(
    fp_a: set[int], fp_b: set[int],
    source_a: str, source_b: str,
    extension: str = ".java",
) -> dict[str, float]:
    """두 파일의 유사도를 Jaccard + identifier cosine으로 계산한다.

    Args:
        fp_a: 파일 A의 Winnowing 핑거프린트 해시 집합.
        fp_b: 파일 B의 Winnowing 핑거프린트 해시 집합.
        source_a: 주석 제거된 소스 A.
        source_b: 주석 제거된 소스 B.
        extension: 파일 확장자 (언어별 필터링).

    Returns:
        {"jaccard": 0.73, "identifier_cosine": 0.65}
    """
    return {
        "jaccard": jaccard_similarity(fp_a, fp_b),
        "identifier_cosine": identifier_cosine(source_a, source_b, extension),
    }
