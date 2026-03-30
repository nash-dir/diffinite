"""Tests for whitespace normalization (tab→space, collapse multiple spaces).

Covers:
  - normalize_whitespace() function
  - by_word auto tab→space in generate_html_diff
  - normalize_ws flag in compute_diff and generate_html_diff
"""

import pytest

from diffinite.differ import (
    compute_diff,
    generate_html_diff,
    normalize_whitespace,
)


class TestNormalizeWhitespace:
    """normalize_whitespace() 함수 단위 테스트."""

    def test_tabs_replaced(self):
        assert normalize_whitespace("\tint x = 5;\n") == "int x = 5;\n"

    def test_multiple_spaces_collapsed(self):
        assert normalize_whitespace("a   b    c\n") == "a b c\n"

    def test_tab_and_spaces_combined(self):
        result = normalize_whitespace("\t\tint  x  = 5;\n")
        assert result == "int x = 5;\n"

    def test_preserves_line_structure(self):
        text = "line1\n\tline2\n  line3\n"
        result = normalize_whitespace(text)
        lines = result.splitlines()
        assert len(lines) == 3
        assert lines[0] == "line1"
        assert lines[1] == "line2"
        assert lines[2] == "line3"

    def test_empty_string(self):
        assert normalize_whitespace("") == ""

    def test_blank_lines_preserved(self):
        """빈 줄은 유지된다 (줄 수가 변하지 않아야 함)."""
        text = "a\n\nb\n"
        result = normalize_whitespace(text)
        assert result.count("\n") == text.count("\n")

    def test_crlf_preserved(self):
        text = "\tint x;\r\n  int y;\r\n"
        result = normalize_whitespace(text)
        assert "int x;\r\n" in result
        assert "int y;\r\n" in result


class TestByWordAutoTabReplacement:
    """by_word=True 시 generate_html_diff에서 탭이 자동으로 스페이스로 변환되어
    블록 밀림이 방지되는지 확인."""

    def test_tab_vs_space_treated_equal_in_word_mode(self):
        """탭 들여쓰기 vs 스페이스 들여쓰기가 word 모드에서 같은 줄로 인식."""
        text_a = "\tint x = 5;\n\tint y = 10;\n"
        text_b = "    int x = 5;\n    int y = 10;\n"

        html = generate_html_diff(
            text_a, text_b,
            filename_a="test.c", filename_b="test.c",
            by_word=True,
        )
        # 탭→스페이스 자동 변환 후에도 내용은 동일하므로
        # del/add 클래스가 없어야 한다 (equal로 인식)
        # 다만 스페이스 수 차이로 일부 chg가 나올 수 있으므로
        # 핵심: 블록이 통째로 delete/insert로 밀리면 안 됨
        assert 'class="code del"' not in html
        assert 'class="code add"' not in html

    def test_tab_vs_space_differs_in_line_mode(self):
        """by_word=False에서는 탭과 스페이스가 다르게 인식되어야 한다."""
        text_a = "\tint x = 5;\n"
        text_b = "    int x = 5;\n"

        html = generate_html_diff(
            text_a, text_b,
            filename_a="test.c", filename_b="test.c",
            by_word=False,
        )
        # 라인 모드에서는 탭 vs 4스페이스가 다른 줄로 인식
        assert "del" in html or "add" in html


class TestNormalizeWsFlag:
    """--normalize-whitespace 플래그 테스트."""

    def test_compute_diff_normalize_ws_ignores_indent_diff(self):
        """normalize_ws=True 시 들여쓰기 차이가 무시된다."""
        text_a = "\t\tint x = 5;\n"
        text_b = "  int x = 5;\n"

        ratio_raw, _, _ = compute_diff(text_a, text_b, normalize_ws=False)
        ratio_norm, _, _ = compute_diff(text_a, text_b, normalize_ws=True)

        # 정규화 후에는 동일해야 (ratio=1.0)
        assert ratio_norm == 1.0
        # 원본에서는 차이가 있어야
        assert ratio_raw < 1.0

    def test_generate_html_diff_normalize_ws(self):
        """normalize_ws=True 시 HTML diff에 del/add가 없어야 한다."""
        text_a = "\t\tint x = 5;\n\t\tint y = 10;\n"
        text_b = "int x = 5;\nint y = 10;\n"

        html = generate_html_diff(
            text_a, text_b,
            filename_a="test.c", filename_b="test.c",
            normalize_ws=True,
        )
        assert 'class="code del"' not in html
        assert 'class="code add"' not in html

    def test_normalize_ws_with_by_word(self):
        """by_word + normalize_ws 조합 테스트."""
        text_a = "\t\tresult  =  a + b;\n"
        text_b = "    result = a + b;\n"

        ratio, adds, dels = compute_diff(
            text_a, text_b,
            by_word=True,
            normalize_ws=True,
        )
        assert ratio == 1.0
        assert adds == 0
        assert dels == 0
