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
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
        ])

    def test_mode_invalid_rejected(self):
        with pytest.raises(SystemExit) as exc:
            main(["x", "y", "--mode", "invalid"])
        assert exc.value.code == 2


class TestDeepCompareArgs:
    """Verify deep compare option flags."""

    def test_manual_override_accepted(self, tmp_path):
        """K, W, T manual override flags are accepted."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--mode", "deep",
            "--k-gram", "5",
            "--window", "3",
            "--threshold-deep", "20",
        ])


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
            "--bates-number", "--filename",
        ])

    def test_threshold_accepts_value(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--threshold", "80",
        ])

    def test_report_json_accepted(self, tmp_path):
        """--report-json flag is accepted and generates output."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        json_path = str(tmp_path / "out.json")
        main([
            str(d_a), str(d_b),
            "--report-json", json_path,
        ])
        from pathlib import Path
        assert Path(json_path).exists()


class TestIncludeUncomparedFlag:
    """Verify --include-uncompared / --no-include-uncompared flags."""

    def test_include_uncompared_default_true(self, tmp_path):
        """Default behavior includes uncompared files."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        (d_a / "only_a.py").write_text("x = 1\n", encoding="utf-8")
        json_path = str(tmp_path / "out.json")
        main([
            str(d_a), str(d_b),
            "--report-json", json_path,
        ])
        import json
        from pathlib import Path
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert "only_a.py" in data["unmatched_a"]

    def test_no_include_uncompared_excludes(self, tmp_path):
        """--no-include-uncompared excludes unmatched file lists."""
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        (d_a / "only_a.py").write_text("x = 1\n", encoding="utf-8")
        json_path = str(tmp_path / "out.json")
        main([
            str(d_a), str(d_b),
            "--report-json", json_path,
            "--no-include-uncompared",
        ])
        import json
        from pathlib import Path
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert data["unmatched_a"] == []
        assert data["unmatched_b"] == []
        # Summary counts should still show the real values
        assert data["summary"]["unmatched_a_count"] == 1
