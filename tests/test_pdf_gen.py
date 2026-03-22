"""Tests for PDF generation module."""

import pytest

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
        # _break_path inserts &#8203; after path separators (., /, \, _)
        assert "handler." in html
        assert "looper." in html

    def test_contains_ratio(self):
        html = _cover()
        assert "95" in html  # ratio 0.95 → 95%

    def test_contains_additions_deletions(self):
        html = _cover()
        assert "+10" in html
        assert "-5" in html

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
        # _break_path inserts &#8203; after separators, so check partial strings
        assert "orphan" in html

    def test_deep_results_without_channels(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.8)],
            ),
        ]
        html = _cover(deep_results=deep)
        assert "foo." in html
        assert "bar." in html

    def test_deep_results_display(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.8)],
                fingerprint_count_a=100,
            ),
        ]
        html = _cover(deep_results=deep)
        assert "foo." in html
        assert "bar." in html
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
    """Verify _break_path inserts zero-width spaces at path separators."""

    def test_slash(self):
        result = _break_path("src/main/java")
        assert "src/&#8203;main/&#8203;java" == result

    def test_backslash(self):
        result = _break_path("src\\main\\java")
        assert "src\\&#8203;main\\&#8203;java" == result

    def test_dot(self):
        result = _break_path("handler.java")
        assert "handler.&#8203;java" == result

    def test_underscore(self):
        result = _break_path("my_file_name")
        assert "my_&#8203;file_&#8203;name" == result

    def test_combined(self):
        result = _break_path("src/com/example/my_handler.java")
        assert "&#8203;" in result

    def test_empty(self):
        assert _break_path("") == ""


# ---------------------------------------------------------------------------
# include_uncompared tests
# ---------------------------------------------------------------------------
class TestIncludeUncompared:
    """Verify include_uncompared parameter on build_cover_body."""

    def test_excludes_unmatched_when_false(self):
        html = build_cover_body(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            strip_comments=False,
            include_uncompared=False,
        )
        assert "orphan" not in html
        assert "Unmatched Files" not in html

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
