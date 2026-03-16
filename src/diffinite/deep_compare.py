"""N:M Deep 크로스매칭 엔진.

Winnowing 핑거프린트의 **역 인덱스(Inverted Index)** 를 활용하여,
코드가 여러 파일로 분산·병합된 경우에도 유사 코드를 효율적으로 탐지한다.

아키텍처:
    1. ``ProcessPoolExecutor``로 모든 파일의 핑거프린트를 **병렬 추출**.
    2. B-파일의 해시값으로 역 인덱스 구축: ``hash → {file_ids}``.
    3. A-파일별로 인덱스 조회 → 후보 B-파일 결정 → Jaccard 계산.
    4. Multi-channel 모드에서는 6채널 증거 점수 + 분류 + AFC 분석 추가.

복잡도:
    - 핑거프린트 추출: O((N+M) × L) — L = 평균 파일 길이, 병렬화로 wall time ↓
    - 역 인덱스 구축: O(Σ|fp_b|)
    - A-파일별 조회: O(|fp_a|) — 나이브 O(N×M) 대비 극적 개선
    - 전체: O((N+M)×L + Σ|fp_a|) ≈ 선형

병렬화 제약:
    워커 함수(``_extract_one``, ``_extract_multi``)는 모듈 최상위에 정의해야 한다.
    ``ProcessPoolExecutor``가 pickle로 함수를 직렬화하기 때문.
    클래스 메서드나 람다를 사용하면 ``PicklingError`` 발생.

의존:
    - ``fingerprint.py``: 핑거프린트 추출 파이프라인
    - ``evidence.py``: multi-channel 모드에서만 lazy import (순환 방지)
    - ``parser.py``: 주석 제거
    - ``differ.py``: 파일 읽기 (인코딩 감지)

호출관계:
    ``pipeline.run_pipeline()`` → ``run_deep_compare()``
    → ``_run_single_channel()`` 또는 ``_run_multi_channel()``
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

from diffinite.differ import read_file
from diffinite.fingerprint import (
    DEFAULT_K,
    DEFAULT_W,
    FingerprintEntry,
    extract_fingerprints,
)
from diffinite.models import DeepMatchResult
from diffinite.parser import strip_comments

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 워커 함수 (ProcessPoolExecutor 직렬화를 위해 모듈 최상위 정의 필수)
# ──────────────────────────────────────────────────────────────────────
def _extract_one(args: tuple) -> tuple[str, set[int], int]:
    """Single-channel 모드용 워커: 단일 파일의 핑거프린트를 추출한다.

    Args:
        args: ``(abs_path, rel_path, extension, k, w, normalize, tokenizer)``
              — tuple 포장은 ``pool.map()`` 인터페이스 제약.

    Returns:
        ``(rel_path, hash_set, fingerprint_count)``
        읽기 실패 시 빈 set / count=0 반환.
    """
    abs_path, rel_path, extension, k, w, normalize, tokenizer = args
    text = read_file(abs_path)
    if text is None:
        return rel_path, set(), 0

    cleaned = strip_comments(text, extension)
    fps = extract_fingerprints(
        cleaned, k=k, w=w, normalize=normalize,
        mode=tokenizer, extension=extension,
    )
    hash_set = {fp.hash_value for fp in fps}
    return rel_path, hash_set, len(fps)


def _extract_multi(args: tuple) -> tuple[str, dict[str, set[int]], str, str]:
    """Multi-channel 모드용 워커: 3개 채널의 핑거프린트를 동시 추출한다.

    추출 채널:
        - ``raw``: 정규화 없는 원문 토큰 → 문자적 복사(Type-1) 탐지
        - ``normalized``: ID/LIT 정규화 → 식별자 변경(Type-2) 탐지
        - ``ast``: tree-sitter 구조 → 구조적 유사성 탐지 (폴백 시 생략)

    AST 채널은 normalized와 결과가 동일하면 저장하지 않는다
    (tree-sitter 미설치 = 토큰 폴백 = normalized와 동일).

    Returns:
        ``(rel_path, {mode: hash_set}, raw_text, cleaned_text)``
        raw_text/cleaned_text는 나중에 identifier/comment 채널 계산에 필요.
    """
    abs_path, rel_path, extension, k, w = args
    text = read_file(abs_path)
    if text is None:
        return rel_path, {}, "", ""

    cleaned = strip_comments(text, extension)
    result: dict[str, set[int]] = {}

    # ── 채널 1: Raw (표현 수준 유사도) ──
    fps_raw = extract_fingerprints(
        cleaned, k=k, w=w, normalize=False,
        mode="token", extension=extension,
    )
    result["raw"] = {fp.hash_value for fp in fps_raw}

    # ── 채널 2: Normalized (아이디어 수준 유사도) ──
    fps_norm = extract_fingerprints(
        cleaned, k=k, w=w, normalize=True,
        mode="token", extension=extension,
    )
    result["normalized"] = {fp.hash_value for fp in fps_norm}

    # ── 채널 3: AST (구조적 유사도) ──
    fps_ast = extract_fingerprints(
        cleaned, k=k, w=w, normalize=True,
        mode="ast", extension=extension,
    )
    ast_set = {fp.hash_value for fp in fps_ast}
    # AST 토크나이징이 실제로 작동했을 때만 저장 (토큰 폴백과 구별)
    if ast_set != result["normalized"]:
        result["ast"] = ast_set

    return rel_path, result, text, cleaned


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
    tokenizer: str = "token",
    multi_channel: bool = False,
    profile: str = "industrial",
    max_index_entries: int = 10_000_000,
) -> list[DeepMatchResult]:
    """Execute N:M cross-matching between two directories.

    1. Parallel fingerprint extraction for all files.
    2. Build inverted index over B-files.
    3. For each A-file, query the index to find matching B-files.
    4. Compute Jaccard similarity and filter by *min_jaccard*.

    When ``multi_channel`` is True, additional evidence channels
    (raw/normalised/AST Winnowing, identifier cosine, comment/string
    overlap) are computed for each matched pair and stored in
    ``DeepMatchResult.channel_scores``.

    Args:
        dir_a / dir_b: Root directory paths.
        files_a / files_b: Relative paths collected via :func:`collector.collect_files`.
        k: K-gram size.
        w: Winnowing window size.
        workers: Number of parallel worker processes.
        min_jaccard: Minimum Jaccard similarity to include in results.
        normalize: If *True*, normalise tokens before fingerprinting.
        tokenizer: Tokenisation strategy (``"token"``, ``"ast"``, ``"pdg"``).
        multi_channel: If *True*, compute all evidence channel scores.

    Returns:
        List of :class:`DeepMatchResult` for every A-file that has at
        least one B-file match above the threshold.
    """
    if multi_channel:
        return _run_multi_channel(
            dir_a, dir_b, files_a, files_b,
            k=k, w=w, workers=workers, min_jaccard=min_jaccard,
            profile=profile,
            max_index_entries=max_index_entries,
        )

    return _run_single_channel(
        dir_a, dir_b, files_a, files_b,
        k=k, w=w, workers=workers, min_jaccard=min_jaccard,
        normalize=normalize, tokenizer=tokenizer,
        max_index_entries=max_index_entries,
    )


def _run_single_channel(
    dir_a: str,
    dir_b: str,
    files_a: list[str],
    files_b: list[str],
    *,
    k: int,
    w: int,
    workers: int,
    min_jaccard: float,
    normalize: bool,
    tokenizer: str,
    max_index_entries: int = 10_000_000,
) -> list[DeepMatchResult]:
    """Single-channel deep compare (original implementation)."""
    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()

    # Prepare work items
    items_a = [
        (str(root_a / f), f, Path(f).suffix.lower(), k, w, normalize, tokenizer)
        for f in files_a
    ]
    items_b = [
        (str(root_b / f), f, Path(f).suffix.lower(), k, w, normalize, tokenizer)
        for f in files_b
    ]

    logger.info("Deep Compare: extracting fingerprints (%d + %d files, %d workers) …",
                len(items_a), len(items_b), workers)

    # Parallel fingerprint extraction
    fp_a: dict[str, set[int]] = {}
    fp_a_counts: dict[str, int] = {}
    fp_b: dict[str, set[int]] = {}

    all_items = items_a + items_b
    with ProcessPoolExecutor(max_workers=workers) as pool:
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


def _run_multi_channel(
    dir_a: str,
    dir_b: str,
    files_a: list[str],
    files_b: list[str],
    *,
    k: int,
    w: int,
    workers: int,
    min_jaccard: float,
    profile: str = "industrial",
    max_index_entries: int = 10_000_000,
) -> list[DeepMatchResult]:
    """Multi-channel 모드 크로스매칭 + 증거 점수 산정.

    Single-channel 대비 추가 수행:
    1. **코퍼스 레벨 TF-IDF** — 전체 파일에서 IDF 구축 → 공통 식별자 가중치 하향
    2. **6채널 증거 점수** — raw/norm/AST/ident/decl/comment
    3. **교차 채널 분류** — DIRECT_COPY, SSO_COPYING 등 패턴 결정
    4. **AFC 분석** — Altai 3단계 (Abstraction-Filtration-Comparison)

    ``evidence`` 모듈은 여기서 **lazy import**한다.
    ``evidence`` → ``fingerprint`` → ``deep_compare`` 순환 방지를 위한 의도적 설계.
    """
    # 순환 import 방지를 위한 함수 내부 import
    from diffinite.evidence import (
        _build_idf,
        _extract_identifiers,
        afc_analysis,
        classify_similarity_pattern,
        compute_channel_scores,
        get_weights_for_profile,
    )

    weights = get_weights_for_profile(profile)

    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()

    # Prepare work items for multi-channel extraction
    items_a = [
        (str(root_a / f), f, Path(f).suffix.lower(), k, w)
        for f in files_a
    ]
    items_b = [
        (str(root_b / f), f, Path(f).suffix.lower(), k, w)
        for f in files_b
    ]

    logger.info(
        "Deep Compare (multi-channel): extracting fingerprints "
        "(%d + %d files, %d workers) …",
        len(items_a), len(items_b), workers,
    )

    # Parallel multi-channel extraction
    all_items = items_a + items_b
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_extract_multi, all_items))

    # Organise results
    fp_a: dict[str, dict[str, set[int]]] = {}
    text_a: dict[str, str] = {}
    cleaned_a: dict[str, str] = {}
    ext_a: dict[str, str] = {}

    fp_b: dict[str, dict[str, set[int]]] = {}
    text_b: dict[str, str] = {}
    cleaned_b: dict[str, str] = {}
    ext_b: dict[str, str] = {}

    for i, (rel, mode_hashes, raw_text, clean_text) in enumerate(results):
        if i < len(items_a):
            fp_a[rel] = mode_hashes
            text_a[rel] = raw_text
            cleaned_a[rel] = clean_text
            ext_a[rel] = items_a[i][2]  # extension
        else:
            j = i - len(items_a)
            fp_b[rel] = mode_hashes
            text_b[rel] = raw_text
            cleaned_b[rel] = clean_text
            ext_b[rel] = items_b[j][2]

    # ── Corpus-level IDF for TF-IDF weighting ──
    all_identifier_lists: list[list[str]] = []
    for ct in list(cleaned_a.values()) + list(cleaned_b.values()):
        if ct:
            all_identifier_lists.append(_extract_identifiers(ct))
    idf = _build_idf(all_identifier_lists) if all_identifier_lists else None

    # Build inverted index using normalised fingerprints (best general coverage)
    norm_b = {rel: hashes.get("normalized", set()) for rel, hashes in fp_b.items()}
    inv_b = build_inverted_index(norm_b, max_entries=max_index_entries)

    # Query each A-file against the index
    deep_results: list[DeepMatchResult] = []

    for file_id_a, mode_hashes_a in fp_a.items():
        norm_a = mode_hashes_a.get("normalized", set())
        if not norm_a:
            continue

        b_counts: dict[str, int] = defaultdict(int)
        for h in norm_a:
            for file_id_b in inv_b.get(h, set()):
                b_counts[file_id_b] += 1

        if not b_counts:
            continue

        matched_b: list[tuple[str, int, float]] = []
        all_channel_scores: dict[str, dict[str, float]] = {}
        all_classifications: dict[str, str] = {}
        all_afc_results: dict[str, dict] = {}

        for file_id_b, shared in b_counts.items():
            jaccard = _jaccard(norm_a, norm_b[file_id_b])
            if jaccard < min_jaccard:
                continue

            matched_b.append((file_id_b, shared, round(jaccard, 4)))

            # Compute multi-channel scores
            mode_hashes_b = fp_b[file_id_b]
            extension = ext_a.get(file_id_a, ext_b.get(file_id_b, ""))

            scores = compute_channel_scores(
                fp_raw_a=mode_hashes_a.get("raw"),
                fp_raw_b=mode_hashes_b.get("raw"),
                fp_norm_a=mode_hashes_a.get("normalized"),
                fp_norm_b=mode_hashes_b.get("normalized"),
                fp_ast_a=mode_hashes_a.get("ast"),
                fp_ast_b=mode_hashes_b.get("ast"),
                source_a=text_a.get(file_id_a),
                source_b=text_b.get(file_id_b),
                cleaned_a=cleaned_a.get(file_id_a),
                cleaned_b=cleaned_b.get(file_id_b),
                extension=extension,
                weights=weights,
            )
            all_channel_scores[file_id_b] = scores

            # ── Cross-channel classification ──
            all_classifications[file_id_b] = classify_similarity_pattern(scores)

            # ── AFC analysis ──
            ca = cleaned_a.get(file_id_a)
            cb = cleaned_b.get(file_id_b)
            if ca and cb and extension:
                try:
                    afc = afc_analysis(
                        ca, cb, extension,
                        skip_boilerplate=True,
                        idf=idf,
                    )
                    all_afc_results[file_id_b] = afc
                except Exception as exc:
                    logger.debug("AFC analysis failed for %s ↔ %s: %s",
                                 file_id_a, file_id_b, exc)

        matched_b.sort(key=lambda x: x[2], reverse=True)

        if matched_b:
            fp_count = sum(len(s) for s in mode_hashes_a.values())
            deep_results.append(DeepMatchResult(
                file_a=file_id_a,
                matched_files_b=matched_b,
                fingerprint_count_a=fp_count,
                channel_scores=all_channel_scores,
                classification=all_classifications,
                afc_results=all_afc_results,
            ))

    deep_results.sort(key=lambda r: r.file_a)
    logger.info(
        "Deep Compare (multi-channel): found %d A-files with cross-matches",
        len(deep_results),
    )
    return deep_results
