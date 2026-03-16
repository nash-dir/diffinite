"""파이프라인 오케스트레이터.

Collection → Parsing → Diff → Deep Compare → Report 전체 흐름을 조율하는
``run_pipeline()`` 함수를 제공한다. CLI에서 직접 호출.

실행 모드:
    - ``simple``: 1:1 파일 매칭 + diff + 보고서. Winnowing 미사용. 빠름.
    - ``deep``: 1:1 + N:M Winnowing 크로스매칭. 정밀.

보고서 형식:
    - ``--report-pdf``: 병합 PDF (북마크 + Bates 번호). 법정 제출용.
    - ``--report-html``: 독립형 HTML (자기 완결형 CSS/JS).
    - ``--report-md``: Markdown 요약 (CI/CD 통합용).

PDF 전략 (Divide-and-Conquer):
    대규모 파일 쌍에서 단일 PDF 변환 시 메모리 폭발을 방지하기 위해,
    파일별로 개별 PDF를 생성한 후 ``pypdf``로 병합한다.
    병합 시 파일별 북마크와 Bates 번호를 자동 추가.

의존:
    - ``collector.py``: 파일 수집 & 매칭
    - ``parser.py``: 주석 제거
    - ``differ.py``: Diff 계산 + HTML 생성
    - ``deep_compare.py``: N:M 크로스매칭
    - ``pdf_gen.py``: PDF 보고서 생성

호출관계:
    ``cli.main()`` → ``run_pipeline()``
    ``run_pipeline()`` → ``_generate_pdf/html/markdown_report()``
"""

from __future__ import annotations

import html as html_mod
import logging
import os
import tempfile
from pathlib import Path

from diffinite.collector import collect_files, match_files, FUZZY_THRESHOLD
from diffinite.deep_compare import run_deep_compare
from diffinite.differ import compute_diff, generate_html_diff, read_file
from diffinite.fingerprint import DEFAULT_K, DEFAULT_W
from diffinite.models import AnalysisMetadata, DiffResult, DeepMatchResult
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _compute_ln_col_width(line_counts: list[int]) -> int:
    """Compute a unified line-number column width for all diff pages."""
    max_ln = max(line_counts) if line_counts else 1
    digits = len(str(max_ln))
    return max(28, digits * 7 + 10)


def _build_metadata_banner_md(meta: AnalysisMetadata) -> str:
    """Return a Markdown metadata block for report transparency."""
    lines = [
        "## Analysis Configuration\n",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| **Execution Mode** | `{meta.exec_mode}` |",
        f"| **K-gram (K)** | `{meta.k}` |",
        f"| **Window (W)** | `{meta.w}` |",
        f"| **Threshold (T)** | `{meta.threshold:.2f}` |",
        "",
    ]
    return "\n".join(lines)


def _build_metadata_banner_html(meta: AnalysisMetadata) -> str:
    """Return an HTML metadata block for report transparency."""
    return (
        '<div class="analysis-meta" style="'
        "border:2px solid #0078d4;border-radius:6px;"
        "padding:10px 16px;margin-bottom:20px;"
        'background:#f0f7ff;font-size:11px;">\n'
        "<strong>📋 Analysis Configuration</strong><br>\n"
        f"<strong>Mode:</strong> {html_mod.escape(meta.exec_mode)} &nbsp;|&nbsp; "
        f"<strong>K=</strong>{meta.k}, <strong>W=</strong>{meta.w}, "
        f"<strong>T=</strong>{meta.threshold:.2f}"
        "\n</div>\n"
    )


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def _generate_markdown_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    compare_comment: bool,
    deep_results: list[DeepMatchResult] | None,
    output_path: str,
    *,
    metadata: AnalysisMetadata | None = None,
) -> None:
    """Generate a Markdown summary report."""
    unit = "word" if by_word else "line"
    comment_mode = "included" if compare_comment else "excluded"

    lines: list[str] = []
    lines.append("# Diffinite — Source Code Diff Report\n")

    if metadata:
        lines.append(_build_metadata_banner_md(metadata))

    lines.append(f"- **Dir A:** `{dir_a}`")
    lines.append(f"- **Dir B:** `{dir_b}`")
    lines.append(f"- **Comparison unit:** {unit}")
    lines.append(f"- **Comments:** {comment_mode}")
    lines.append(f"- **Matched pairs:** {len(results)}")
    lines.append(f"- **Unmatched:** {len(unmatched_a)} (A) / {len(unmatched_b)} (B)\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| # | File A | File B | Name Sim. | Match | +Added | −Deleted |")
    lines.append("|---|--------|--------|:---------:|:-----:|:------:|:--------:|")
    for idx, r in enumerate(results, 1):
        pct = r.ratio * 100
        err = f" ⚠ {r.error}" if r.error else ""
        lines.append(
            f"| {idx} | `{r.match.rel_path_a}` | `{r.match.rel_path_b}` "
            f"| {r.match.similarity:.1f} | {pct:.1f}%{err} "
            f"| +{r.additions} | −{r.deletions} |"
        )

    # Unmatched
    if unmatched_a or unmatched_b:
        lines.append("\n## Unmatched Files\n")
        if unmatched_a:
            lines.append(f"### Only in A (`{dir_a}`)\n")
            for f in unmatched_a:
                lines.append(f"- `{f}`")
        if unmatched_b:
            lines.append(f"\n### Only in B (`{dir_b}`)\n")
            for f in unmatched_b:
                lines.append(f"- `{f}`")

    # Deep Compare
    if deep_results:
        lines.append("\n## Deep Compare — N:M Cross-Match Results\n")
        lines.append("| A File | B File(s) | Shared Hashes | Jaccard |")
        lines.append("|--------|-----------|:-------------:|:-------:|")
        for dr in deep_results:
            for b_file, shared, jaccard in dr.matched_files_b:
                lines.append(
                    f"| `{dr.file_a}` | `{b_file}` | {shared} | {jaccard*100:.1f}% |"
                )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Markdown report → %s", out.resolve())


