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


class TestIntraLineWordDiff:
    """by_word=True 시 replace 블록에서 단어 단위 하이라이팅 검증."""

    def test_single_word_change_produces_word_spans(self):
        """한 단어만 바뀌면 word-del/word-add span이 생성되어야 한다."""
        html = generate_html_diff(
            "return calculateSum(a, b)\n",
            "return calculateSum(a, c)\n",
            filename_a="test.py", filename_b="test.py",
            by_word=True,
        )
        assert "word-del" in html
        assert "word-add" in html
        assert "chg" in html

    def test_by_word_false_no_word_spans(self):
        """by_word=False이면 word-del/word-add span이 없어야 한다."""
        html = generate_html_diff(
            "return a\n",
            "return b\n",
            filename_a="test.py", filename_b="test.py",
            by_word=False,
        )
        assert "word-del" not in html
        assert "word-add" not in html

    def test_identical_lines_no_word_spans(self):
        """동일한 줄에는 word-del/word-add가 없어야 한다."""
        html = generate_html_diff(
            "hello world\n",
            "hello world\n",
            filename_a="test.txt", filename_b="test.txt",
            by_word=True,
        )
        assert "word-del" not in html
        assert "word-add" not in html
        assert "chg" not in html

    def test_unequal_line_count_partial_fallback(self):
        """줄 수가 다르면 대응 없는 줄은 기존 del/add 방식으로 처리."""
        html = generate_html_diff(
            "line1\nline2\nline3\n",
            "line1\nmodified2\n",
            filename_a="test.txt", filename_b="test.txt",
            by_word=True,
        )
        # 대응 없는 줄(line3)은 기존 del 방식
        assert "del" in html

