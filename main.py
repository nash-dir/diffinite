#!/usr/bin/env python3
"""
Diffinite PoC — Source Code Directory Diff → PDF Report

Compares source code files across two directories (A, B) using fuzzy file-name
matching, produces quantitative analysis (match ratio, additions, deletions),
and generates a styled PDF report with side-by-side visual diffs.

Usage:
    python main.py dir_a dir_b --output-pdf report.pdf [--by-word] [--no-comments]
"""

from __future__ import annotations

import argparse
import difflib
import html
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from charset_normalizer import from_bytes
from rapidfuzz import fuzz
from xhtml2pdf import pisa

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FUZZY_THRESHOLD = 60  # minimum similarity score for file matching (0-100)

# Comment regex patterns keyed by file extension
_COMMENT_PATTERNS: dict[str, list[re.Pattern]] = {}


def _build_comment_patterns() -> dict[str, list[re.Pattern]]:
    """Build and cache compiled regex patterns for comment removal.

    Returns:
        Mapping of file extension → list of compiled regex patterns.
    """
    if _COMMENT_PATTERNS:
        return _COMMENT_PATTERNS

    # Python: # to end-of-line (avoid shebang-like false positives minimally)
    py_line = re.compile(r"#[^\n]*", re.MULTILINE)

    # C-family: // to end-of-line
    c_line = re.compile(r"//[^\n]*", re.MULTILINE)
    # C-family: /* ... */ (non-greedy, DOTALL)
    c_block = re.compile(r"/\*.*?\*/", re.DOTALL)

    # HTML/XML: <!-- ... -->
    html_block = re.compile(r"<!--.*?-->", re.DOTALL)

    for ext in (".py",):
        _COMMENT_PATTERNS[ext] = [py_line]

    for ext in (".js", ".ts", ".c", ".cpp", ".h", ".hpp", ".java", ".cs", ".go", ".rs"):
        _COMMENT_PATTERNS[ext] = [c_line, c_block]

    for ext in (".html", ".xml", ".htm", ".svg"):
        _COMMENT_PATTERNS[ext] = [html_block]

    return _COMMENT_PATTERNS


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FileMatch:
    """A matched pair of files from dir_a and dir_b."""

    rel_path_a: str
    rel_path_b: str
    similarity: float  # 0-100


@dataclass
class DiffResult:
    """Quantitative + visual diff result for one file pair."""

    match: FileMatch
    ratio: float  # 0.0 – 1.0
    additions: int
    deletions: int
    html_diff: str  # side-by-side HTML table
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Step 1: File collection & Fuzzy matching
# ---------------------------------------------------------------------------
def collect_files(directory: str) -> list[str]:
    """Recursively collect relative file paths under *directory*.

    Args:
        directory: Root directory to scan.

    Returns:
        Sorted list of relative POSIX-style paths.
    """
    root = Path(directory).resolve()
    paths: list[str] = []
    for item in root.rglob("*"):
        if item.is_file():
            paths.append(item.relative_to(root).as_posix())
    paths.sort()
    return paths


def match_files(
    files_a: list[str],
    files_b: list[str],
    threshold: float = FUZZY_THRESHOLD,
) -> Tuple[list[FileMatch], list[str], list[str]]:
    """Match files from two lists using fuzzy string similarity.

    Uses a greedy best-match strategy with the Hungarian-style approach:
    build a full similarity matrix, then greedily pick the best remaining
    pair until no pair exceeds the threshold.

    Args:
        files_a:   Relative paths from directory A.
        files_b:   Relative paths from directory B.
        threshold: Minimum similarity score (0–100) to accept a match.

    Returns:
        Tuple of (matched pairs, unmatched_a, unmatched_b).
    """
    # Build similarity matrix: list of (score, idx_a, idx_b)
    candidates: list[Tuple[float, int, int]] = []
    for i, fa in enumerate(files_a):
        for j, fb in enumerate(files_b):
            score = fuzz.ratio(fa, fb)
            if score >= threshold:
                candidates.append((score, i, j))

    # Sort descending by score
    candidates.sort(key=lambda x: x[0], reverse=True)

    used_a: set[int] = set()
    used_b: set[int] = set()
    matches: list[FileMatch] = []

    for score, i, j in candidates:
        if i in used_a or j in used_b:
            continue
        matches.append(FileMatch(files_a[i], files_b[j], score))
        used_a.add(i)
        used_b.add(j)

    unmatched_a = [files_a[i] for i in range(len(files_a)) if i not in used_a]
    unmatched_b = [files_b[j] for j in range(len(files_b)) if j not in used_b]

    return matches, unmatched_a, unmatched_b