# ---------------------------------------------------------------------------
# HTML report generator (standalone, self-contained)
# ---------------------------------------------------------------------------
def _generate_html_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    compare_comment: bool,
    deep_results: list[DeepMatchResult] | None,
    output_path: str,
    ln_col_width: int = 28,
    *,
    metadata: AnalysisMetadata | None = None,
) -> None:
    """Generate a standalone HTML report with all diffs inline."""
    cover_html_body = build_cover_html(
        results, unmatched_a, unmatched_b,
        dir_a, dir_b, by_word, compare_comment,
        deep_results=deep_results,
        metadata=metadata,
    )

    # Append all inline diffs
    unit = "word" if by_word else "line"
    diff_sections: list[str] = []
    for idx, r in enumerate(results, 1):
        if r.error:
            diff_sections.append(
                f'<h2>{idx}. {html_mod.escape(r.match.rel_path_a)} &harr; '
                f'{html_mod.escape(r.match.rel_path_b)}</h2>\n'
                f'<p style="color:red">Error: {html_mod.escape(r.error)}</p>\n'
            )
        else:
            from diffinite.pdf_gen import _ratio_badge
            diff_sections.append(
                f'<h2>{idx}. {html_mod.escape(r.match.rel_path_a)} &harr; '
                f'{html_mod.escape(r.match.rel_path_b)}</h2>\n'
                f'<p>Match ratio: {_ratio_badge(r.ratio)} &nbsp; '
                f'<span style="color:green">+{r.additions} {unit}(s)</span> &nbsp; '
                f'<span style="color:red">-{r.deletions} {unit}(s)</span></p>\n'
                f'{r.html_diff}\n'
            )

    # Write full standalone HTML
    from diffinite.pdf_gen import _CSS_BODY
    full_html = f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Diffinite — Diff Report</title>
