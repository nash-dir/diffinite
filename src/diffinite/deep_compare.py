"""N:M Deep 크로스매칭 엔진.

Winnowing 핑거프린트의 **역 인덱스(Inverted Index)** 를 활용하여,
코드가 여러 파일로 분산·병합된 경우에도 유사 코드를 효율적으로 탐지한다.

아키텍처:
    1. ``ProcessPoolExecutor``로 모든 파일의 핑거프린트를 **병렬 추출**.
    2. B-파일의 해시값으로 역 인덱스 구축: ``hash → {file_ids}``.
    3. A-파일별로 인덱스 조회 → 후보 B-파일 결정 → Jaccard 계산.

복잡도:
    - 핑거프린트 추출: O((N+M) × L) — L = 평균 파일 길이, 병렬화로 wall time ↓
    - 역 인덱스 구축: O(Σ|fp_b|)
    - A-파일별 조회: O(|fp_a|) — 나이브 O(N×M) 대비 극적 개선
    - 전체: O((N+M)×L + Σ|fp_a|) ≈ 선형

병렬화 제약:
    워커 함수(``_extract_one``)는 모듈 최상위에 정의해야 한다.
    ``ProcessPoolExecutor``가 pickle로 함수를 직렬화하기 때문.
    클래스 메서드나 람다를 사용하면 ``PicklingError`` 발생.

의존:
    - ``fingerprint.py``: 핑거프린트 추출 파이프라인
    - ``parser.py``: 주석 제거
    - ``differ.py``: 파일 읽기 (인코딩 감지)

호출관계:
    ``pipeline.run_pipeline()`` → ``run_deep_compare()``
"""

from __future__ import annotations

import logging
import multiprocessing
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

from diffinite.differ import read_file
from diffinite.fingerprint import (
    DEFAULT_K,
    DEFAULT_W,
    extract_fingerprints,
)
from diffinite.models import DeepMatchResult
from diffinite.parser import strip_comments

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 워커 함수 (ProcessPoolExecutor 직렬화를 위해 모듈 최상위 정의 필수)
# ──────────────────────────────────────────────────────────────────────
def _extract_one(args: tuple) -> tuple[str, set[int], int]:
    """단일 파일의 핑거프린트를 추출한다.

    Args:
        args: ``(abs_path, rel_path, extension, k, w, normalize)``
              — tuple 포장은 ``pool.map()`` 인터페이스 제약.

    Returns:
        ``(rel_path, hash_set, fingerprint_count)``
        읽기 실패 시 빈 set / count=0 반환.
    """
    abs_path, rel_path, extension, k, w, normalize = args
    text = read_file(abs_path)
    if text is None:
        return rel_path, set(), 0

    cleaned = strip_comments(text, extension)
    fps = extract_fingerprints(
        cleaned, k=k, w=w, normalize=normalize,
    )
    hash_set = {fp.hash_value for fp in fps}
    return rel_path, hash_set, len(fps)


# ──────────────────────────────────────────────────────────────────────
# 역 인덱스 (Information Retrieval 표준 기법)
# ──────────────────────────────────────────────────────────────────────
def build_inverted_index(
    fp_map: dict[str, set[int]],
    max_entries: int = 10_000_000,
) -> dict[int, set[str]]:
    """해시값 → 파일 ID 집합의 역 인덱스를 구축한다.

    이 인덱스 덕분에 A-파일의 각 해시를 O(1)로 조회하여
    공유 해시를 가진 B-파일을 즉시 찾을 수 있다.
    나이브 쌍-단위 비교 O(N×M) 대비 O(Σ|fp_a|)로 단축.

    메모리: O(Σ|fp_b|) — 대규모 코퍼스에서 수 GB 가능.
    ``max_entries`` 초과 시 경고 로그 출력 후 truncated index 반환.
    ``--max-index-entries`` CLI 옵션으로 제어 가능.
    """
    index: dict[int, set[str]] = defaultdict(set)
    entry_count = 0
    for file_id, hashes in fp_map.items():
        for h in hashes:
            index[h].add(file_id)
            entry_count += 1
            if entry_count >= max_entries:
                logger.warning(
                    "Inverted index truncated at %d entries "
                    "(--max-index-entries). Some matches may be missed.",
                    max_entries,
                )
                return index
    return index


