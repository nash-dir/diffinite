"""End-to-end pipeline tests using the example directory."""

import json
import os
from pathlib import Path

import pytest


EXAMPLE_LEFT = str(Path(__file__).resolve().parent.parent / "example" / "left")
EXAMPLE_RIGHT = str(Path(__file__).resolve().parent.parent / "example" / "right")
EXAMPLE_EXISTS = Path(EXAMPLE_LEFT).is_dir() and Path(EXAMPLE_RIGHT).is_dir()


@pytest.mark.skipif(not EXAMPLE_EXISTS, reason="example/ directories not found")
class TestPipelineE2E:
    """Integration tests using the example data."""

    def test_standard_mode(self, tmp_path):
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "e2e_report.pdf")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            output_pdf=output,
            by_word=False,
            compare_comment=False,
        )
        assert Path(output).exists()
        assert Path(output).stat().st_size > 0

    def test_deep_mode(self, tmp_path):
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "deep_report.pdf")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            output_pdf=output,
            exec_mode="deep",
            workers=2,
            kgram_size=5,
            window_size=4,
        )
        assert Path(output).exists()
        assert Path(output).stat().st_size > 0

    def test_no_merge_mode(self, tmp_path):
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "individual.pdf")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            output_pdf=output,
            no_merge=True,
        )
        files_dir = tmp_path / "individual_files"
        if files_dir.exists():
            pdfs = list(files_dir.glob("*.pdf"))
            assert len(pdfs) >= 1


class TestJsonReport:
    """Tests for --report-json output format."""

    def test_json_report_empty_dirs(self, tmp_path):
        """JSON report is generated even with empty directories."""
        from diffinite.pipeline import run_pipeline

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        output = str(tmp_path / "result.json")

        run_pipeline(dir_a=str(d_a), dir_b=str(d_b), report_json=output)

        assert Path(output).exists()
        data = json.loads(Path(output).read_text(encoding="utf-8"))
        assert data["summary"]["matched_pairs"] == 0
        assert isinstance(data["results"], list)
        assert isinstance(data["unmatched_a"], list)

    def test_json_report_structure(self, tmp_path):
        """JSON report contains all required top-level keys."""
        from diffinite.pipeline import run_pipeline

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        (d_a / "hello.py").write_text("import os\nprint('hello')\nprint('done')\n", encoding="utf-8")
        (d_b / "hello.py").write_text("import os\nprint('world')\nprint('done')\n", encoding="utf-8")
        output = str(tmp_path / "result.json")

        run_pipeline(dir_a=str(d_a), dir_b=str(d_b), report_json=output)

        data = json.loads(Path(output).read_text(encoding="utf-8"))
        # Top-level keys
        for key in ("metadata", "dir_a", "dir_b", "summary",
                     "results", "unmatched_a", "unmatched_b"):
            assert key in data, f"Missing key: {key}"
        # Result entry keys
        assert len(data["results"]) == 1
        r = data["results"][0]
        for key in ("file_a", "file_b", "ratio", "additions",
                     "deletions", "html_diff"):
            assert key in r, f"Missing result key: {key}"
        assert r["ratio"] > 0
        assert "<table" in r["html_diff"]

    @pytest.mark.skipif(not EXAMPLE_EXISTS, reason="example/ directories not found")
    def test_json_report_deep_mode(self, tmp_path):
        """JSON report includes deep_results when mode=deep."""
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "deep.json")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            report_json=output,
            exec_mode="deep",
            workers=2,
        )
        data = json.loads(Path(output).read_text(encoding="utf-8"))
        assert data["metadata"]["exec_mode"] == "deep"
        # deep_results should be a list (may be empty if no cross-matches)
        assert isinstance(data["deep_results"], list)
