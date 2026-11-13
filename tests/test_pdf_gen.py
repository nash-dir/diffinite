"""Tests for PDF generation module."""

from diffinite.models import DiffResult, FileMatch, DeepMatchResult
from diffinite.pdf_gen import build_cover_body, build_diff_page_html, _break_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_results():
    return [
        DiffResult(
            match=FileMatch("handler.java", "handler.java", 100.0),
            ratio=0.95,
            additions=10,
            deletions=5,
            html_diff="<table></table>",
        ),
        DiffResult(
            match=FileMatch("looper.java", "looper.java", 100.0),
            ratio=1.0,
            additions=0,
            deletions=0,
            html_diff="<table></table>",
        ),
    ]


def _cover(results=None, *, deep_results=None):
    """Shorthand wrapper for build_cover_body with required positional args."""
    return build_cover_body(
        results or _make_results(),
        unmatched_a=[],
        unmatched_b=[],
        dir_a="dir_a",
        dir_b="dir_b",
        by_word=False,
        strip_comments=False,
        deep_results=deep_results,
    )


# ---------------------------------------------------------------------------
# Cover page tests
# ---------------------------------------------------------------------------
class TestBuildCoverHtml:
    """Verify cover page HTML generation."""

    def test_returns_string(self):
        html = _cover()
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_file_names(self):
        html = _cover()
        # _break_path inserts <wbr> after path separators (., /, \, _)
        assert "handler." in html
        assert "looper." in html

    def test_contains_ratio(self):
        html = _cover()
        assert "95" in html  # ratio 0.95 → 95%

    def test_content_match_relabelled_to_difflib(self):
        """The headline column must name difflib so the line-level ratio is not
        misread as semantic similarity (forensic clarity)."""
        html = _cover()
        assert "Line match</th>" in html
        assert "(difflib)" not in html
        assert "Content Match" not in html

    def test_metadata_banner_surfaces_autojunk(self):
        from diffinite.models import AnalysisMetadata
        meta = AnalysisMetadata(
            exec_mode="deep", k=5, w=4, threshold=5.0, autojunk=False,
        )
        html = build_cover_body(
            _make_results(), unmatched_a=[], unmatched_b=[],
            dir_a="a", dir_b="b", by_word=False, strip_comments=False,
            metadata=meta,
        )
        assert 'Line diff autojunk</td><td style="width: 78%;">off</td>' in html

    def _cover_with_meta(self, *, normalize, exec_mode, strip_comments=True):
        from diffinite.models import AnalysisMetadata
        from diffinite.calibration import NORMALIZE_DEFAULT_THRESHOLD
        meta = AnalysisMetadata(
            exec_mode=exec_mode, k=5, w=4, threshold=NORMALIZE_DEFAULT_THRESHOLD,
            threshold_provenance="normalize-default", normalize=normalize,
            strip_comments=strip_comments,
        )
        return build_cover_body(
            _make_results(), unmatched_a=[], unmatched_b=[],
            dir_a="a", dir_b="b", by_word=False,
            strip_comments=strip_comments, metadata=meta,
        )

    def test_pdf_cover_discloses_fp_under_normalize_deep(self):
        # The PDF is the primary forensic deliverable; it must carry the FP rate.
        from diffinite.calibration import NORMALIZE_FP_RATE_PCT
        html = self._cover_with_meta(normalize=True, exec_mode="deep")
        assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" in html

    def test_pdf_cover_withholds_measured_fp_for_unvalidated_profile(self):
        from diffinite.calibration import NORMALIZE_FP_RATE_PCT
        html = self._cover_with_meta(
            normalize=True, exec_mode="deep", strip_comments=False,
        )
        assert "unvalidated profile" in html.lower()
        assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" not in html

    def test_pdf_cover_no_disclosure_in_simple_mode(self):
        # normalize is a no-op without deep fingerprinting, so no disclosure.
        html = self._cover_with_meta(normalize=True, exec_mode="simple")
        assert "false-positive" not in html.lower()

    def test_contains_additions_deletions(self):
        html = _cover()
        assert "+10" in html
        assert "\u22125" in html  # U+2212 MINUS SIGN, not a hyphen

    def test_empty_results(self):
        html = _cover(results=[])
        assert isinstance(html, str)

    def test_unmatched_files_shown(self):
        html = build_cover_body(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            strip_comments=False,
        )
        # _break_path inserts <wbr> after separators, so check partial strings
        assert "orphan" in html

    def test_deep_results_without_channels(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.8, False)],
            ),
        ]
        html = _cover(deep_results=deep)
        assert "foo." in html
        assert "bar." in html

    def test_deep_results_display(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.8, False)],
                fingerprint_count_a=100,
            ),
        ]
        html = _cover(deep_results=deep)
        assert "foo." in html
        assert "bar." in html

    def test_inconclusive_match_is_flagged(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.99, True)],  # inconclusive
            ),
        ]
        html = _cover(deep_results=deep)
        assert "inconclusive" in html.lower()

    def test_conclusive_match_not_flagged(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.99, False)],
            ),
        ]
        html = _cover(deep_results=deep)
        assert "inconclusive" not in html.lower()
        assert "50" in html  # shared hashes


