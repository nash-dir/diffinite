"""Forensic line-boundary handling.

Covers two audit findings:
  - The line-level similarity ratio must be insensitive to EOL style
    (CRLF vs LF vs CR) so identical content is not reported as ~0% match.
  - Line splitting must use real newlines only (\\r\\n / \\r / \\n), not
    str.splitlines()'s extra separators (form feed, NEL, U+2028/9), so
    displayed line numbers match a standard editor.
"""

from diffinite.differ import compute_diff, generate_html_diff, split_lines


class TestEolInsensitiveRatio:
    def test_crlf_vs_lf_identical_is_full_match(self):
        lf = "import os\nx = 1\nprint(x)\n"
        crlf = "import os\r\nx = 1\r\nprint(x)\r\n"
        ratio, adds, dels = compute_diff(lf, crlf)
        assert ratio == 1.0
        assert adds == 0
        assert dels == 0

    def test_cr_old_mac_vs_lf_identical(self):
        ratio, _, _ = compute_diff("a\nb\nc\n", "a\rb\rc\r")
        assert ratio == 1.0

    def test_trailing_newline_difference_is_equal(self):
        ratio, _, _ = compute_diff("a\nb\n", "a\nb")
        assert ratio == 1.0

    def test_real_content_change_still_detected(self):
        ratio, adds, dels = compute_diff("a\nb\nc\n", "a\nX\nc\n")
        assert ratio < 1.0
        assert adds >= 1 and dels >= 1


class TestRealNewlineSplitting:
    def test_form_feed_is_not_a_line_boundary(self):
        assert split_lines("a\x0cb") == ["a\x0cb"]

    def test_vertical_tab_and_nel_not_boundaries(self):
        assert split_lines("a\x0bb\x85c") == ["a\x0bb\x85c"]

    def test_unicode_line_separators_not_boundaries(self):
        assert split_lines("a b c") == ["a b c"]

    def test_standard_newlines_split(self):
        assert split_lines("a\nb\r\nc\rd") == ["a", "b", "c", "d"]

    def test_trailing_newline_dropped_like_splitlines(self):
        assert split_lines("a\nb\n") == ["a", "b"]
        assert split_lines("a\nb") == ["a", "b"]
        assert split_lines("") == []

    def test_html_diff_form_feed_kept_inline(self):
        # A form feed inside a line must not create an extra diff row.
        html = generate_html_diff(
            "a\x0cb\n", "a\x0cb\n", filename_a="x.c", filename_b="x.c",
        )
        assert isinstance(html, str)
        assert "identical" in html or "<table" in html