<style>
{_CSS_BODY}
</style>
</head>
<body>
{cover_html_body}
<hr style="margin:40px 0">
{"<hr style='margin:40px 0'>".join(diff_sections)}
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(full_html, encoding="utf-8")
    logger.info("HTML report → %s", out.resolve())


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
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
    # Execution mode & deep compare options
    exec_mode: str = "deep",
    workers: int = 4,
    kgram_size: int = DEFAULT_K,
    window_size: int = DEFAULT_W,
    min_jaccard: float = 0.05,
    normalize: bool = False,
    metadata: AnalysisMetadata | None = None,
    # Multi-format output
    report_pdf: str | None = None,
    report_html: str | None = None,
    report_md: str | None = None,
    # Forensic options
    autojunk: bool = True,
    max_index_entries: int = 10_000_000,
) -> None:
    """Execute the full diff-to-report pipeline.

    Execution Modes
    ===============
    ``simple``
        1. Collect files → fuzzy 1:1 match
        2. Read + optional comment strip
        3. Compute diff + Pygments-highlighted HTML
        4. Generate report in requested format(s)

    ``deep`` (default)
        Adds Winnowing-based N:M cross-matching and appends the
        cross-match table to the cover page / separate PDF section.

    Output formats (can be combined):
        --report-pdf  (default) — merged PDF with bookmarks.
        --report-html           — standalone self-contained HTML.
        --report-md             — Markdown summary table.
    """
    # Determine effective output paths
    if report_pdf is None and report_html is None and report_md is None:
        report_pdf = output_pdf

    # Build default metadata if caller didn't provide one
    if metadata is None:
        metadata = AnalysisMetadata(
            exec_mode=exec_mode,
            k=kgram_size,
            w=window_size,
            threshold=min_jaccard,
        )

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

    # Steps 2-4 — read, preprocess, diff, collect line counts
    results: list[DiffResult] = []
    all_line_counts: list[int] = []

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

        all_line_counts.append(text_a.count("\n") + 1)
        all_line_counts.append(text_b.count("\n") + 1)

        ratio, additions, deletions = compute_diff(text_a, text_b, by_word,
                                                    autojunk=autojunk)

        results.append(DiffResult(
            match=m,
            ratio=ratio,
            additions=additions,
            deletions=deletions,
            html_diff="",  # filled below after width computed
        ))

    # Compute global unified line-number column width
    ln_col_width = _compute_ln_col_width(all_line_counts)
    logger.info("  Responsive ln width: %dpx (max line: %s)",
                ln_col_width, max(all_line_counts) if all_line_counts else 0)

    # Generate HTML diffs with unified column width
    for m_idx, m in enumerate(matches):
        r = results[m_idx]
        if r.error:
            continue

        abs_a = str(root_a / m.rel_path_a)
        abs_b = str(root_b / m.rel_path_b)
        ext = Path(m.rel_path_a).suffix.lower()

        text_a = read_file(abs_a)
        text_b = read_file(abs_b)
        if text_a is None or text_b is None:
            continue
        if not compare_comment:
            text_a = strip_comments(text_a, ext, squash_blanks=squash_blanks)
            text_b = strip_comments(text_b, ext, squash_blanks=squash_blanks)

        html_diff = generate_html_diff(
            text_a, text_b,
            label_a=m.rel_path_a,
            label_b=m.rel_path_b,
            filename_a=m.rel_path_a,
            filename_b=m.rel_path_b,
            context_lines=3 if collapse_identical else -1,
            ln_col_width=ln_col_width,
            autojunk=autojunk,
        )
        results[m_idx] = DiffResult(
            match=r.match,
            ratio=r.ratio,
            additions=r.additions,
            deletions=r.deletions,
            html_diff=html_diff,
        )

    total_files = len(results)

    # Deep Compare (only in deep mode)
    deep_results = None
    if exec_mode == "deep":
        logger.info("Step 4b: Running Deep Compare (N:M cross-matching) …")
        deep_results = run_deep_compare(
            dir_a, dir_b, files_a, files_b,
            k=kgram_size, w=window_size,
            workers=workers, min_jaccard=min_jaccard,
            normalize=normalize,
            max_index_entries=max_index_entries,
        )
    elif exec_mode == "simple":
        logger.info("Step 4b: Skipped (simple mode — no Winnowing)")

    # ── Output generation ─────────────────────────────────────────────

    # Markdown report
    if report_md:
        logger.info("Generating Markdown report …")
        _generate_markdown_report(
            results, unmatched_a, unmatched_b,
            dir_a, dir_b, by_word, compare_comment,
            deep_results, report_md,
            metadata=metadata,
        )

    # HTML report
    if report_html:
        logger.info("Generating HTML report …")
        _generate_html_report(
            results, unmatched_a, unmatched_b,
            dir_a, dir_b, by_word, compare_comment,
            deep_results, report_html, ln_col_width,
            metadata=metadata,
        )

    # PDF report
    if report_pdf:
        logger.info("Generating PDF report (divide-and-conquer) …")
        _generate_pdf_report(
            results, unmatched_a, unmatched_b,
            dir_a, dir_b, by_word, compare_comment,
            deep_results, report_pdf,
            no_merge=no_merge,
            show_page_number=show_page_number,
            show_file_number=show_file_number,
            show_bates_number=show_bates_number,
            show_filename=show_filename,
            unit=unit,
            total_files=total_files,
            metadata=metadata,
        )

    logger.info("Done ✓")


# ---------------------------------------------------------------------------
# PDF report (extracted from old pipeline)
# ---------------------------------------------------------------------------
def _generate_pdf_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    compare_comment: bool,
    deep_results: list[DeepMatchResult] | None,
    output_pdf: str,
    *,
    no_merge: bool,
    show_page_number: bool,
    show_file_number: bool,
    show_bates_number: bool,
    show_filename: bool,
    unit: str,
    total_files: int,
    metadata: AnalysisMetadata | None = None,
) -> None:
    """Generate PDF report with divide-and-conquer merging."""
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
            metadata=metadata,
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
