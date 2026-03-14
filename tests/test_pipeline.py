"""End-to-end pipeline tests using the example directory."""

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
