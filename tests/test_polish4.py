"""Regression tests for the final-review polish (PDF rows, console, lists).

Covers final-review items #1 (line-number padding), #6 (no-counterpart
cells in greyscale), #7 (dead truncation-note rewrite), #8 (console size
labels, Step 5 indentation, digests of every report) and #9 (unmatched
files without a bullet glyph).
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from diffinite import pdf_gen
from diffinite.models import DiffResult, FileMatch, size_label, truncation_note_text

A_SRC = "\n".join(f"int alpha_{i}(int x) {{ return x * {i} + {i * 3}; }}" for i in range(12)) + "\n"
B_SRC = A_SRC.replace("alpha_3(", "gamma_3(") + "int extra(void) { return 0; }\n"


def _css_rule(css: str, selector: str) -> str:
    """The declaration block of the first rule whose selector is exactly ``selector``."""
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def _dirs(tmp_path: Path) -> tuple[str, str]:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.c").write_text(A_SRC, encoding="utf-8")
    (tmp_path / "b" / "x.c").write_text(B_SRC, encoding="utf-8")
    (tmp_path / "b" / "only_in_b.c").write_text("int z;\n", encoding="utf-8")
    return str(tmp_path / "a"), str(tmp_path / "b")


# -- #1: line numbers on the code baseline, without taller rows --------------
def test_pdf_line_number_padding_matches_code_baseline():
    cells = _css_rule(pdf_gen._CSS_BODY, ".difftbl th, .difftbl td")
    assert "padding: 1.5pt 3pt 0 3pt;" in cells
    # xhtml2pdf doubles a cell's padding for direct text: 2 x 0.95 = 1.5 + 0.4.
    ln = _css_rule(pdf_gen._CSS_BODY, ".difftbl td.ln")
    assert "padding-top: 0.95pt;" in ln and "padding-bottom: 0;" in ln


def test_screen_css_keeps_symmetric_line_number_padding():
    ln = _css_rule(pdf_gen._CSS_SCREEN, ".difftbl td.ln")
    assert "padding-top: 1px;" in ln and "padding-bottom: 1px;" in ln


# -- #6: no-counterpart cells are white and ruled, not a grey fill -----------
def test_no_counterpart_cells_are_white_and_ruled():
    assert "background: #fff;" in _css_rule(pdf_gen._CSS_BODY, ".empty")
    assert "#f2f2f2" not in pdf_gen._CSS_BODY
    ruled = _css_rule(pdf_gen._CSS_BODY, ".difftbl td.empty")
    assert "border-top: 0.5pt solid #9a9a9a;" in ruled
    assert "border-bottom: 0.5pt solid #9a9a9a;" in ruled
    # The HTML keeps its hatch and the ordinary hairline.
    assert "border-top: none;" in _css_rule(pdf_gen._CSS_SCREEN, ".difftbl td.empty")


def test_key_swatch_for_no_counterpart_is_ruled_without_a_bar():
    key = pdf_gen.diff_key_html('<td class="code empty"><pre></pre></td>')
    cell = re.search(r'<td class="sw empty"[^>]*>', key).group(0)
    assert "border-top: 0.5pt solid #9a9a9a;" in cell
    assert "border-left" not in cell
    assert "No counterpart line" in key


# -- #7: the truncation note is shown as recorded -----------------------------
def test_truncation_note_is_not_rewritten():
    assert not hasattr(pdf_gen, "_truncation_note_html")
    assert not hasattr(pdf_gen, "_RE_TRUNC_LIMIT")
    note = f'<p class="note">{truncation_note_text(36_864, 0.01)}</p>'
    r = DiffResult(
        match=FileMatch("x.c", "x.c", 100.0),
        ratio=0.5,
        additions=1,
        deletions=1,
        html_diff=note,
        html_diff_truncated=True,
        html_diff_original_bytes=36_864,
    )
    out = pdf_gen.pair_result_html(r, "line")
    assert note in out
    assert "its HTML is 36.0 KB, over the 0.01 MB (10.2 KB) limit" in out


# -- #9: unmatched files as plain lines --------------------------------------
def test_unmatched_files_are_plain_lines():
    body = pdf_gen.build_cover_body([], ["a/one.c"], ["b/two.c", "b/three.c"], "A", "B", False, False)
    section = body[body.index("<h2>Unmatched Files</h2>"):]
    assert "<li>" not in section and "<ul" not in section
    assert "<h3>Only in A (A)</h3>\n<div class='unmatched'>\n" in section
    assert section.count("<p>") >= 3
    assert "•" not in body


# -- #8: console size labels ---------------------------------------------------
def test_large_diff_warnings_use_the_shared_size_label():
    src = Path(pdf_gen.__file__).with_name("pipeline.py").read_text(encoding="utf-8")
    assert "%.0f KB" not in src
    assert '"  %d. %s (%s of HTML)"' in src
    assert src.count("size_label(len(r.html_diff))") == 2
    assert size_label(600_000) == "585.9 KB"
    assert size_label(1_234 * 1024 * 1024) == "1,234.0 MB"


# -- #8 #9: end to end through the PDF ---------------------------------------
def test_step5_console_and_pdf_text_layer(tmp_path, caplog):
    from pypdf import PdfReader

    from diffinite.pipeline import run_pipeline

    dir_a, dir_b = _dirs(tmp_path)
    out = tmp_path / "out"
    reports = {ext: out / f"r.{ext}" for ext in ("pdf", "html", "md", "json")}
    with caplog.at_level(logging.INFO):
        run_pipeline(
            dir_a,
            dir_b,
            workers=1,
            exec_mode="simple",
            show_bates_number=True,
            report_pdf=str(reports["pdf"]),
            report_html=str(reports["html"]),
            report_md=str(reports["md"]),
            report_json=str(reports["json"]),
        )
    messages = [r.getMessage() for r in caplog.records]

    # Every report written has its digest printed, and it is the file's digest.
    for path in reports.values():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert f"  SHA-256 of {path.name}: {digest}" in messages, path.name

    # Step 5 sub-lines from pdf_gen are indented like the others.
    merged = [m for m in messages if "Merged PDF with bookmarks" in m]
    bates = [m for m in messages if "Bates numbers added" in m]
    assert merged and bates
    assert all(m.startswith("  ") for m in merged + bates)

    # No bullet glyph in the PDF text layer; the path is there on its own.
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(reports["pdf"])).pages)
    assert "only_in_b.c" in text
    assert "•" not in text