# ---------------------------------------------------------------------------
# Diff page tests
# ---------------------------------------------------------------------------
class TestBuildDiffPageHtml:
    """Verify per-file diff page HTML."""

    def test_basic_output(self):
        result = DiffResult(
            match=FileMatch("test.py", "test.py", 100.0),
            ratio=0.90,
            additions=5,
            deletions=3,
            html_diff='<table class="difftbl"><tbody></tbody></table>',
        )
        html = build_diff_page_html(result, index=1, unit="line")
        assert isinstance(html, str)
        assert "test.py" in html

    def test_error_in_result(self):
        result = DiffResult(
            match=FileMatch("broken.py", "broken.py", 100.0),
            ratio=0.0,
            additions=0,
            deletions=0,
            html_diff="",
            error="Could not decode file",
        )
        html = build_diff_page_html(result, index=1, unit="line")
        assert "Could not decode" in html or "broken.py" in html

    def test_with_annotations(self):
        result = DiffResult(
            match=FileMatch("annotated.py", "annotated.py", 100.0),
            ratio=0.75,
            additions=10,
            deletions=8,
            html_diff='<table class="difftbl"><tbody></tbody></table>',
        )
        html = build_diff_page_html(
            result,
            index=1,
            unit="line",
            total_files=5,
            show_filename=True,
        )
        assert "annotated.py" in html


# ---------------------------------------------------------------------------
# _break_path tests
# ---------------------------------------------------------------------------
class TestBreakPath:
    """Verify _break_path is a no-op passthrough (word wrapping handled by CSS pdf-word-wrap: CJK)."""

    def test_slash(self):
        result = _break_path("src/main/java")
        assert result == "src/main/java"

    def test_backslash(self):
        result = _break_path("src\\main\\java")
        assert result == "src\\main\\java"

    def test_dot(self):
        result = _break_path("handler.java")
        assert result == "handler.java"

    def test_underscore(self):
        result = _break_path("my_file_name")
        assert result == "my_file_name"

    def test_combined(self):
        result = _break_path("src/com/example/my_handler.java")
        assert result == "src/com/example/my_handler.java"

    def test_empty(self):
        assert _break_path("") == ""


# ---------------------------------------------------------------------------
# include_uncompared tests
# ---------------------------------------------------------------------------
class TestUncomparedMode:
    """Verify uncompared_mode parameter on build_cover_body."""

    def test_excludes_unmatched_when_none(self):
        html = build_cover_body(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            strip_comments=False,
            uncompared_mode="none",
        )
        assert "orphan" not in html
        assert "Unmatched Files" not in html

    def test_excludes_unmatched_when_separate(self):
        html = build_cover_body(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            strip_comments=False,
            uncompared_mode="separate",
        )
        assert "orphan" not in html
        assert "Unmatched Files" not in html

    def test_includes_unmatched_when_inline(self):
        html = build_cover_body(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            strip_comments=False,
            uncompared_mode="inline",
        )
        assert "orphan" in html
        assert "Unmatched Files" in html

    def test_includes_unmatched_by_default(self):
        html = build_cover_body(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            strip_comments=False,
        )
        assert "orphan" in html
        assert "Unmatched Files" in html


def _text_pdf(path, pages=3):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for p in range(pages):
        for i in range(60):
            c.drawString(40, 800 - i * 12, f"public int line{p}_{i} = {i}; // code text")
        c.showPage()
    c.save()


def _contents_filtered(pdf_path):
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    out = []
    for page in reader.pages:
        contents = page["/Contents"].get_object()
        streams = contents if isinstance(contents, list) else [contents]
        out.append(all(s.get_object().get("/Filter") is not None for s in streams))
    return reader, out


def test_bates_stamping_keeps_content_streams_compressed(tmp_path):
    """merge_page decompresses page content; stamped PDFs must not stay uncompressed
    (that made Bates-stamped reports ~10x larger than the same report unstamped)."""
    from diffinite.pdf_gen import add_bates_numbers, stamp_bates_inplace

    src = tmp_path / "in.pdf"
    _text_pdf(src)
    merged = tmp_path / "merged.pdf"
    add_bates_numbers(str(src), str(merged), prefix="X-", suffix="-C")
    reader, filtered = _contents_filtered(merged)
    assert all(filtered)
    assert reader.pages[-1].extract_text().rstrip().endswith("X-0003-C")

    split = tmp_path / "split.pdf"
    _text_pdf(split)
    stamp_bates_inplace(str(split), 5, 4, prefix="X-", suffix="-C")
    reader, filtered = _contents_filtered(split)
    assert all(filtered)
    assert reader.pages[-1].extract_text().rstrip().endswith("X-0007-C")


def test_pdf_css_does_not_use_inherit():
    """xhtml2pdf 0.2.28 crashes resolving "inherit" for cache-hit cells.

    ('Element' object has no attribute 'cssElement'.) The PDF CSS states
    values explicitly; the screen-only CSS is never given to xhtml2pdf.
    """
    import re

    from diffinite.pdf_gen import _CSS_BODY

    assert not re.search(r":\s*inherit\b", _CSS_BODY)
