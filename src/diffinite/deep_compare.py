"""N:M deep cross-matching engine.

Uses an **inverted index** of Winnowing fingerprints to efficiently
find all files in directory B that share logic with each file in
directory A — even when code has been split or merged across files.

Architecture
============

1. Extract fingerprints for every file (parallelised with
   ``ProcessPoolExecutor``).
2. Build a **global inverted index**: ``hash_value → [(file_id, pos), …]``.
3. For each file in A, look up its fingerprints in the index to find
   matching B-files in **O(|fp_A|)** instead of naïve O(N×M).
4. Compute Jaccard similarity: ``|A ∩ B| / |A ∪ B|``.

Multi-channel mode additionally computes:
- Raw Winnowing (no normalisation)
- Normalised Winnowing (identifier/literal abstraction)
- AST Winnowing (tree-sitter linearisation, if available)
- Identifier Cosine similarity
- Comment/String Overlap
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


# ---------------------------------------------------------------------------
# Worker function (must be top-level for pickling)
# ---------------------------------------------------------------------------
def _extract_one(args: tuple) -> tuple[str, set[int], int]:
    """Extract fingerprints for a single file.

    Args:
        args: ``(abs_path, rel_path, extension, k, w, normalize, tokenizer)``

    Returns:
        ``(rel_path, set_of_hash_values, total_fingerprint_count)``
    """
    abs_path, rel_path, extension, k, w, normalize, tokenizer = args
    text = read_file(abs_path)
    if text is None:
        return rel_path, set(), 0

    # Strip comments for normalisation
    cleaned = strip_comments(text, extension)
    fps = extract_fingerprints(
        cleaned, k=k, w=w, normalize=normalize,
        mode=tokenizer, extension=extension,
    )
    hash_set = {fp.hash_value for fp in fps}
    return rel_path, hash_set, len(fps)


def _extract_multi(args: tuple) -> tuple[str, dict[str, set[int]], str, str]:
    """Extract multi-channel fingerprints for a single file.

    Args:
        args: ``(abs_path, rel_path, extension, k, w)``

    Returns:
        ``(rel_path, {mode: hash_set}, raw_text, cleaned_text)``
    """
    abs_path, rel_path, extension, k, w = args
    text = read_file(abs_path)
    if text is None:
        return rel_path, {}, "", ""

    cleaned = strip_comments(text, extension)
    result: dict[str, set[int]] = {}

    # Raw (no normalisation)
    fps_raw = extract_fingerprints(
        cleaned, k=k, w=w, normalize=False,
        mode="token", extension=extension,
    )
    result["raw"] = {fp.hash_value for fp in fps_raw}

    # Normalised (Phase 1)
    fps_norm = extract_fingerprints(
        cleaned, k=k, w=w, normalize=True,
        mode="token", extension=extension,
    )
    result["normalized"] = {fp.hash_value for fp in fps_norm}

    # AST (Phase 2 — may fall back to token if tree-sitter unavailable)
    fps_ast = extract_fingerprints(
        cleaned, k=k, w=w, normalize=True,
        mode="ast", extension=extension,
    )
    ast_set = {fp.hash_value for fp in fps_ast}
    # Only store if different from normalised (meaning AST actually worked)
    if ast_set != result["normalized"]:
        result["ast"] = ast_set

    return rel_path, result, text, cleaned


# ---------------------------------------------------------------------------
# Inverted index
# ---------------------------------------------------------------------------
def build_inverted_index(
    fp_map: dict[str, set[int]],
) -> dict[int, set[str]]:
    """Build hash_value → {file_ids…} inverted index.

    Args:
        fp_map: Mapping of ``rel_path → set_of_hash_values``.

    Returns:
        Inverted index mapping each hash to the set of files containing it.
    """
    index: dict[int, set[str]] = defaultdict(set)
    for file_id, hashes in fp_map.items():
        for h in hashes:
            index[h].add(file_id)
    return index


# ---------------------------------------------------------------------------
# N:M matching
# ---------------------------------------------------------------------------
def _jaccard(set_a: set[int], set_b: set[int]) -> float:
    """Compute Jaccard similarity coefficient."""
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
        )

    return _run_single_channel(
        dir_a, dir_b, files_a, files_b,
        k=k, w=w, workers=workers, min_jaccard=min_jaccard,
        normalize=normalize, tokenizer=tokenizer,
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
    inv_b = build_inverted_index(fp_b)

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
) -> list[DeepMatchResult]:
    """Multi-channel deep compare with evidence scoring.

    Integrates:
    - Corpus-level TF-IDF weighting for identifier channels
    - Cross-channel pattern classification (SSO_COPYING, DIRECT_COPY, etc.)
    - AFC (Abstraction-Filtration-Comparison) analysis
    """
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
    inv_b = build_inverted_index(norm_b)

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
