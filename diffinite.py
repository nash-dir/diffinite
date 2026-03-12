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
# Base CSS without @page (the @page rule is built dynamically per document)
_CSS_BODY = """\
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
/* ---- Annotation frame styles ---- */
.footer-table {
    width: 100%;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 8px;
    color: #888;
    border: none;
}
.footer-table td {
    border: none;
    padding: 0;
    vertical-align: bottom;
}
.header-filename {
    text-align: right;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 7px;
    color: #aaa;
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


def _html_wrap(
    title: str,
    body: str,
    annotation_html: str = "",
    *,
    has_footer: bool = False,
    has_header: bool = False,
) -> str:
    """Wrap body content in a full HTML document with CSS.

    Dynamically builds the @page CSS rule with optional @frame blocks
    for footer and header annotations that repeat on every page.

    Args:
        title:           Page title.
        body:            Main HTML body content.
        annotation_html: Annotation divs with IDs matching frame names.
        has_footer:      If True, add a footer @frame to @page.
        has_header:      If True, add a header @frame to @page.

    Returns:
        Full HTML document string.
    """
    margin_bottom = "2cm" if has_footer else "1.2cm"
    margin_top = "2cm" if has_header else "1.2cm"

    frames = ""
    if has_footer:
        frames += """
    @frame footer_frame {
        -pdf-frame-content: pageFooter;
        left: 1.2cm;
        right: 1.2cm;
        bottom: 0.2cm;
        height: 1cm;
    }"""
    if has_header:
        frames += """
    @frame header_frame {
        -pdf-frame-content: pageHeader;
        left: 1.2cm;
        right: 1.2cm;
        top: 0.2cm;
        height: 1cm;
    }"""

    page_css = f"""@page {{
    size: A4 landscape;
    margin: {margin_top} 1.2cm {margin_bottom} 1.2cm;{frames}
}}"""

    return f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
{page_css}
{_CSS_BODY}
</style>
</head>
<body>
{annotation_html}
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


def _build_annotation_html(
    *,
    show_page_number: bool = False,
    show_file_number: bool = False,
    file_index: int = 0,
    total_files: int = 0,
    show_filename: bool = False,
    filename: str = "",
) -> tuple[str, bool, bool]:
    """Build annotation divs using xhtml2pdf @frame mechanism.

    Returns div elements whose IDs match @frame `-pdf-frame-content`
    names, so xhtml2pdf renders them on every page.

    Args:
        show_page_number: Render 'Page n / N' at footer right.
        show_file_number: Render 'File n / N' at footer left.
        file_index:       1-based index of the current file.
        total_files:      Total number of matched file pairs.
        show_filename:    Render filename at header right.
        filename:         Filename string to display.

    Returns:
        Tuple of (annotation_html, has_footer, has_header).
    """
    parts: list[str] = []
    has_footer = show_page_number or show_file_number
    has_header = show_filename and bool(filename)

    if has_footer:
        left_cell = ""
        right_cell = ""
        if show_file_number and total_files > 0:
            left_cell = f'File {file_index} / {total_files}'
        if show_page_number:
            right_cell = 'Page <pdf:pagenumber> / <pdf:pagecount>'
        parts.append(
            f'<div id="pageFooter">'
            f'<table class="footer-table"><tr>'
            f'<td style="text-align:left;">{left_cell}</td>'
            f'<td style="text-align:center;"></td>'  # Bates placeholder (added post-hoc)
            f'<td style="text-align:right;">{right_cell}</td>'
            f'</tr></table>'
            f'</div>'
        )

    if has_header:
        parts.append(
            f'<div id="pageHeader">'
            f'<p class="header-filename">{html.escape(filename)}</p>'
            f'</div>'
        )

    return "\n".join(parts), has_footer, has_header


def build_diff_page_html(
    result: DiffResult,
    index: int,
    unit: str,
    *,
    show_page_number: bool = False,
    show_file_number: bool = False,
    total_files: int = 0,
    show_filename: bool = False,
) -> str:
    """Build a single-file diff page HTML.

    Args:
        result:           DiffResult for this file pair.
        index:            1-based index of this pair.
        unit:             "word" or "line".
        show_page_number: Add page number annotation.
        show_file_number: Add file sequence annotation.
        total_files:      Total number of file pairs.
        show_filename:    Add filename annotation.

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
    annotation_html, has_footer, has_header = _build_annotation_html(
        show_page_number=show_page_number,
        show_file_number=show_file_number,
        file_index=index,
        total_files=total_files,
        show_filename=show_filename,
        filename=r.match.rel_path_a,
    )
    return _html_wrap(
        f"Diff — {r.match.rel_path_a}",
        body,
        annotation_html=annotation_html,
        has_footer=has_footer,
        has_header=has_header,
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


def add_bates_numbers(input_path: str, output_path: str) -> None:
    """Stamp Bates numbers on each page of a merged PDF.

    Uses reportlab to create an overlay with Bates numbers at the
    bottom-center of each page, then merges the overlay onto the
    original pages.

    Args:
        input_path:  Path to the input merged PDF.
        output_path: Path to the stamped output PDF.
    """
    import io

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas

    reader = PdfReader(input_path)
    writer = PdfWriter()
    total_pages = len(reader.pages)
    digits = max(4, len(str(total_pages)))

    for i, page in enumerate(reader.pages):
        # Get page dimensions
        box = page.mediabox
        pw = float(box.width)
        ph = float(box.height)

        # Create an overlay PDF in memory
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        bates = str(i + 1).zfill(digits)
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawCentredString(pw / 2, 18, bates)
        c.save()
        buf.seek(0)

        # Merge overlay onto the original page
        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "wb") as fh:
        writer.write(fh)
    writer.close()
    logger.info("Bates numbers added → %s", out.resolve())