# ---------------------------------------------------------------------------
# Step 2: File reading with encoding auto-detection
# ---------------------------------------------------------------------------
def read_file(path: str) -> Optional[str]:
    """Read a file and auto-detect its encoding via charset_normalizer.

    Args:
        path: Absolute or relative file path.

    Returns:
        Decoded text content, or None on failure.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return None

    if not raw:
        return ""

    result = from_bytes(raw).best()
    if result is None:
        logger.warning("Could not detect encoding for %s — skipping", path)
        return None

    try:
        return str(result)
    except Exception as exc:  # noqa: BLE001
        logger.error("Decoding failed for %s (%s): %s", path, result.encoding, exc)
        return None


# ---------------------------------------------------------------------------
# Step 3: Comment stripping
# ---------------------------------------------------------------------------
def strip_comments(text: str, extension: str) -> str:
    """Remove comments from *text* based on the file *extension*.

    Uses conservative regex patterns. Does NOT handle edge cases inside
    string literals (acceptable for PoC).

    Args:
        text:      Source code text.
        extension: Lowercase file extension including the dot, e.g. ".py".

    Returns:
        Text with comments removed.
    """
    patterns = _build_comment_patterns().get(extension, [])
    for pat in patterns:
        text = pat.sub("", text)
    return text


# ---------------------------------------------------------------------------
# Step 4: Diff analysis
# ---------------------------------------------------------------------------
def compute_diff(
    text_a: str,
    text_b: str,
    by_word: bool = False,
) -> Tuple[float, int, int]:
    """Compute similarity ratio, additions, and deletions between two texts.

    Args:
        text_a:  Text from directory A.
        text_b:  Text from directory B.
        by_word: If True, compare by whitespace-split tokens; else by lines.

    Returns:
        (ratio, additions, deletions) where ratio ∈ [0.0, 1.0].
    """
    if by_word:
        seq_a = text_a.split()
        seq_b = text_b.split()
    else:
        seq_a = text_a.splitlines(keepends=True)
        seq_b = text_b.splitlines(keepends=True)

    matcher = difflib.SequenceMatcher(None, seq_a, seq_b, autojunk=False)
    ratio = matcher.ratio()

    additions = 0
    deletions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            additions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "replace":
            additions += j2 - j1
            deletions += i2 - i1

    return ratio, additions, deletions


def generate_html_diff(
    text_a: str,
    text_b: str,
    label_a: str = "A",
    label_b: str = "B",
) -> str:
    """Generate a side-by-side HTML diff using table rows.

    Uses <table>/<tr>/<td> structure inspired by diff2html's
    line-by-line renderer for reliable xhtml2pdf rendering.

    Args:
        text_a:  Text from file A.
        text_b:  Text from file B.
        label_a: Column header for A side.
        label_b: Column header for B side.

    Returns:
        HTML string containing the diff table.
    """
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    rows: list[str] = []

    def _row(ln_a: str, code_a: str, cls_a: str,
             ln_b: str, code_b: str, cls_b: str) -> str:
        """Build a single <tr> with 4 <td> cells: lnA, codeA, lnB, codeB."""
        return (
            f'<tr>'
            f'<td class="ln {cls_a}">{ln_a}</td>'
            f'<td class="code {cls_a}"><pre>{code_a}</pre></td>'
            f'<td class="ln {cls_b}">{ln_b}</td>'
            f'<td class="code {cls_b}"><pre>{code_b}</pre></td>'
            f'</tr>'
        )

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for off in range(i2 - i1):
                c = html.escape(lines_a[i1 + off])
                rows.append(_row(str(i1+off+1), c, "",
                                 str(j1+off+1), c, ""))
        elif tag == "replace":
            mx = max(i2 - i1, j2 - j1)
            for off in range(mx):
                if i1 + off < i2:
                    la, ca, cla = str(i1+off+1), html.escape(lines_a[i1+off]), "del"
                else:
                    la, ca, cla = "", "", "empty"
                if j1 + off < j2:
                    lb, cb, clb = str(j1+off+1), html.escape(lines_b[j1+off]), "add"
                else:
                    lb, cb, clb = "", "", "empty"
                rows.append(_row(la, ca, cla, lb, cb, clb))
        elif tag == "delete":
            for off in range(i2 - i1):
                c = html.escape(lines_a[i1 + off])
                rows.append(_row(str(i1+off+1), c, "del", "", "", "empty"))
        elif tag == "insert":
            for off in range(j2 - j1):
                c = html.escape(lines_b[j1 + off])
                rows.append(_row("", "", "empty", str(j1+off+1), c, "add"))

    body = "\n".join(rows)
    return (
        f'<table class="difftbl">'
        f'<thead><tr>'
        f'<th class="ln">#</th>'
        f'<th class="code">{html.escape(label_a)}</th>'
        f'<th class="ln">#</th>'
        f'<th class="code">{html.escape(label_b)}</th>'
        f'</tr></thead>\n'
        f'<tbody>\n{body}\n</tbody>'
        f'</table>'
    )


# ---------------------------------------------------------------------------
# Step 5: HTML report & PDF conversion
# ---------------------------------------------------------------------------
_CSS = """\
@page {
    size: A4 landscape;
    margin: 1.2cm;
}
body {
    font-family: "Segoe UI", "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
    font-size: 10px;
    color: #1e1e1e;
    background: #fff;
}
h1 {
    font-size: 22px;
    border-bottom: 3px solid #0078d4;
    padding-bottom: 6px;
    margin-bottom: 16px;
    color: #0078d4;
}
h2 {
    font-size: 16px;
    margin-top: 28px;
    color: #333;
}
h3 {
    font-size: 13px;
    margin-top: 20px;
    color: #555;
}
/* Summary table */
table.summary {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0 20px 0;
    font-size: 10px;
}
table.summary th, table.summary td {
    border: 1px solid #ccc;
    padding: 5px 8px;
    text-align: left;
}
table.summary th {
    background: #0078d4;
    color: #fff;
    font-weight: 600;
}
table.summary tr:nth-child(even) {
    background: #f4f8fb;
}
/* ---- Side-by-side diff table (diff2html-inspired) ---- */
.difftbl {
    border-collapse: collapse;
    table-layout: fixed;
    width: 100%;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 7.5px;
    margin-bottom: 20px;
}
.difftbl th, .difftbl td {
    border: 1px solid #ddd;
    padding: 1px 3px;
    vertical-align: top;
    word-wrap: break-word;
    overflow: hidden;
}
.difftbl thead th {
    background: #444;
    color: #fff;
    font-weight: bold;
    font-size: 8px;
    padding: 3px 4px;
    text-align: left;
}
/* Line-number columns — narrow fixed width */
.ln {
    width: 28px;
    text-align: right;
    color: #999;
    background: #f5f5f5;
    font-size: 7px;
    padding-right: 4px;
}
.difftbl thead th.ln {
    background: #444;
    color: #fff;
    text-align: center;
}
/* Code columns — fill remaining width equally */
.code {
    white-space: pre-wrap;
    word-wrap: break-word;
}
.code pre {
    margin: 0;
    padding: 0;
    font-size: inherit;
    font-family: inherit;
    white-space: pre-wrap;
    word-wrap: break-word;
}
/* Diff row colours — from diff2html CSS variables */
.del { background: #fee8e9; }   /* d2h-del-bg-color */
.add { background: #dfd; }      /* d2h-ins-bg-color */
.empty { background: #f1f1f1; } /* d2h-empty-placeholder-bg-color */
/* Unmatched file list */
ul.unmatched {
    font-size: 11px;
    color: #a00;
}
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: bold;
    color: #fff;
}
.badge-high { background: #28a745; }
.badge-mid  { background: #ffc107; color: #333; }
.badge-low  { background: #dc3545; }
.meta {
    font-size: 11px;
    color: #777;
    margin-bottom: 20px;
}
"""


def _ratio_badge(ratio: float) -> str:
    """Return an HTML badge span for a similarity ratio."""
    pct = ratio * 100
    if pct >= 80:
        cls = "badge-high"
    elif pct >= 50:
        cls = "badge-mid"
    else:
        cls = "badge-low"
    return f'<span class="badge {cls}">{pct:.1f}%</span>'


def _html_wrap(title: str, body: str) -> str:
    """Wrap body content in a full HTML document with CSS."""
    return f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
{_CSS}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def build_cover_html(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    compare_comment: bool,
) -> str:
    """Build the cover-page HTML with summary table and matching map.

    Args:
        results:         List of DiffResult objects.
        unmatched_a:     Files only in dir_a.
        unmatched_b:     Files only in dir_b.
        dir_a / dir_b:   Directory paths.
        by_word:         Whether word-level comparison was used.
        compare_comment: Whether comments were included.

    Returns:
        Full HTML string for the cover page.
    """
    unit = "word" if by_word else "line"
    comment_mode = "included" if compare_comment else "excluded"

    # Summary table rows
    summary_rows = ""
    for idx, r in enumerate(results, 1):
        badge = _ratio_badge(r.ratio)
        err = f' <em style="color:red">({html.escape(r.error)})</em>' if r.error else ""
        summary_rows += (
            f"<tr>"
            f"<td>{idx}</td>"
            f"<td>{html.escape(r.match.rel_path_a)}</td>"
            f"<td>{html.escape(r.match.rel_path_b)}</td>"
            f"<td>{r.match.similarity:.1f}</td>"
            f"<td>{badge}{err}</td>"
            f"<td style='color:green'>+{r.additions}</td>"
            f"<td style='color:red'>-{r.deletions}</td>"
            f"</tr>\n"
        )

    # Unmatched lists
    unmatched_html = ""
    if unmatched_a or unmatched_b:
        unmatched_html += "<h2>Unmatched Files</h2>\n"
        if unmatched_a:
            unmatched_html += f"<h3>Only in A ({html.escape(dir_a)})</h3>\n<ul class='unmatched'>\n"
            for f in unmatched_a:
                unmatched_html += f"  <li>{html.escape(f)}</li>\n"
            unmatched_html += "</ul>\n"
        if unmatched_b:
            unmatched_html += f"<h3>Only in B ({html.escape(dir_b)})</h3>\n<ul class='unmatched'>\n"
            for f in unmatched_b:
                unmatched_html += f"  <li>{html.escape(f)}</li>\n"
            unmatched_html += "</ul>\n"

    body = f"""\
<h1>Diffinite &mdash; Source Code Diff Report</h1>
<p class="meta">
  <strong>Dir A:</strong> {html.escape(dir_a)}<br>
  <strong>Dir B:</strong> {html.escape(dir_b)}<br>
  <strong>Comparison unit:</strong> {unit} &nbsp;|&nbsp;
  <strong>Comments:</strong> {comment_mode} &nbsp;|&nbsp;
  <strong>Matched pairs:</strong> {len(results)} &nbsp;|&nbsp;
  <strong>Unmatched:</strong> {len(unmatched_a)} (A) / {len(unmatched_b)} (B)
</p>

<h2>Summary</h2>
<table class="summary">
<tr>
  <th>#</th><th>File A</th><th>File B</th><th>Name Sim.</th>
  <th>Content Match</th><th>Added</th><th>Deleted</th>
</tr>
{summary_rows}
</table>

{unmatched_html}
"""
    return _html_wrap("Diffinite — Cover", body)


def build_diff_page_html(
    result: DiffResult,
    index: int,
    unit: str,
) -> str:
    """Build a single-file diff page HTML.

    Args:
        result: DiffResult for this file pair.
        index:  1-based index of this pair.
        unit:   "word" or "line".

    Returns:
        Full HTML string for one diff page.
    """
    r = result
    if r.error:
        body = (
            f"<h2>{index}. {html.escape(r.match.rel_path_a)} &harr; "
            f"{html.escape(r.match.rel_path_b)}</h2>\n"
            f"<p style='color:red'>Error: {html.escape(r.error)}</p>\n"
        )
    else:
        body = (
            f"<h2>{index}. {html.escape(r.match.rel_path_a)} &harr; "
            f"{html.escape(r.match.rel_path_b)}</h2>\n"
            f"<p>Match ratio: {_ratio_badge(r.ratio)} &nbsp; "
            f"<span style='color:green'>+{r.additions} {unit}(s)</span> &nbsp; "
            f"<span style='color:red'>-{r.deletions} {unit}(s)</span></p>\n"
            f"{r.html_diff}\n"
        )
    return _html_wrap(
        f"Diff — {r.match.rel_path_a}",
        body,
    )


def html_to_pdf(html_content: str, output_path: str) -> bool:
    """Convert an HTML string to a PDF file via xhtml2pdf.

    Args:
        html_content: Full HTML document string.
        output_path:  Destination PDF file path.

    Returns:
        True if the PDF was created successfully, False otherwise.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "w+b") as fh:
        status = pisa.CreatePDF(html_content, dest=fh)
    if status.err:
        logger.error("PDF conversion error for %s", output_path)
        return False
    return True


def merge_pdfs(pdf_paths: list[str], output_path: str) -> None:
    """Merge multiple PDF files into a single output PDF.

    Args:
        pdf_paths:   Ordered list of PDF file paths to merge.
        output_path: Destination merged PDF file path.
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    for p in pdf_paths:
        if Path(p).exists() and Path(p).stat().st_size > 0:
            writer.append(p)
        else:
            logger.warning("Skipping empty or missing PDF: %s", p)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "wb") as fh:
        writer.write(fh)
    writer.close()
    logger.info("Merged PDF saved → %s (%d bytes)", out.resolve(), out.stat().st_size)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_pipeline(
    dir_a: str,
    dir_b: str,
    by_word: bool = False,
    compare_comment: bool = True,
    output_pdf: str = "report.pdf",
    threshold: float = FUZZY_THRESHOLD,
) -> None:
    """Execute the full diff-to-PDF pipeline.

    Uses divide-and-conquer: generates a cover PDF and individual per-file
    diff PDFs, then merges them into the final output.

    Args:
        dir_a:           Path to the original source directory.
        dir_b:           Path to the comparison source directory.
        by_word:         True for word-level comparison; False for line-level.
        compare_comment: True to include comments; False to strip before diff.
        output_pdf:      Output PDF file path.
        threshold:       Fuzzy matching threshold (0–100).
    """
    import tempfile

    # Step 1 — collect & match
    logger.info("Step 1: Collecting files …")
    files_a = collect_files(dir_a)
    files_b = collect_files(dir_b)
    logger.info("  Dir A: %d files  |  Dir B: %d files", len(files_a), len(files_b))

    matches, unmatched_a, unmatched_b = match_files(files_a, files_b, threshold=threshold)
    logger.info("  Matched pairs: %d  |  Unmatched A: %d  |  Unmatched B: %d",
                len(matches), len(unmatched_a), len(unmatched_b))

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
            text_a = strip_comments(text_a, ext)
            text_b = strip_comments(text_b, ext)

        ratio, additions, deletions = compute_diff(text_a, text_b, by_word)

        html_diff = generate_html_diff(
            text_a, text_b,
            label_a=m.rel_path_a,
            label_b=m.rel_path_b,
        )

        results.append(DiffResult(
            match=m,
            ratio=ratio,
            additions=additions,
            deletions=deletions,
            html_diff=html_diff,
        ))

    # Step 5 — divide-and-conquer PDF generation
    logger.info("Step 5: Generating PDFs (divide-and-conquer) …")

    with tempfile.TemporaryDirectory(prefix="diffinite_") as tmpdir:
        pdf_parts: list[str] = []

        # (1) Cover page
        cover_html = build_cover_html(
            results, unmatched_a, unmatched_b,
            dir_a, dir_b, by_word, compare_comment,
        )
        cover_pdf = os.path.join(tmpdir, "00_cover.pdf")
        if html_to_pdf(cover_html, cover_pdf):
            pdf_parts.append(cover_pdf)
            logger.info("  Cover page → OK")

        # (2) Per-file diff pages
        for idx, r in enumerate(results, 1):
            diff_html = build_diff_page_html(r, idx, unit)
            diff_pdf = os.path.join(tmpdir, f"{idx:03d}_diff.pdf")
            if html_to_pdf(diff_html, diff_pdf):
                pdf_parts.append(diff_pdf)
                logger.info("  Diff page %d (%s) → OK", idx, r.match.rel_path_a)
            else:
                logger.warning("  Diff page %d FAILED", idx)

        # (3) Merge all
        if pdf_parts:
            merge_pdfs(pdf_parts, output_pdf)
        else:
            logger.error("No PDF parts were generated — cannot create report")

    logger.info("Done ✓")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Parse arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="Diffinite PoC — Compare two source directories and generate a PDF diff report.",
    )
    parser.add_argument("dir_a", help="Path to the original source directory (A)")
    parser.add_argument("dir_b", help="Path to the comparison source directory (B)")
    parser.add_argument(
        "--output-pdf", "-o",
        default="report.pdf",
        help="Output PDF file path (default: report.pdf)",
    )
    parser.add_argument(
        "--by-word",
        action="store_true",
        default=False,
        help="Compare by word instead of by line",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        default=False,
        help="Strip comments before comparison",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=FUZZY_THRESHOLD,
        help=f"Fuzzy matching threshold (0–100, default: {FUZZY_THRESHOLD})",
    )

    args = parser.parse_args()

    run_pipeline(
        dir_a=args.dir_a,
        dir_b=args.dir_b,
        by_word=args.by_word,
        compare_comment=not args.no_comments,
        output_pdf=args.output_pdf,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()

