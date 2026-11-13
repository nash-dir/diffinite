"""Regression tests for the third polish round of the PDF and HTML diff rendering.

Each test names the review item it guards.
"""

from __future__ import annotations

import re

import pytest

from diffinite import pdf_gen
from diffinite.differ import _highlight_word_diff, generate_html_diff
from diffinite.models import DiffResult, FileMatch


def _diff(text_a: str, text_b: str, **kw) -> str:
    return generate_html_diff(text_a, text_b, "a.py", "b.py", ln_col_width=28, **kw)


# ---------------------------------------------------------------------------
# Visual #1: browsers take column widths from <colgroup>, not the rule row
# ---------------------------------------------------------------------------
def test_ruled_table_declares_header_widths_in_colgroup():
    header = '<tr><th style="width: 5%;">#</th><th style="width: 95%;">File</th></tr>\n'
    out = pdf_gen.ruled_table("summary", 2, ["<tr><td>1</td><td>x</td></tr>\n"], header)
    assert '<colgroup><col style="width: 5%;"><col style="width: 95%;"></colgroup>' in out
    # The colgroup comes before the first (spanning) rule row.
    assert out.index("<colgroup>") < out.index('<tr class="rule">')


def test_kv_table_declares_widths_from_its_first_row():
    out = pdf_gen.kv_table_html([("Label", "Value")])
    assert '<col style="width: 22%;"><col style="width: 78%;">' in out


def test_diff_table_declares_line_number_widths():
    out = pdf_gen._prepare_diff_table(_diff("a\n", "b\n"))
    m = re.search(r'<table class="difftbl"[^>]*><colgroup>(.*?)</colgroup>', out)
    assert m, out[:300]
    assert m.group(1) == '<col style="width: 28px;"><col><col style="width: 28px;"><col>'


# ---------------------------------------------------------------------------
# Visual #2 and #4: CJK tops and inline backgrounds stay inside the row
# ---------------------------------------------------------------------------
def test_diff_cells_have_top_padding_for_cjk_ascent():
    m = re.search(r"\.difftbl th, \.difftbl td \{[^}]*padding: ([0-9.]+)pt", pdf_gen._CSS_BODY)
    assert m and float(m.group(1)) >= 1.5


def test_vertical_borders_get_butt_caps():
    from xhtml2pdf.tables import TableData

    td = TableData()
    td.add_style(("LINEBEFORE", (0, 0), (0, 0), 2, "black", "squared"))
    td.add_style(("LINEABOVE", (0, 0), (0, 0), 1, "black", "squared"))
    assert td.styles[0][5] == "butt"  # no stub into the next row
    assert td.styles[1][5] == "squared"  # horizontal rules unchanged


# ---------------------------------------------------------------------------
# Visual #3: a hanging closing bracket stays inside the code cell
# ---------------------------------------------------------------------------
def test_code_cells_keep_room_for_hanging_punctuation():
    m = re.search(r"\.difftbl td\.code \{ padding-right: ([0-9.]+)pt; \}", pdf_gen._CSS_BODY)
    assert m and float(m.group(1)) >= pdf_gen._PDF_CODE_ADVANCE_PT


# ---------------------------------------------------------------------------
# Visual #6: hanging indent follows the line's own indentation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "inner, cols",
    [("x = 1", 0), ("    x", 4), ("\tx", 8), ("&nbsp;&nbsp;<span>x</span>", 2), ("  \t x", 9)],
)
def test_leading_columns(inner, cols):
    assert pdf_gen._leading_columns(inner) == cols


