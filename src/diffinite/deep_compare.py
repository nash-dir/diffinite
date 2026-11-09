"""N:M deep cross-matching engine.

Uses an **inverted index** over Winnowing fingerprints to compare every A file
with every B file, so similar code is found even when file names differ.

Architecture:
    1. Extract fingerprints for all files **in parallel** via
       ``ProcessPoolExecutor``.
    2. Build an inverted index from B-file hashes: ``hash → {file_ids}``.
    3. For each A-file, query the index → pick candidate B-files →
       compute Jaccard similarity.

Complexity:
    - Fingerprint extraction: O((N+M) × L) — L = avg file length; parallelism
      lowers wall time.
    - Inverted index build: O(Σ|fp_b|)
    - Per A-file lookup: O(|fp_a|) — a dramatic improvement over the naive
      O(N×M) pairwise comparison.
    - Total: O((N+M)×L + Σ|fp_a|) ≈ linear.

Parallelism constraint:
    The worker function (``_extract_one``) must be defined at module top level,
    because ``ProcessPoolExecutor`` serializes it via pickle. Using a class
    method or lambda raises ``PicklingError``.

Depends on:
    - ``fingerprint.py``: fingerprint extraction pipeline
    - ``parser.py``: comment stripping
    - ``differ.py``: file reading (encoding detection)

Call graph:
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
from diffinite.calibration import INCONCLUSIVE_TOKEN_FLOOR, RAW_LEGACY_THRESHOLD
from diffinite.fingerprint import (
    DEFAULT_K,
    DEFAULT_W,
    extract_fingerprints,
    tokenize,
)
from diffinite.languages import get_spec
from diffinite.models import DeepMatchResult
from diffinite.parser import strip_comments

logger = logging.getLogger(__name__)


# Non-fatal skip reason: recorded in the report, never treated as a failure.
SKIPPED_BINARY_REASON = "skipped-binary-content"


def _looks_binary(path: str) -> bool:
    """NUL byte in content that failed text decoding → treat as binary.

    Only consulted after decoding already failed, so UTF-16 text (which
    contains NULs but decodes) never reaches this check.
    """
    try:
        with open(path, "rb") as fh:
            # A NUL in the first 8 KiB is the same heuristic git and diff(1)
            # use to call a file binary; reading the whole file is unnecessary.
            return b"\x00" in fh.read(8192)
    except OSError:
        return False


# ──────────────────────────────────────────────────────────────────────
# 워커 함수 (ProcessPoolExecutor 직렬화를 위해 모듈 최상위 정의 필수)
# ──────────────────────────────────────────────────────────────────────
def _extract_one(args: tuple) -> tuple[str, str, set[int], int, int, str | None]:
    """단일 파일의 핑거프린트를 추출한다.

    Args:
        args: ``(side, abs_path, rel_path, extension, k, w, normalize, lang_aware,
                 max_bytes, strip_requested, encoding)``.

    Returns:
        ``(side, rel_path, hash_set, fingerprint_count, token_count, failure_reason)``
        읽기 실패 / 크기 초과 시 빈 set / count=0 / token_count=-1 반환.
        ``token_count`` 은 normalize 모드에서만 계산한다(판정불가 floor 판정용);
        그 외에는 -1(미산정)을 돌려준다.
    """
    (
        side,
        abs_path,
        rel_path,
        extension,
        k,
        w,
        normalize,
        lang_aware,
        max_bytes,
        strip_requested,
        encoding,
    ) = args

    # Size cap: skip oversized files entirely (both channels) so an untrusted
    # large/pathological file can't hang the run — especially under --lang-aware,
    # where Pygments lexing is expensive. Skipping (vs Tier-1 downgrade) also keeps
    # the lang-aware tier consistent across same-extension files.
    if max_bytes:
        try:
            if Path(abs_path).stat().st_size > max_bytes:
                logger.warning(
                    "Skipping oversized file in deep compare (> %d bytes): %s", max_bytes, rel_path
                )
                return side, rel_path, set(), 0, -1, "max-file-size-exceeded"
        except OSError:
            pass

    try:
        text = read_file(abs_path, encoding=encoding)
    except PermissionError:
        logger.warning("Permission denied during deep compare: %s", rel_path)
        return side, rel_path, set(), 0, -1, "permission-denied"

    if text is None:
        # An explicit decoder or a registered source language means this was
        # intended to be text. Treat the failed read/decode as evidence loss;
        # unregistered binary assets remain an intentional deep-channel skip.
        explicit_encoding = bool(encoding and encoding.lower() not in ("auto", ""))
        # Undecodable content with a NUL byte is binary data under a source-code
        # name (e.g. a compiled file saved as .py). The line channel already
        # reports such a pair by SHA-256 as binary; failing the whole run here
        # would make one misnamed file block every other result.
        if not explicit_encoding and _looks_binary(abs_path):
            logger.warning("Skipping binary content in deep compare: %s", rel_path)
            return side, rel_path, set(), 0, -1, SKIPPED_BINARY_REASON
        failure_reason = (
            "decode-or-read-failure" if explicit_encoding or get_spec(extension) else None
        )
        return side, rel_path, set(), 0, -1, failure_reason

    cleaned = strip_comments(text, extension) if strip_requested else text
    fps = extract_fingerprints(
        cleaned,
        k=k,
        w=w,
        normalize=normalize,
        ext=extension,
        lang_aware=lang_aware,
    )
    hash_set = {fp.hash_value for fp in fps}
    # Token count gates the inconclusive band; only needed under normalize.
    # Use the RAW token count as a channel-independent file-size proxy: the
    # compatibility guard was defined in raw-token units, while --lang-aware's
    # Pygments tokenization yields a different count. Changing channels would
    # silently change which pairs receive the conservative inconclusive label.
    n_tokens = len(tokenize(cleaned)) if normalize else -1
    return side, rel_path, hash_set, len(fps), n_tokens, None


# ──────────────────────────────────────────────────────────────────────
# 역 인덱스 (Information Retrieval 표준 기법)
# ──────────────────────────────────────────────────────────────────────
def build_inverted_index(
    fp_map: dict[str, set[int]],
    max_entries: int = 10_000_000,
) -> tuple[dict[int, set[str]], bool]:
    """해시값 → 파일 ID 집합의 역 인덱스를 구축한다.

    이 인덱스 덕분에 A-파일의 각 해시를 O(1)로 조회하여
    공유 해시를 가진 B-파일을 즉시 찾을 수 있다.
    나이브 쌍-단위 비교 O(N×M) 대비 O(Σ|fp_a|)로 단축.

    메모리: O(Σ|fp_b|) — 대규모 코퍼스에서 수 GB 가능.
    엔트리 수가 ``max_entries`` 를 초과해 실제로 버려지는 엔트리가 있을 때만
    경고 로그 출력 후 truncated index 반환(정확히 상한과 같으면 완전한 인덱스).
    ``--max-index-entries`` CLI 옵션으로 제어 가능.

    Returns:
        ``(index, truncated)``. ``truncated`` 가 True이면 상한에 도달해 일부
        엔트리가 누락된 것이므로, 호출쪽은 이를 보고서에 표기해야 한다.
    """
    index: dict[int, set[str]] = defaultdict(set)
    entry_count = 0
    for file_id, hashes in fp_map.items():
        for h in hashes:
            # 삽입 전에 검사한다: 정확히 max_entries 개로 끝나는 완전한 인덱스는
            # 잘린 것이 아니다. 실제로 엔트리를 버릴 때만 truncated=True.
            if entry_count >= max_entries:
                logger.warning(
                    "Inverted index truncated at %d entries "
                    "(--max-index-entries). Some matches may be missed.",
                    max_entries,
                )
                return index, True
            index[h].add(file_id)
            entry_count += 1
    return index, False


# ──────────────────────────────────────────────────────────────────────
# Jaccard 유사도 & N:M 매칭
# ──────────────────────────────────────────────────────────────────────
# 유사도 공식의 단일 출처(single source of truth). 운영 경로와 테스트가
# **정확히 같은 함수**를 쓰도록 evidence 모듈의 구현을 그대로 재사용한다.
from diffinite.evidence import jaccard_similarity as _jaccard  # noqa: E402


def run_deep_compare(
    dir_a: str,
    dir_b: str,
    files_a: list[str],
    files_b: list[str],
    *,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    workers: int = 4,  # Operational limit, not a similarity judgment.
    min_jaccard: float = RAW_LEGACY_THRESHOLD / 100.0,
    normalize: bool = False,
    lang_aware: bool = False,
    # Operational limits (memory and hang protection), not similarity judgments.
    max_index_entries: int = 10_000_000,
    max_file_size_mb: float = 10.0,
    strip_comments: bool = False,
    encoding: str | None = None,
    allow_partial: bool = False,
    status: Optional[dict] = None,
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
        lang_aware: If *True* (with *normalize*), use the language-aware
            normalization channel (Pygments lexer / registry keywords) instead
            of the language-agnostic default keyword set.
        status: Optional dict; if given, ``status["index_truncated"]`` is set
            to whether the inverted index hit ``max_index_entries`` (so the
            caller can flag an incomplete report).

    Returns:
        List of :class:`DeepMatchResult` for every A-file that has at
        least one B-file match above the threshold.
    """
    workers = max(1, workers)  # library guard: ProcessPoolExecutor needs >= 1
    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()

    # Prepare work items
    max_bytes = int(max_file_size_mb * 1024 * 1024) if max_file_size_mb else 0
    items_a = [
        (
            "A",
            str(root_a / f),
            f,
            Path(f).suffix.lower(),
            k,
            w,
            normalize,
            lang_aware,
            max_bytes,
            strip_comments,
            encoding,
        )
        for f in files_a
    ]
    items_b = [
        (
            "B",
            str(root_b / f),
            f,
            Path(f).suffix.lower(),
            k,
            w,
            normalize,
            lang_aware,
            max_bytes,
            strip_comments,
            encoding,
        )
        for f in files_b
    ]

    logger.info(
        "Deep Compare: extracting fingerprints (%d + %d files, %d workers) …",
        len(items_a),
        len(items_b),
        workers,
    )

    # Parallel fingerprint extraction
    fp_a: dict[str, set[int]] = {}
    fp_a_counts: dict[str, int] = {}
    fp_a_tokens: dict[str, int] = {}
    fp_b: dict[str, set[int]] = {}
    fp_b_tokens: dict[str, int] = {}

    all_items = items_a + items_b
    ctx = multiprocessing.get_context("spawn")
    results = []
    failed_files: list[dict[str, str]] = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        futures = [pool.submit(_extract_one, item) for item in all_items]
        for item, future in zip(all_items, futures):
            side, _abs_path, rel_path = item[:3]
            try:
                results.append(future.result())
            except Exception as exc:
                failed_files.append(
                    {
                        "side": side,
                        "path": rel_path,
                        "reason": f"worker-failure: {exc}",
                    }
                )

    skipped_binary: list[dict[str, str]] = []
    for side, rel, _hset, _cnt, _ntok, failure_reason in results:
        if failure_reason == SKIPPED_BINARY_REASON:
            skipped_binary.append({"side": side, "path": rel, "reason": failure_reason})
        elif failure_reason:
            failed_files.append(
                {
                    "side": side,
                    "path": rel,
                    "reason": failure_reason,
                }
            )

    # A configured size cap is still an omitted deep-analysis input.  It may be
    # emitted only under the caller's explicit partial-analysis authorization;
    # otherwise an incomplete evidence result would look like a complete run.
    fatal_failures = failed_files
    if fatal_failures and not allow_partial:
        details = ", ".join(
            f"{item['side']}:{item['path']} ({item['reason']})" for item in fatal_failures
        )
        raise RuntimeError(
            "Deep Compare worker/file failure; refusing a partial analysis. "
            "Use --allow-partial to emit an explicitly incomplete report: " + details
        )

    for side, rel, hset, cnt, ntok, _failure_reason in results:
        if side == "A":
            fp_a[rel] = hset
            fp_a_counts[rel] = cnt
            fp_a_tokens[rel] = ntok
        else:
            fp_b[rel] = hset
            fp_b_tokens[rel] = ntok

    # Build inverted index over B-files
    inv_b, index_truncated = build_inverted_index(fp_b, max_entries=max_index_entries)
    if status is not None:
        status["index_truncated"] = index_truncated
        status["requested_file_count"] = len(all_items)
        status["successful_file_count"] = len(all_items) - len(failed_files) - len(skipped_binary)
        status["failed_files"] = failed_files
        status["skipped_binary_files"] = skipped_binary

    if index_truncated and not allow_partial:
        raise RuntimeError(
            "Deep Compare inverted index reached --max-index-entries; "
            "refusing an incomplete analysis. Use --allow-partial to emit an "
            "explicitly incomplete report."
        )

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

        tokens_a = fp_a_tokens.get(file_id_a, -1)
        matched_b: list[tuple[str, int, float, bool]] = []
        for file_id_b in b_counts:
            # Recount from the full sets: under --allow-partial the inverted
            # index may be truncated, and Jaccard, containment and the shared
            # count must all describe the same two sets.
            shared = len(hashes_a & fp_b[file_id_b])
            jaccard = _jaccard(hashes_a, fp_b[file_id_b])
            if jaccard >= min_jaccard:
                # Inconclusive band: the published corpus did not establish a
                # separate precision claim for this small-file guard. Flag the
                # score conservatively instead of presenting it as confident.
                tokens_b = fp_b_tokens.get(file_id_b, -1)
                smaller = min(tokens_a, tokens_b)
                inconclusive = normalize and smaller >= 0 and smaller < INCONCLUSIVE_TOKEN_FLOOR
                matched_b.append((file_id_b, shared, round(jaccard, 4), inconclusive))

        # Sort by Jaccard desc, then shared-hash count desc, then file id asc.
        # The full tie-break is seed-independent: without it, equal-Jaccard
        # matches kept set-iteration order (PYTHONHASHSEED-dependent), so the
        # reported "top match" could change run-to-run on identical inputs.
        matched_b.sort(key=lambda x: (-x[2], -x[1], x[0]))

        if matched_b:
            deep_results.append(
                DeepMatchResult(
                    file_a=file_id_a,
                    matched_files_b=matched_b,
                    fingerprint_count_a=fp_a_counts.get(file_id_a, 0),
                    unique_hashes_a=len(hashes_a),
                    unique_hashes_b={b: len(fp_b[b]) for b, *_ in matched_b},
                )
            )

    deep_results.sort(key=lambda r: r.file_a)
    logger.info("Deep Compare: found %d A-files with cross-matches", len(deep_results))
    return deep_results
