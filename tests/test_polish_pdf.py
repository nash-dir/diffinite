"""Regression tests for the PDF/HTML report polish (pdf_gen.py, differ.py).

Glyph fidelity, print-first syntax style, pane labels, number formats,
plain-language status and threshold wording, continuous rules and the Bates
stamp's face and baseline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from diffinite import pdf_gen
from diffinite.differ import generate_html_diff
from diffinite.models import AnalysisMetadata, AnalysisStatus, DiffResult, FileMatch

SRC = Path(__file__).resolve().parents[1] / "src" / "diffinite"

JA = "\u623b"        # 戻: Japanese shinjitai, not in KS X 1001
ZH = "\u91ca"        # 释: Simplified Chinese, not in KS X 1001 or JIS X 0208
AR = "\u0645"        # م: Arabic, no PDF font here draws it
EMOJI = "\U0001F600"  # astral, beyond every UCS-2 CMap


def _result(**kw) -> DiffResult:
    base = dict(match=FileMatch("a.py", "b.py", 87.5), ratio=0.5,
                additions=1234, deletions=5678, html_diff="")
    base.update(kw)
    return DiffResult(**base)


def _pdf_text(path: Path) -> str:
    return "".join(p.extract_text() for p in PdfReader(str(path)).pages)


# ── #1 glyph fidelity ────────────────────────────────────────────────────
class TestGlyphFidelity:
    def test_every_character_is_drawn_or_marked(self, tmp_path):
        line_a = f"// {JA}り値 中文注{ZH} {AR}رحبا {EMOJI}"
        diff = generate_html_diff(line_a + "\n", "x\n", filename_a="a.java", filename_b="b.java")
        r = _result(html_diff=diff)
        out = tmp_path / "page.pdf"
        assert pdf_gen.html_to_pdf(pdf_gen.build_diff_page_html(r, 1, "line"), str(out))
        text = _pdf_text(out)
        assert "\x00" not in text
        for ch in (JA, ZH):
            assert ch in text
        # Undrawable characters are shown as visible code points, never as nothing.
        assert "[U+0645]" in text and "[U+1F600]" in text

    def test_font_choice_follows_coverage(self):
        plan = pdf_gen._font_plan(None, None)
        assert plan.key_for(JA) == "g-ja"
        assert plan.key_for(ZH) == "g-zhcn"
        assert plan.key_for("\ud55c") == "g-ko"  # 한
        assert plan.key_for(EMOJI) == "cpm"
        assert plan.key_for("\x1b") == "cpm"     # control characters are shown, too
        assert plan.key_for("e") == "" and plan.key_for("\u00e9") == ""
        assert plan.key_for("\u2212") == "g-sym"  # minus keeps the serif metrics

    def test_pdf_lang_is_the_first_choice_for_shared_han(self):
        # 中 is in every CJK character set; --pdf-lang decides its glyph form.
        assert pdf_gen._FontPlan(lang="ja").key_for("\u4e2d") == "g-ja"
        assert pdf_gen._FontPlan(lang="zh-cn").key_for("\u4e2d") == "g-zhcn"

    def test_traditional_chinese_uses_the_cns_cmap(self):
        pdf_gen._fix_cid_cmaps()
        from reportlab.pdfbase import _cidfontdata

        assert _cidfontdata.defaultUnicodeEncodings["MSung-Light"][1] == "UniCNS-UCS2-H"

    def test_tags_and_attributes_are_never_changed(self):
        plan = pdf_gen._font_plan(None, None)
        src = f'<td title="{EMOJI}">a{EMOJI}&amp;b</td>'
        out = pdf_gen._apply_glyph_fonts(src, plan)
        assert out == f'<td title="{EMOJI}">a<span class="cpm">[U+1F600]</span>&amp;b</td>'

    def test_cover_discloses_the_count_once(self, tmp_path):
        diff = generate_html_diff(f"{AR}{AR} {EMOJI}\n", "x\n", filename_a="a.py", filename_b="b.py")
        body = pdf_gen.build_cover_body([_result(html_diff=diff)], [], [], "A", "B", False, False)
        html = pdf_gen._html_wrap("c", body)
        assert html.count("could not be drawn by the PDF fonts") == 1
        assert "3 characters could not be drawn" in html
        assert "the HTML report shows them as written" in html

    def test_no_notice_when_everything_is_drawn(self):
        body = pdf_gen.build_cover_body([_result(html_diff="<p>plain</p>")], [], [], "A", "B", False, False)
        assert "could not be drawn" not in pdf_gen._html_wrap("c", body)

    def test_html_report_keeps_characters_as_written(self):
        diff = generate_html_diff(f"{EMOJI}\n", "x\n")
        assert EMOJI in diff and "[U+" not in diff


# ── #3 #4 #8 syntax style ────────────────────────────────────────────────
class TestSyntaxStyle:
    def test_multiline_comment_is_styled_as_comment(self):
        src = "/* licence\n * for this new default\n */\nint x = 1;\n"
        html = generate_html_diff(src, src.replace("1", "2"), filename_a="a.java", filename_b="b.java")
        assert '<pre><span style="color: #555"> * for this new default</span></pre>' in html

    def test_no_bold_italic_or_colour(self):
        src = 'public class A { /* c */ String s = "x"; }\n'
        html = generate_html_diff(src, src + "\n", filename_a="a.java", filename_b="b.java")
        styles = set(re.findall(r'style="([^"]*)"', html.split("<tbody>", 1)[1]))
        assert all("bold" not in s and "italic" not in s for s in styles)
        colours = set(re.findall(r"color: (#[0-9a-f]+)", " ".join(styles)))
        assert colours <= {"#555", "#444"}

    def test_highlighted_text_is_the_source_text(self):
        src = "a = '<&>'  # \u00e9\n\tb\n"
        html = generate_html_diff(src, src, filename_a="a.py", filename_b="a.py", context_lines=-1)
        cells = re.findall(r"<pre>(.*?)</pre>", html)
        import html as h
        texts = [h.unescape(re.sub(r"<[^>]*>", "", c)) for c in cells]
        assert "a = '<&>'  # \u00e9" in texts and "\tb" in texts


# ── #12 pane headers, fold rows ──────────────────────────────────────────
def test_pane_headers_name_side_and_directory():
    diff = generate_html_diff("a\n", "b\n", label_a="ArrayList.java", label_b="ArrayList.java")
    assert '<th class="code">A: ArrayList.java</th>' in diff
    page = pdf_gen.pair_result_html(_result(html_diff=diff), "line",
                                    dir_a="/cases/AOSP_Google", dir_b="C:\\cases\\OpenJDK_Oracle\\")
    assert "A: AOSP_Google/ArrayList.java" in page
    assert "B: OpenJDK_Oracle/ArrayList.java" in page


def test_fold_row_is_plain_with_thousands_separators():
    a = "".join(f"line {i}\n" for i in range(3000))
    html = generate_html_diff(a + "x\n", a + "y\n")
    assert "2,994 identical lines not shown (A 4 to 2,997, B 4 to 2,997)" in html
    assert "\u22ef" not in html


# ── #10 #16 copy #6 #7 labels and numbers ────────────────────────────────
def test_summary_labels_and_number_formats():
    body = pdf_gen.build_cover_body([_result()], [], [], "A", "B", False, False)
    assert "(difflib)" not in body and "Line match</th>" in body
    assert ">87.5%</td>" in body                 # name similarity carries %
    assert "+1,234" in body and "\u22125,678" in body


def test_deep_table_uses_two_decimals_and_file_a_b():
    from diffinite.models import DeepMatchResult

    dr = DeepMatchResult(file_a="x.java", unique_hashes_a=4000,
                         matched_files_b=[("y.java", 1172, 0.27951, False)],
                         unique_hashes_b={"y.java": 5000})
    body = pdf_gen.build_cover_body([], [], [], "A", "B", False, False, deep_results=[dr])
    assert "27.95%" in body and "1,172" in body
    assert ">File A</th>" in body and "A File" not in body and "B File(s)" not in body


def test_config_rows_threshold_in_plain_words():
    meta = AnalysisMetadata("deep", 5, 4, 93.0, threshold_provenance="normalize-default")
    rows = dict(pdf_gen.config_rows(meta))
    assert rows["Jaccard threshold"] == "93%"
    assert rows["Threshold source"] == "Default for normalized comparison"
    assert rows["Ignore policy"].startswith("0 rules;")


# ── #11 #15 copy #3 #4 status and alert ──────────────────────────────────
def test_incomplete_notice_has_no_reason_codes():
    status = AnalysisStatus()
    status.mark_incomplete("diff-payload-truncated")
    status.mark_incomplete("deep-index-truncated")
    meta = AnalysisMetadata("deep", 5, 4, 5.0, deep_index_truncated=True)
    text = pdf_gen.incomplete_notice(meta, status)
    assert "truncated" not in text and "Recorded reasons" not in text
    assert text.count("--max-index-entries") == 1
    box = pdf_gen.alert_html(text)
    assert box.startswith('<div class="alert"><b>Incomplete analysis.</b> ')
    assert box.count("<b>") == 1


def test_status_rows_have_labels():
    rows = pdf_gen.status_rows(AnalysisStatus())
    assert rows[0][0] == "State"
    assert all(label for label, _ in rows)


def test_cover_has_no_forced_page_break():
    body = pdf_gen.build_cover_body([_result()], [], [], "A", "B", False, False)
    assert "newpage" not in body


# ── #9 continuous rules ──────────────────────────────────────────────────
def test_rules_are_spanning_rows():
    t = pdf_gen.kv_table_html([("a", "1"), ("b", "2")])
    assert t.count('<tr class="rule"><td colspan="2"></td></tr>') == 2
    assert t.count('<tr class="hair"><td colspan="2"></td></tr>') == 1
    assert "border-top" not in pdf_gen._CSS_BODY.split("table.summary th", 1)[1].split("}", 1)[0]


# ── #14 Bates stamp ──────────────────────────────────────────────────────
def test_bates_shares_face_and_baseline_with_footer(tmp_path):
    annotation, footer, header = pdf_gen._build_annotation_html(show_page_number=True)
    page = tmp_path / "p.pdf"
    assert pdf_gen.html_to_pdf(pdf_gen._html_wrap("t", "<p>x</p>", annotation, has_footer=footer), str(page))
    out = tmp_path / "b.pdf"
    pdf_gen.add_bates_numbers(str(page), str(out), prefix="CASE-")

    found: dict[str, tuple[float, str]] = {}

    def visit(text, cm, tm, font_dict, size):
        if text.strip() and font_dict is not None:
            found[text.strip()] = (tm[5] * cm[3] + cm[5], str(font_dict.get("/BaseFont")))

    PdfReader(str(out)).pages[0].extract_text(visitor_text=visit)
    bates = next(v for k, v in found.items() if k.startswith("CASE-"))
    footer_line = next(v for k, v in found.items() if k.startswith("Page"))
    assert "Times" in bates[1] and "Times" in footer_line[1]
    assert abs(bates[0] - footer_line[0]) < 0.5


# ── #5 language, log text ────────────────────────────────────────────────
def test_pdf_html_is_english():
    assert '<html lang="en">' in pdf_gen._html_wrap("t", "<p>x</p>")


@pytest.mark.parametrize("name", ["pdf_gen.py", "differ.py"])
def test_log_messages_have_no_forbidden_glyphs(name):
    source = (SRC / name).read_text(encoding="utf-8")
    calls = re.findall(r"logger\.\w+\((.*?)\)\s*$", source, re.S | re.M)
    for call in calls:
        for glyph in "\u2192\u2014\u2013\u2026\u00b7\u26a0\u2713\u22ef":
            assert glyph not in call, (name, glyph, call[:80])


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("C:\\cases\\OpenJDK_Oracle\\", "OpenJDK_Oracle"),
        ("/cases/AOSP_Google", "AOSP_Google"),
        ("/cases/AOSP_Google/", "AOSP_Google"),
        ("relative\\mixed/dir", "dir"),
        ("C:\\", "C:"),
        ("", ""),
    ],
)
def test_dir_label_is_the_same_on_every_os(path, expected):
    """Windows and POSIX paths yield the same pane label on Linux and Windows."""
    assert pdf_gen._dir_label(path) == expected