def test_hanging_indent_starts_after_parent_indentation():
    html_out = pdf_gen._prepare_diff_table(_diff("        x = 1\n", "        y = 2\n"))
    assert '<pre style="padding-left: 10ch; text-indent: -10ch;">' in html_out
    pdf_out = pdf_gen._prepare_diff_table(_diff("        x = 1\n", "        y = 2\n"), for_pdf=True)
    width = f"{10 * pdf_gen._PDF_CODE_ADVANCE_PT:.2f}pt"
    assert f'<pre style="padding-left: {width}; text-indent: -{width};">' in pdf_out
    # Unindented lines keep the stylesheet's two-character indent.
    plain = pdf_gen._prepare_diff_table(_diff("x\n", "y\n"))
    assert "<pre>" in plain and "padding-left" not in plain.split("<tbody>")[1]


def test_hanging_indent_is_capped():
    out = pdf_gen._hanging_indent_style(" " * 200 + "x", for_pdf=False)
    n = pdf_gen._HANG_MAX_INDENT + pdf_gen._HANG_EXTRA_CHARS
    assert out == f' style="padding-left: {n}ch; text-indent: -{n}ch;"'


def test_block_background_patch_is_installed():
    from xhtml2pdf.xhtml2pdf_reportlab import PmlParagraph

    assert getattr(PmlParagraph.draw, "_diffinite_hang", False)


def test_hanging_indent_paragraph_draws_no_block_background(tmp_path):
    """The row tint of a wrapped, indented line stays inside the table."""
    fitz = pytest.importorskip("fitz")
    long_line = "        " + "word " * 80
    html_diff = _diff("a\n", long_line + "\n")
    r = DiffResult(FileMatch("a.py", "b.py", 100.0), 0.0, 1, 1, html_diff)
    page = pdf_gen.build_diff_page_html(r, 1, "line")
    out = tmp_path / "p.pdf"
    assert pdf_gen.html_to_pdf(page, str(out))
    doc = fitz.open(str(out))
    right_edge = max(
        d["rect"].x1 for d in doc[0].get_drawings() if d.get("color") and d["rect"].height == 0
    )
    fills = [d["rect"] for d in doc[0].get_drawings() if d.get("fill")]
    assert fills and max(f.x1 for f in fills) <= right_edge + 0.01


# ---------------------------------------------------------------------------
# Visual #7: changed whitespace is tinted, never struck or underlined
# ---------------------------------------------------------------------------
def test_whitespace_only_change_uses_ws_class():
    a, b = _highlight_word_diff("    x = 1", "\tx = 1")
    assert '<span class="word-del ws">    </span>' in a
    assert '<span class="word-add ws">\t</span>' in b


def test_ws_style_has_no_text_decoration():
    m = re.search(r"\.ws \{([^}]*)\}", pdf_gen._CSS_BODY)
    assert m and "text-decoration: none" in m.group(1)
    # .ws comes after the word marks, so it wins at equal specificity.
    assert pdf_gen._CSS_BODY.index(".ws {") > pdf_gen._CSS_BODY.index(".word-add {")


def test_key_lists_whitespace_change_separately():
    key = pdf_gen.diff_key_html(_diff("    x = 1\n", "\tx = 1\n", by_word=True))
    assert "Whitespace changed" in key
    assert "Text only in A" not in key and "Text only in B" not in key
    key2 = pdf_gen.diff_key_html(_diff("x = 1\n", "y = 1\n", by_word=True))
    assert "Text only in A" in key2 and "Whitespace changed" not in key2


# ---------------------------------------------------------------------------
# Visual #11: rows with no counterpart line carry a cue
# ---------------------------------------------------------------------------
def test_empty_rows_carry_a_visible_cue():
    # Print: white cells ruled above and below (xhtml2pdf cannot draw dotted rules);
    # screen: a light hatch. Both differ from the change tints in greyscale.
    assert re.search(r"td\.empty \{[^}]*border-top: 0\.5pt solid", pdf_gen._CSS_BODY)
    assert "repeating-linear-gradient" in pdf_gen._CSS_SCREEN


