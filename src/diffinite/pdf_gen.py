"""PDF 생성, TOC 북마크, Bates 번호 부여.

법정 제출용 PDF 보고서 생성 파이프라인.

구현:
    - ``xhtml2pdf``: HTML -> PDF 변환. CSS subset만 지원 (@page, @frame).
    - ``pypdf``: Divide-and-Conquer 병합. 파일별 개별 PDF -> 최종 통합.
    - ``reportlab``: Bates 번호 오버레이 (각 페이지 하단 중앙).
    - 북마크: 계층적 TOC (Cover -> 파일별 Diff -> Deep Compare).

CSS 설계:
    ``_CSS_BODY``에 모든 스타일을 중앙 집중. xhtml2pdf는 최신 CSS를
    지원하지 않으므로, 인라인 스타일과 테이블 레이아웃 사용.
    font-family는 한글 폰트(Noto Sans KR, Malgun Gothic) 포함.

라인 번호 열 너비:
    ``differ.py``의 ``_calc_ln_width()``가 산정한 동적 너비를 사용.
    긴 파일(10,000줄+)에서 라인 번호 열이 넘치는 것을 방지.

호출관계:
    ``pipeline._generate_pdf_report()`` -> ``build_cover_body()``
    ``pipeline._generate_pdf_report()`` -> ``build_diff_page_html()``
    ``pipeline._generate_pdf_report()`` -> ``html_to_pdf()``
    ``pipeline._generate_pdf_report()`` -> ``merge_with_bookmarks()``
    ``pipeline._generate_pdf_report()`` -> ``add_bates_numbers()``
"""

from __future__ import annotations

import html
import io
import logging
import os
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from xhtml2pdf import pisa

