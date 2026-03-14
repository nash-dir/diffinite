"""Tests for CLI argument parsing."""

import pytest
from diffinite.cli import main, PROFILES


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


class TestModeArg:
    """Verify --mode simple|deep execution mode."""

    def test_mode_simple_valid(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--mode", "simple",
        ])

    def test_mode_deep_valid(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--mode", "deep",
        ])

    def test_mode_default_is_deep(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        # No --mode flag → should default to deep without error
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
        ])

    def test_mode_invalid_rejected(self):
        with pytest.raises(SystemExit) as exc:
            main(["x", "y", "--mode", "invalid"])
        assert exc.value.code == 2


class TestProfileAndTierSystem:
    """Verify 3-Tier parameter system (profile → override → grid-search)."""

    def test_profile_industrial_defaults(self):
        """Industrial profile should set K=5, W=4, T=0.10."""
        p = PROFILES["industrial"]
        assert p["k"] == 5
        assert p["w"] == 4
        assert p["t"] == 0.10

    def test_profile_academic_defaults(self):
        """Academic profile should set K=2, W=3, T=0.40."""
        p = PROFILES["academic"]
        assert p["k"] == 2
        assert p["w"] == 3
        assert p["t"] == 0.40

    def test_manual_override_accepted(self, tmp_path):
        """Tier 2 manual override flags are accepted."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--mode", "deep",
            "--profile", "academic",
            "--k-gram", "5",
            "--window", "3",
            "--threshold-deep", "0.20",
        ])

    def test_grid_search_flag_accepted(self, tmp_path):
        """--grid-search flag is parsed without error on empty dirs."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--mode", "deep",
            "--grid-search",
        ])


class TestTokenizerArg:
    """Verify --tokenizer replaces the old --mode token|ast|pdg."""

    def test_tokenizer_token(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--tokenizer", "token",
        ])

    def test_tokenizer_ast(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--tokenizer", "ast",
        ])

    def test_tokenizer_invalid_rejected(self):
        with pytest.raises(SystemExit) as exc:
            main(["x", "y", "--tokenizer", "invalid"])
        assert exc.value.code == 2


class TestAnnotationsAndReportFlags:
    """Verify remaining flags still work."""

    def test_all_flags_accepted(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--collapse-identical",
            "--page-number", "--file-number",
            "--bates-number", "--show-filename",
        ])

    def test_threshold_accepts_value(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--threshold", "80",
        ])