# ---------------------------------------------------------------------------
# Copy #5 and #11: column name and bookmark name
# ---------------------------------------------------------------------------
def test_deep_compare_bookmark_equals_heading(tmp_path):
    from pypdf import PdfReader, PdfWriter

    blank = tmp_path / "b.pdf"
    w = PdfWriter()
    w.add_blank_page(100, 100)
    with open(blank, "wb") as fh:
        w.write(fh)
    out = tmp_path / "m.pdf"
    pdf_gen.merge_with_bookmarks(str(blank), [], str(out), deep_pdf=str(blank))
    titles = [item.title for item in PdfReader(str(out)).outline]
    assert pdf_gen.DEEP_COMPARE_HEADING in titles
    assert not any("N:M" in t for t in titles)


def test_deep_compare_column_is_shared_hashes():
    from diffinite.models import DeepMatchResult

    dr = DeepMatchResult(file_a="a.py", matched_files_b=[("b.py", 4, 0.4, False)])
    cover = pdf_gen.build_cover_body([], [], [], "A", "B", False, False, deep_results=[dr])
    assert f"<h2>{pdf_gen.DEEP_COMPARE_HEADING}</h2>" in cover
    assert ">Shared hashes</th>" in cover


# ---------------------------------------------------------------------------
# Visual #3 (and text loss): a run with no space wraps inside the cell
# ---------------------------------------------------------------------------
def test_long_run_is_broken_without_changing_text():
    run = "x" * 250
    out = pdf_gen._pdf_break_long_runs(run, 100)
    assert out.split("<br/>") == ["x" * 100, "x" * 100, "x" * 50]


def test_break_counts_entities_wide_and_unmapped_characters():
    # An entity is one character; a wide CJK character takes two cells;
    # an astral character is drawn as its [U+XXXXX] marker.
    assert pdf_gen._pdf_break_long_runs("&amp;" * 4, 3) == "&amp;" * 3 + "<br/>" + "&amp;"
    assert pdf_gen._pdf_break_long_runs("日本語", 4) == "日本<br/>語"
    assert pdf_gen._char_cells("\U0001F600") == len("[U+1F600]")


def test_break_resets_at_spaces_and_spans_tags():
    assert "<br/>" not in pdf_gen._pdf_break_long_runs("aaaa bbbb cccc", 5)
    out = pdf_gen._pdf_break_long_runs('ab<span class="c">cd</span>ef', 3)
    assert out == 'ab<span class="c">c<br/>d</span>ef'


def test_pdf_run_capacity_fits_the_code_cell():
    code_pt = pdf_gen._pdf_code_cell_width_pt(["28px", "", "28px", ""])
    cap = pdf_gen._pdf_run_capacity(code_pt, "x")
    # Even at Courier's 4.2 pt advance the run fits after the hanging indent.
    assert cap * 4.2 + 2 * pdf_gen._PDF_CODE_ADVANCE_PT <= code_pt
    assert cap > 70


def test_long_token_reaches_the_pdf_text_layer_whole(tmp_path):
    from pypdf import PdfReader

    token = "(<i>e<sup>x</sup>&nbsp;-&nbsp;e<sup>-x</sup></i>)/" * 6 + "END"
    html_diff = _diff("a\n", "     * " + token + "\n")
    r = DiffResult(FileMatch("a.py", "b.py", 100.0), 0.0, 1, 1, html_diff)
    out = tmp_path / "t.pdf"
    assert pdf_gen.html_to_pdf(pdf_gen.build_diff_page_html(r, 1, "line"), str(out))
    page = PdfReader(str(out)).pages[0]
    text = "".join(page.extract_text().split())
    assert "".join(token.split()) in text
    # The 300-character run is set on several lines, each inside the page.
    ys: set[float] = set()

    def visit(t, cm, tm, font, size):  # type: ignore[no-untyped-def]
        if "&nbsp;" in t:
            ys.add(round(tm[5] * cm[3] + cm[5], 1))

    page.extract_text(visitor_text=visit)
    assert len(ys) >= 3
