"""Markdown report escaping and newly-registered languages (README accuracy)."""

from diffinite.languages import get_spec
from diffinite.parser import strip_comments
from diffinite.pipeline import _generate_markdown_report, _md_code


class TestMarkdownEscaping:
    def test_md_code_contains_dangerous_chars(self):
        # The fence is longer than any backtick run in the name, so the name
        # cannot leave the code span; inside a code span < and > are literal.
        assert _md_code("a`b|c<d>e") == "``a`b|c<d>e``"
        # Inside a GFM table cell the pipe is escaped so it cannot split the row.
        assert _md_code("a`b|c<d>e", table=True) == "``a`b\\|c<d>e``"

    def test_markdown_report_escapes_dir_name(self, tmp_path):
        out_md = tmp_path / "r.md"
        _generate_markdown_report(
            [], [], [], "evil|<x>", "dirB", False, False, None, str(out_md),
        )
        text = out_md.read_text(encoding="utf-8")
        # Code spans show the name literally and cannot be escaped from; in the
        # particulars table the pipe is escaped so it cannot split the row.
        assert "| Directory A | `evil\\|<x>` |" in text


class TestNewlyRegisteredLanguages:
    def test_zsh_and_r_are_registered(self):
        assert get_spec(".zsh") is not None
        assert get_spec(".r") is not None
        assert get_spec(".R") is not None

    def test_zsh_strips_hash_comment(self):
        result = strip_comments("echo hi  # greet\n", ".zsh")
        assert "# greet" not in result
        assert "echo hi" in result

    def test_r_strips_hash_comment(self):
        result = strip_comments("x <- 1  # assign\n", ".r")
        assert "# assign" not in result
        assert "x <- 1" in result
