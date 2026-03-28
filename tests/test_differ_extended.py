"""Tests for differ module — context folding and read_file."""

import os
import tempfile

import pytest

from diffinite.differ import compute_diff, generate_html_diff, read_file


class TestReadFile:
    """Verify file reading with encoding detection."""

    def test_read_utf8(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello = '안녕'\n", encoding="utf-8")
        content = read_file(str(f))
        assert "hello" in content
        assert "안녕" in content

    def test_read_nonexistent_returns_none(self):
        content = read_file("nonexistent_file_xyz.py")
        assert content is None

    def test_read_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        content = read_file(str(f))
        assert content == "" or content is not None


class TestContextFolding:
    """Verify --collapse-identical context folding behavior."""

    @pytest.fixture
    def long_diff_pair(self):
        """Two files with a small change in the middle of 100 identical lines."""
        common_top = "\n".join(f"line_{i} = {i}" for i in range(50))
        common_bottom = "\n".join(f"line_{i} = {i}" for i in range(60, 110))
        text_a = common_top + "\nchanged_line_a = 'old'\n" + common_bottom
        text_b = common_top + "\nchanged_line_b = 'new'\n" + common_bottom
        return text_a, text_b

    def test_no_folding_shows_all_lines(self, long_diff_pair):
        ta, tb = long_diff_pair
        html = generate_html_diff(
            ta, tb,
            filename_a="test.py", filename_b="test.py",
            context_lines=-1,
        )
        # Without folding, all lines should be present
        assert "line_0" in html
        assert "line_49" in html
        assert "line_100" in html
        assert 'class="fold"' not in html

    def test_folding_hides_identical_blocks(self, long_diff_pair):
        ta, tb = long_diff_pair
        html = generate_html_diff(
            ta, tb,
            filename_a="test.py", filename_b="test.py",
            context_lines=3,
        )
        # With folding, fold separators should appear
        assert 'class="fold"' in html
        assert "identical lines" in html

    def test_folded_smaller_than_full(self, long_diff_pair):
        ta, tb = long_diff_pair
        full = generate_html_diff(
            ta, tb,
            filename_a="test.py", filename_b="test.py",
            context_lines=-1,
        )
        folded = generate_html_diff(
            ta, tb,
            filename_a="test.py", filename_b="test.py",
            context_lines=3,
        )
        assert len(folded) < len(full), (
            f"Folded ({len(folded)}) should be smaller than full ({len(full)})"
        )

    def test_folding_preserves_change_context(self, long_diff_pair):
        ta, tb = long_diff_pair
        html = generate_html_diff(
            ta, tb,
            filename_a="test.py", filename_b="test.py",
            context_lines=3,
        )
        # The changed content should still be visible
        assert "changed_line" in html

    def test_identical_files_no_crash(self):
        text = "line_1\nline_2\nline_3\n"
        html = generate_html_diff(
            text, text,
            filename_a="same.py", filename_b="same.py",
            context_lines=3,
        )
        assert isinstance(html, str)