def _stamp_bates_inplace(pdf_path: str, start_number: int, digits: int) -> None:
    """Stamp Bates numbers on a single PDF file in-place.

    Args:
        pdf_path:     Path to the PDF to stamp.
        start_number: 0-based starting page number for Bates sequence.
        digits:       Number of zero-padded digits.
    """
    import io

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        box = page.mediabox
        pw = float(box.width)
        ph = float(box.height)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        bates = str(start_number + i + 1).zfill(digits)
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawCentredString(pw / 2, 18, bates)
        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    writer.close()


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
    *,
    no_merge: bool = False,
    show_page_number: bool = False,
    show_file_number: bool = False,
    show_bates_number: bool = False,
    show_filename: bool = False,
) -> None:
    """Execute the full diff-to-PDF pipeline.

    Uses divide-and-conquer: generates a cover PDF and individual per-file
    diff PDFs, then optionally merges them into the final output.

    Args:
        dir_a:             Path to the original source directory.
        dir_b:             Path to the comparison source directory.
        by_word:           True for word-level comparison; False for line-level.
        compare_comment:   True to include comments; False to strip before diff.
        output_pdf:        Output PDF file path.
        threshold:         Fuzzy matching threshold (0–100).
        no_merge:          If True, output individual PDFs instead of merging.
        show_page_number:  If True, stamp 'Page n / N' at bottom-right.
        show_file_number:  If True, stamp 'File n / N' at bottom-left.
        show_bates_number: If True, stamp Bates numbers at bottom-center (merged only).
        show_filename:     If True, stamp filename at top-right.
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

    total_files = len(results)

    # Step 5 — divide-and-conquer PDF generation
    logger.info("Step 5: Generating PDFs (divide-and-conquer) …")

    # Determine output directory for no-merge mode
    if no_merge:
        out_stem = Path(output_pdf).stem
        out_dir = Path(output_pdf).parent / f"{out_stem}_files"
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info("  No-merge mode — individual PDFs → %s", out_dir.resolve())

    with tempfile.TemporaryDirectory(prefix="diffinite_") as tmpdir:
        pdf_parts: list[str] = []

        # (1) Cover page
        cover_html = build_cover_html(
            results, unmatched_a, unmatched_b,
            dir_a, dir_b, by_word, compare_comment,
        )
        if no_merge:
            cover_dest = str(out_dir / "000_cover.pdf")
        else:
            cover_dest = os.path.join(tmpdir, "00_cover.pdf")
        if html_to_pdf(cover_html, cover_dest):
            pdf_parts.append(cover_dest)
            logger.info("  Cover page → OK")

        # (2) Per-file diff pages
        for idx, r in enumerate(results, 1):
            diff_html = build_diff_page_html(
                r, idx, unit,
                show_page_number=show_page_number,
                show_file_number=show_file_number,
                total_files=total_files,
                show_filename=show_filename,
            )
            # Determine destination path
            safe_name = Path(r.match.rel_path_a).name.replace(" ", "_")
            if no_merge:
                diff_dest = str(out_dir / f"{idx:03d}_{safe_name}.pdf")
            else:
                diff_dest = os.path.join(tmpdir, f"{idx:03d}_diff.pdf")
            if html_to_pdf(diff_html, diff_dest):
                pdf_parts.append(diff_dest)
                logger.info("  Diff page %d (%s) → OK", idx, r.match.rel_path_a)
            else:
                logger.warning("  Diff page %d FAILED", idx)

        # (3) Merge or skip
        if no_merge:
            # (4) Bates numbers for individual PDFs
            if show_bates_number and pdf_parts:
                logger.info("  Stamping Bates numbers on individual PDFs …")
                global_page = 0
                # Count total pages across all PDFs first
                from pypdf import PdfReader as _PR
                page_counts = []
                for p in pdf_parts:
                    try:
                        page_counts.append(len(_PR(p).pages))
                    except Exception:
                        page_counts.append(0)
                total_global_pages = sum(page_counts)
                digits = max(4, len(str(total_global_pages)))
                for p, pc in zip(pdf_parts, page_counts):
                    if pc == 0:
                        continue
                    _stamp_bates_inplace(p, global_page, digits)
                    global_page += pc
            logger.info("  No-merge mode — %d PDFs saved to %s", len(pdf_parts), out_dir.resolve())
        elif pdf_parts:
            merge_pdfs(pdf_parts, output_pdf)
            # (4) Bates numbers (only for merged PDFs)
            if show_bates_number:
                logger.info("  Stamping Bates numbers …")
                bates_tmp = os.path.join(tmpdir, "bates_tmp.pdf")
                os.replace(output_pdf, bates_tmp)
                add_bates_numbers(bates_tmp, output_pdf)
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
    parser.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        help="Generate individual PDFs per file instead of one merged PDF",
    )
    parser.add_argument(
        "--page-number",
        action="store_true",
        default=False,
        help="Show 'Page n / N' at the bottom-right of each page",
    )
    parser.add_argument(
        "--file-number",
        action="store_true",
        default=False,
        help="Show 'File n / N' at the bottom-left of each page",
    )
    parser.add_argument(
        "--bates-number",
        action="store_true",
        default=False,
        help="Stamp Bates numbers at the bottom-center of each page (merged mode only)",
    )
    parser.add_argument(
        "--show-filename",
        action="store_true",
        default=False,
        help="Show the filename at the top-right of each page",
    )

    args = parser.parse_args()


    run_pipeline(
        dir_a=args.dir_a,
        dir_b=args.dir_b,
        by_word=args.by_word,
        compare_comment=not args.no_comments,
        output_pdf=args.output_pdf,
        threshold=args.threshold,
        no_merge=args.no_merge,
        show_page_number=args.page_number,
        show_file_number=args.file_number,
        show_bates_number=args.bates_number,
        show_filename=args.show_filename,
    )


if __name__ == "__main__":
    main()

