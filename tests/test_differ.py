"""Tests for the diff engine with Pygments syntax highlighting."""

import pytest

from diffinite.differ import compute_diff, generate_html_diff


class TestComputeDiff:
    def test_identical(self):
        ratio, adds, dels = compute_diff("hello\n", "hello\n")
        assert ratio == 1.0
        assert adds == 0
        assert dels == 0

    def test_completely_different(self):
        ratio, adds, dels = compute_diff("aaa\n", "bbb\n")
        assert ratio < 0.5
        assert adds >= 1
        assert dels >= 1

    def test_by_word(self):
        ratio, adds, dels = compute_diff("a b c", "a b d", by_word=True)
        assert 0.0 < ratio < 1.0


class TestGenerateHtmlDiff:
    def test_basic_output(self):
        html = generate_html_diff(
            "line1\nline2\n",
            "line1\nline3\n",
            label_a="A", label_b="B",
            filename_a="test.py", filename_b="test.py",
        )
        assert "<table" in html
        assert "line1" in html
        # One side should show deleted, other added (compound class names)
        assert "del" in html or "add" in html

    def test_syntax_highlighting_present(self):
        """Pygments should inject inline styles for Python code."""
        src_a = 'def foo():\n    return 42\n'
        src_b = 'def bar():\n    return 99\n'
        html = generate_html_diff(
            src_a, src_b,
            filename_a="code.py", filename_b="code.py",
        )
        # Pygments inline styles use style="..."
        assert 'style="' in html

    def test_unknown_language_no_crash(self):
        """Unknown file type should fall back to TextLexer without crash."""
        html = generate_html_diff(
            "a = 1\n", "b = 2\n",
            filename_a="data.xyz", filename_b="data.xyz",
        )
        assert "<table" in html