from diffinite.models import DeepMatchResult, DiffResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSS (shared across all generated pages)
# ---------------------------------------------------------------------------
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
/* ---- Side-by-side diff table ---- */
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
.ln {
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
.del { background: #fee8e9; }
.add { background: #dfd; }
.empty { background: #f1f1f1; }
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
/* Deep Compare table */
table.deep {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0 20px 0;
    font-size: 9px;
}
table.deep th, table.deep td {
    border: 1px solid #ccc;
    padding: 4px 6px;
    text-align: left;
}
table.deep th {
    background: #6c5ce7;
    color: #fff;
    font-weight: 600;
}
table.deep tr:nth-child(even) {
    background: #f0eef9;
}
/* Annotation frames */
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
    """Wrap body content in a full HTML document with CSS."""
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


def _build_annotation_html(
    *,
    show_page_number: bool = False,
    show_file_number: bool = False,
    file_index: int = 0,
    total_files: int = 0,
    show_filename: bool = False,
    filename: str = "",
) -> tuple[str, bool, bool]:
    """Build annotation divs for xhtml2pdf @frame mechanism."""
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
            f'<td style="text-align:center;"></td>'
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


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------
def build_cover_body(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    compare_comment: bool,
    *,
    deep_results: Optional[list[DeepMatchResult]] = None,
    metadata: Optional["AnalysisMetadata"] = None,
) -> str:
    """Build the cover-page body fragment (no DOCTYPE/html/head wrapper)."""
    from diffinite.models import AnalysisMetadata as _AM  # avoid circular at module level

    unit = "word" if by_word else "line"
    comment_mode = "included" if compare_comment else "excluded"

    # Analysis metadata banner (transparency)
    meta_html = ""
    if metadata is not None:
        meta_html = (
            '<div style="border:2px solid #0078d4;border-radius:6px;'
            'padding:10px 16px;margin-bottom:20px;'
            'background:#f0f7ff;font-size:11px;">\n'
            '<strong>&#128203; Analysis Configuration</strong><br>\n'
            f'<strong>Mode:</strong> {html.escape(metadata.exec_mode)} &nbsp;|&nbsp; '
            f'<strong>K=</strong>{metadata.k}, <strong>W=</strong>{metadata.w}, '
            f'<strong>T=</strong>{metadata.threshold:.2f}'
            + '\n</div>\n'
        )

    summary_rows = ""
    for idx, r in enumerate(results, 1):
        badge = _ratio_badge(r.ratio)
        err = (
            f' <em style="color:red">({html.escape(r.error)})</em>'
            if r.error else ""
        )
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
            unmatched_html += (
                f"<h3>Only in A ({html.escape(dir_a)})</h3>\n"
                "<ul class='unmatched'>\n"
            )
            for f in unmatched_a:
                unmatched_html += f"  <li>{html.escape(f)}</li>\n"
            unmatched_html += "</ul>\n"
        if unmatched_b:
            unmatched_html += (
                f"<h3>Only in B ({html.escape(dir_b)})</h3>\n"
                "<ul class='unmatched'>\n"
            )
            for f in unmatched_b:
                unmatched_html += f"  <li>{html.escape(f)}</li>\n"
            unmatched_html += "</ul>\n"

    deep_html = ""
    if deep_results:
        deep_html += "<h2>Deep Compare &mdash; N:M Cross-Match Results</h2>\n"
        deep_html += (
            '<table class="deep">'
            "<tr><th>A File</th><th>B File(s)</th>"
            "<th>Shared Hashes</th><th>Jaccard</th></tr>\n"
        )
        for dr in deep_results:
            for b_file, shared, jaccard in dr.matched_files_b:
                jbadge = _ratio_badge(jaccard)
                deep_html += (
                    f"<tr>"
                    f"<td>{html.escape(dr.file_a)}</td>"
                    f"<td>{html.escape(b_file)}</td>"
                    f"<td>{shared}</td>"
                    f"<td>{jbadge}</td>"
                    f"</tr>\n"
                )
        deep_html += "</table>\n"

    body = f"""\
<h1>Diffinite &mdash; Source Code Diff Report</h1>
{meta_html}
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
{deep_html}
"""
    return body


# ---------------------------------------------------------------------------
# Diff page
# ---------------------------------------------------------------------------
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
    """Build a single-file diff page HTML."""
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


# ---------------------------------------------------------------------------
# HTML → PDF
# ---------------------------------------------------------------------------
def html_to_pdf(html_content: str, output_path: str) -> bool:
    """Convert an HTML string to a PDF file via xhtml2pdf."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "w+b") as fh:
        status = pisa.CreatePDF(html_content, dest=fh)
    if status.err:
        logger.error("PDF conversion error for %s", output_path)
        return False
    return True


# ---------------------------------------------------------------------------
# Merge with bookmarks
# ---------------------------------------------------------------------------
def merge_with_bookmarks(
    cover_pdf: str,
    diff_pdfs: list[tuple[str, DiffResult]],
    output_path: str,
    *,
    deep_pdf: Optional[str] = None,
) -> None:
    """Merge PDFs and insert hierarchical bookmarks (TOC).

    Args:
        cover_pdf:  Path to the cover page PDF.
        diff_pdfs:  List of ``(pdf_path, DiffResult)`` tuples.
        output_path: Final merged PDF destination.
        deep_pdf:   Optional path to the deep-compare summary PDF.
    """
    writer = PdfWriter()
    page_offset = 0

    # Cover page
    if Path(cover_pdf).exists() and Path(cover_pdf).stat().st_size > 0:
        reader = PdfReader(cover_pdf)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item("Cover — Summary", page_offset)
        page_offset += len(reader.pages)

    # Diff pages with bookmarks
    for pdf_path, result in diff_pdfs:
        if not Path(pdf_path).exists() or Path(pdf_path).stat().st_size == 0:
            logger.warning("Skipping empty or missing PDF: %s", pdf_path)
            continue

        reader = PdfReader(pdf_path)
        for page in reader.pages:
            writer.add_page(page)

        label = f"{result.match.rel_path_a} ↔ {result.match.rel_path_b}"
        writer.add_outline_item(label, page_offset)
        page_offset += len(reader.pages)

    # Deep compare page
    if deep_pdf and Path(deep_pdf).exists() and Path(deep_pdf).stat().st_size > 0:
        reader = PdfReader(deep_pdf)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item("Deep Compare — N:M Cross-Match", page_offset)
        page_offset += len(reader.pages)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "wb") as fh:
        writer.write(fh)
    writer.close()
    logger.info("Merged PDF with bookmarks → %s (%d bytes)",
                out.resolve(), out.stat().st_size)


# ---------------------------------------------------------------------------
# Bates numbering
# ---------------------------------------------------------------------------
def add_bates_numbers(input_path: str, output_path: str) -> None:
    """Stamp Bates numbers on each page of a merged PDF.

    Preserves existing bookmarks/outline by cloning the full document
    before overlaying Bates numbers.
    """
    reader = PdfReader(input_path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    total_pages = len(writer.pages)
    digits = max(4, len(str(total_pages)))

    for i, page in enumerate(writer.pages):
        box = page.mediabox
        pw = float(box.width)
        ph = float(box.height)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        bates = str(i + 1).zfill(digits)
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawCentredString(pw / 2, 18, bates)
        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "wb") as fh:
        writer.write(fh)
    writer.close()
    logger.info("Bates numbers added → %s", out.resolve())


def stamp_bates_inplace(pdf_path: str, start_number: int, digits: int) -> None:
    """Stamp Bates numbers on a single PDF file in-place."""
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
