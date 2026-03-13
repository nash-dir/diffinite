"""Pipeline orchestrator.

Ties together collection, parsing, diffing, deep-compare, and PDF
generation into a single ``run_pipeline()`` function that is called
by the CLI.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from diffinite.collector import collect_files, match_files, FUZZY_THRESHOLD
from diffinite.deep_compare import run_deep_compare
from diffinite.differ import compute_diff, generate_html_diff, read_file
from diffinite.fingerprint import DEFAULT_K, DEFAULT_W
from diffinite.models import DiffResult
from diffinite.parser import strip_comments
from diffinite.pdf_gen import (
    add_bates_numbers,
    build_cover_html,
    build_diff_page_html,
    html_to_pdf,
    merge_with_bookmarks,
    stamp_bates_inplace,
)

logger = logging.getLogger(__name__)


def run_pipeline(
    dir_a: str,
    dir_b: str,
    by_word: bool = False,
    compare_comment: bool = True,
    squash_blanks: bool = False,
    output_pdf: str = "report.pdf",
    threshold: float = FUZZY_THRESHOLD,
    *,
    no_merge: bool = False,
    show_page_number: bool = False,
    show_file_number: bool = False,
    show_bates_number: bool = False,
    show_filename: bool = False,
    # Display options
    collapse_identical: bool = False,
    # Deep compare options
    deep: bool = False,
    workers: int = 4,
    kgram_size: int = DEFAULT_K,
    window_size: int = DEFAULT_W,
    min_jaccard: float = 0.05,
    normalize: bool = False,
    mode: str = "token",
    multi_channel: bool = False,
) -> None:
    """Execute the full diff-to-PDF pipeline.

    Standard mode:
        1. Collect files → fuzzy 1:1 match
        2. Read + optional comment strip
        3. Compute diff + Pygments-highlighted HTML
        4. Generate per-file PDFs → merge with bookmarks

    Deep mode (``--deep``):
        Adds Winnowing-based N:M cross-matching and appends the
        cross-match table to the cover page / separate PDF section.
    """
    # Step 1 — collect & match
    logger.info("Step 1: Collecting files …")
    files_a = collect_files(dir_a)
    files_b = collect_files(dir_b)
    logger.info("  Dir A: %d files  |  Dir B: %d files", len(files_a), len(files_b))

    matches, unmatched_a, unmatched_b = match_files(
        files_a, files_b, threshold=threshold,
    )
    logger.info(
        "  Matched pairs: %d  |  Unmatched A: %d  |  Unmatched B: %d",
        len(matches), len(unmatched_a), len(unmatched_b),
    )

    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()
    unit = "word" if by_word else "line"

    # Steps 2-4 — read, preprocess, diff for each pair
    results: list[DiffResult] = []
    for m in matches:
        abs_a = str(root_a / m.rel_path_a)
        abs_b = str(root_b / m.rel_path_b)
        ext = Path(m.rel_path_a).suffix.lower()

        text_a = read_file(abs_a)
        text_b = read_file(abs_b)

        if text_a is None or text_b is None:
            results.append(DiffResult(
                match=m, ratio=0.0, additions=0, deletions=0,
                html_diff="", error="Could not decode one or both files",
            ))
            continue

        if not compare_comment:
            text_a = strip_comments(text_a, ext, squash_blanks=squash_blanks)
            text_b = strip_comments(text_b, ext, squash_blanks=squash_blanks)

        ratio, additions, deletions = compute_diff(text_a, text_b, by_word)

        html_diff = generate_html_diff(
            text_a, text_b,
            label_a=m.rel_path_a,
            label_b=m.rel_path_b,
            filename_a=m.rel_path_a,
            filename_b=m.rel_path_b,
            context_lines=3 if collapse_identical else -1,
        )

        results.append(DiffResult(
            match=m,
            ratio=ratio,
            additions=additions,
            deletions=deletions,
            html_diff=html_diff,
        ))

    total_files = len(results)

    # Deep Compare (optional)
    deep_results = None
    if deep:
        logger.info("Step 4b: Running Deep Compare (N:M cross-matching) …")
        deep_results = run_deep_compare(
            dir_a, dir_b, files_a, files_b,
            k=kgram_size, w=window_size,
            workers=workers, min_jaccard=min_jaccard,
            normalize=normalize,
            mode=mode,
            multi_channel=multi_channel,
        )

    # Step 5 — divide-and-conquer PDF generation
    logger.info("Step 5: Generating PDFs (divide-and-conquer) …")

    if no_merge:
        out_stem = Path(output_pdf).stem
        out_dir = Path(output_pdf).parent / f"{out_stem}_files"
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info("  No-merge mode — individual PDFs → %s", out_dir.resolve())

    with tempfile.TemporaryDirectory(prefix="diffinite_") as tmpdir:
        # (1) Cover page
        cover_html = build_cover_html(
            results, unmatched_a, unmatched_b,
            dir_a, dir_b, by_word, compare_comment,
            deep_results=deep_results,
        )
        if no_merge:
            cover_dest = str(out_dir / "000_cover.pdf")  # type: ignore[possibly-undefined]
        else:
            cover_dest = os.path.join(tmpdir, "00_cover.pdf")
        cover_ok = html_to_pdf(cover_html, cover_dest)
        if cover_ok:
            logger.info("  Cover page → OK")

        # (2) Per-file diff pages
        diff_pdf_pairs: list[tuple[str, DiffResult]] = []
        for idx, r in enumerate(results, 1):
            diff_html = build_diff_page_html(
                r, idx, unit,
                show_page_number=show_page_number,
                show_file_number=show_file_number,
                total_files=total_files,
                show_filename=show_filename,
            )
            safe_name = Path(r.match.rel_path_a).name.replace(" ", "_")
            if no_merge:
                diff_dest = str(out_dir / f"{idx:03d}_{safe_name}.pdf")  # type: ignore[possibly-undefined]
            else:
                diff_dest = os.path.join(tmpdir, f"{idx:03d}_diff.pdf")
            if html_to_pdf(diff_html, diff_dest):
                diff_pdf_pairs.append((diff_dest, r))
                logger.info("  Diff page %d (%s) → OK", idx, r.match.rel_path_a)
            else:
                logger.warning("  Diff page %d FAILED", idx)

        # (3) Merge with bookmarks or individual PDFs
        if no_merge:
            # Bates for individual PDFs
            if show_bates_number:
                _apply_bates_to_individual(
                    [cover_dest] + [p for p, _ in diff_pdf_pairs]
                )
            logger.info("  No-merge mode — %d PDFs saved",
                        1 + len(diff_pdf_pairs))
        elif cover_ok or diff_pdf_pairs:
            merge_with_bookmarks(
                cover_dest, diff_pdf_pairs, output_pdf,
            )
            if show_bates_number:
                logger.info("  Stamping Bates numbers …")
                bates_tmp = os.path.join(tmpdir, "bates_tmp.pdf")
                os.replace(output_pdf, bates_tmp)
                add_bates_numbers(bates_tmp, output_pdf)
        else:
            logger.error("No PDF parts were generated — cannot create report")

    logger.info("Done ✓")


def _apply_bates_to_individual(pdf_paths: list[str]) -> None:
    """Stamp sequential Bates numbers across individual PDFs."""
    from pypdf import PdfReader as _PR

    page_counts = []
    for p in pdf_paths:
        try:
            page_counts.append(len(_PR(p).pages))
        except Exception:
            page_counts.append(0)

    total = sum(page_counts)
    digits = max(4, len(str(total)))
    offset = 0
    for p, pc in zip(pdf_paths, page_counts):
        if pc == 0:
            continue
        stamp_bates_inplace(p, offset, digits)
        offset += pc
