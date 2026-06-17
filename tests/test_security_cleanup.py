"""Markdown report escaping and newly-registered languages (README accuracy)."""

from diffinite.languages import get_spec
from diffinite.parser import strip_comments
from diffinite.pipeline import _generate_markdown_report, _md_escape


class TestMarkdownEscaping:
    def test_md_escape_neutralizes_dangerous_chars(self):
        out = _md_escape("a`b|c<d>e")
        assert "&lt;d&gt;" in out
        assert "\\|" in out
        assert "\\`" in out
        assert "<" not in out and ">" not in out

    def test_markdown_report_escapes_dir_name(self, tmp_path):
        out_md = tmp_path / "r.md"
        _generate_markdown_report(
            [], [], [], "evil|<x>", "dirB", False, False, None, str(out_md),
        )
        text = out_md.read_text(encoding="utf-8")
        assert "evil|<x>" not in text          # raw dangerous string gone
        assert "&lt;x&gt;" in text             # angle brackets escaped
        assert "evil\\|" in text               # pipe escaped (no table break)


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
