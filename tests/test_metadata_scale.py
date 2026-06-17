"""AnalysisMetadata.threshold must be recorded on one scale (0-100) everywhere.

Previously the CLI stored the 0-100 user value while the library default stored
the 0-1 internal value, so two logically-equivalent runs printed 5.00 vs 0.05
for the same setting in a reproducibility banner.
"""

import json
from pathlib import Path

from diffinite.cli import main
from diffinite.pipeline import run_pipeline


def _threshold(report_json: str) -> float:
    data = json.loads(Path(report_json).read_text(encoding="utf-8"))
    return data["metadata"]["threshold"]


def test_library_default_threshold_is_percent_scale(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    rj = str(tmp_path / "lib.json")
    # Library default min_jaccard = 0.05 → recorded as 5.0 (percent).
    run_pipeline(dir_a=str(a), dir_b=str(b), report_json=rj, exec_mode="simple")
    assert _threshold(rj) == 5.0


def test_cli_and_library_agree_on_scale(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    rj = str(tmp_path / "cli.json")
    main([str(a), str(b), "--report-json", rj, "--threshold-deep", "5"])
    assert _threshold(rj) == 5.0
