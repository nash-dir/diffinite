"""Tests for PDF generation module."""

import pytest

from diffinite.models import DiffResult, FileMatch, DeepMatchResult
from diffinite.pdf_gen import build_cover_html, build_diff_page_html


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
    """Shorthand wrapper for build_cover_html with required positional args."""
    return build_cover_html(
        results or _make_results(),
        unmatched_a=[],
        unmatched_b=[],
        dir_a="dir_a",
        dir_b="dir_b",
        by_word=False,
        compare_comment=True,
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
        assert "handler.java" in html
        assert "looper.java" in html

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
        html = build_cover_html(
            _make_results(),
            unmatched_a=["orphan_a.py"],
            unmatched_b=["orphan_b.py"],
            dir_a="left",
            dir_b="right",
            by_word=False,
            compare_comment=True,
        )
        assert "orphan_a.py" in html
        assert "orphan_b.py" in html

    def test_deep_results_without_channels(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.8)],
            ),
        ]
        html = _cover(deep_results=deep)
        assert "foo.py" in html
        assert "bar.py" in html

    def test_deep_results_with_channel_scores(self):
        deep = [
            DeepMatchResult(
                file_a="foo.py",
                matched_files_b=[("bar.py", 50, 0.8)],
                channel_scores={
                    "foo.py|bar.py": {
                        "raw_winnowing": 0.8,
                        "normalized_winnowing": 0.9,
                        "composite": 0.85,
                    }
                },
            ),
        ]
        html = _cover(deep_results=deep)
        assert "Multi-Channel" in html or "channel" in html.lower() or "0.8" in html


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
