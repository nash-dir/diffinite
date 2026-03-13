"""Tests for CLI argument parsing."""

import pytest
from diffinite.cli import main


class TestCliParsing:
    """Verify CLI parses all arguments correctly."""

    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_requires_two_dirs(self):
        with pytest.raises(SystemExit):
            main([])

    def test_requires_dir_b(self):
        with pytest.raises(SystemExit):
            main(["dir_a_only"])

    def test_mode_choices_invalid(self):
        """--mode rejects unknown values."""
        with pytest.raises(SystemExit) as exc:
            main(["x", "y", "--mode", "invalid"])
        assert exc.value.code == 2  # argparse error

    def test_valid_flags_accepted(self, tmp_path):
        """All flags are accepted by the parser (runs on empty dirs → no crash)."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        # Should run to completion on empty directories (no files to diff)
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--collapse-identical",
            "--page-number", "--file-number",
            "--bates-number", "--show-filename",
        ])

    def test_deep_flags_accepted(self, tmp_path):
        """Deep compare flags parse correctly."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--deep", "--mode", "ast",
            "--multi-channel", "--normalize",
        ])

    def test_threshold_accepts_value(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--threshold", "80",
        ])