# ──────────────────────────────────────────────────────────────────────
# Jaccard 유사도 & N:M 매칭
# ──────────────────────────────────────────────────────────────────────
def _jaccard(set_a: set[int], set_b: set[int]) -> float:
    """두 해시 집합의 Jaccard 유사도 계수. |A∩B| / |A∪B|.
    양쪽 모두 빈 집합이면 0.0 반환."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def run_deep_compare(
    dir_a: str,
    dir_b: str,
    files_a: list[str],
    files_b: list[str],
    *,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    workers: int = 4,
    min_jaccard: float = 0.05,
    normalize: bool = False,
    max_index_entries: int = 10_000_000,
) -> list[DeepMatchResult]:
    """Execute N:M cross-matching between two directories.

    1. Parallel fingerprint extraction for all files.
    2. Build inverted index over B-files.
    3. For each A-file, query the index to find matching B-files.
    4. Compute Jaccard similarity and filter by *min_jaccard*.

    Args:
        dir_a / dir_b: Root directory paths.
        files_a / files_b: Relative paths collected via :func:`collector.collect_files`.
        k: K-gram size.
        w: Winnowing window size.
        workers: Number of parallel worker processes.
        min_jaccard: Minimum Jaccard similarity to include in results.
        normalize: If *True*, normalise tokens before fingerprinting.

    Returns:
        List of :class:`DeepMatchResult` for every A-file that has at
        least one B-file match above the threshold.
    """
    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()

    # Prepare work items
    items_a = [
        (str(root_a / f), f, Path(f).suffix.lower(), k, w, normalize)
        for f in files_a
    ]
    items_b = [
        (str(root_b / f), f, Path(f).suffix.lower(), k, w, normalize)
        for f in files_b
    ]

    logger.info("Deep Compare: extracting fingerprints (%d + %d files, %d workers) …",
                len(items_a), len(items_b), workers)

    # Parallel fingerprint extraction
    fp_a: dict[str, set[int]] = {}
    fp_a_counts: dict[str, int] = {}
    fp_b: dict[str, set[int]] = {}

    all_items = items_a + items_b
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        results = list(pool.map(_extract_one, all_items))

    for i, (rel, hset, cnt) in enumerate(results):
        if i < len(items_a):
            fp_a[rel] = hset
            fp_a_counts[rel] = cnt
        else:
            fp_b[rel] = hset

    # Build inverted index over B-files
    inv_b = build_inverted_index(fp_b, max_entries=max_index_entries)

    # Query each A-file against the index
    deep_results: list[DeepMatchResult] = []

    for file_id_a, hashes_a in fp_a.items():
        if not hashes_a:
            continue

        # Accumulate shared-hash counts per B-file
        b_counts: dict[str, int] = defaultdict(int)
        for h in hashes_a:
            for file_id_b in inv_b.get(h, set()):
                b_counts[file_id_b] += 1

        if not b_counts:
            continue

        matched_b: list[tuple[str, int, float]] = []
        for file_id_b, shared in b_counts.items():
            jaccard = _jaccard(hashes_a, fp_b[file_id_b])
            if jaccard >= min_jaccard:
                matched_b.append((file_id_b, shared, round(jaccard, 4)))

        # Sort by Jaccard descending
        matched_b.sort(key=lambda x: x[2], reverse=True)

        if matched_b:
            deep_results.append(DeepMatchResult(
                file_a=file_id_a,
                matched_files_b=matched_b,
                fingerprint_count_a=fp_a_counts.get(file_id_a, 0),
            ))

    deep_results.sort(key=lambda r: r.file_a)
    logger.info("Deep Compare: found %d A-files with cross-matches", len(deep_results))
    return deep_results
