"""Diffinite 유사도 메트릭.

Winnowing 핑거프린트 기반 Jaccard 유사도를 계산한다.

이 모듈은 "얼마나 비슷한가"만 계산한다.
"어떤 유형의 복제인가"는 판단하지 않는다 (감정인의 몫).
"""

from __future__ import annotations


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
