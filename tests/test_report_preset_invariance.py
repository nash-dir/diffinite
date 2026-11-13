"""Report presets must not change any analysis result.

The VS Code extension's report presets (vscode-extension/src/reportPresets.ts)
only toggle output flags: --page-number, --file-number, --bates-number
(+ prefix/suffix/start) and --hash. These tests run the real CLI with the
flag sets of each preset and require byte-identical JSON reports, so a
future change that lets an output flag leak into matching, diffing or
fingerprinting fails here.
"""

import json
from pathlib import Path

import pytest

from diffinite.cli import main

# Mirrors REPORT_PRESETS in vscode-extension/src/reportPresets.ts.
PRESET_FLAGS = {
    "configured-none": [],
    "technical": ["--page-number", "--file-number"],
    "evidence": [
        "--page-number",
        "--file-number",
        "--bates-number",
        # "=" form, as buildCoreArgs passes it: a suffix may start with "-".
        "--bates-prefix=CASE-",
        "--bates-suffix=-CONFIDENTIAL",
        "--bates-start",
        "7",
        "--hash",
    ],
}


def _make_sources(root: Path) -> tuple[Path, Path]:
    a, b = root / "A", root / "B"
    (a / "pkg").mkdir(parents=True)
    (b / "pkg").mkdir(parents=True)
    body = "".join(f"def f{i}(x):\n    return x * {i} + {i % 7}\n\n" for i in range(40))
    (a / "pkg" / "core.py").write_text(body, encoding="utf-8")
    (b / "pkg" / "core.py").write_text(body.replace("x * 3", "x * 33"), encoding="utf-8")
    (a / "util.py").write_text("import os\n\nprint(os.sep)\n", encoding="utf-8")
    (b / "util.py").write_text("import sys\n\nprint(sys.argv)\n", encoding="utf-8")
    (a / "only_a.py").write_text("x = 1\n", encoding="utf-8")
    (b / "한글 파일 (b).py").write_text("y = 2\n", encoding="utf-8")
    return a, b


def _run(tmp: Path, a: Path, b: Path, mode: str, preset: str, fmt: str) -> dict:
    out = tmp / f"{mode}-{preset}-{fmt}"
    out.mkdir()
    json_path = out / "report.json"
    main(
        [
            "--mode",
            mode,
            f"--report-{fmt}",
            str(out / f"report.{fmt}"),
            "--report-json",
            str(json_path),
            *PRESET_FLAGS[preset],
            "--",
            str(a),
            str(b),
        ]
    )
    return json.loads(json_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mode", ["simple", "deep"])
@pytest.mark.parametrize("fmt", ["html", "md"])
def test_presets_produce_identical_json_metrics(tmp_path: Path, mode: str, fmt: str) -> None:
    a, b = _make_sources(tmp_path / "src")
    reports = {p: _run(tmp_path, a, b, mode, p, fmt) for p in PRESET_FLAGS}

    baseline = reports["configured-none"]
    assert baseline["summary"]["matched_pairs"] >= 2
    for preset, report in reports.items():
        assert report == baseline, f"preset {preset!r} changed the JSON report in {mode} mode"


def test_pdf_presets_produce_identical_json_metrics(tmp_path: Path) -> None:
    """PDF is the only format where Bates/page/file numbers take effect."""
    a, b = _make_sources(tmp_path / "src")
    technical = _run(tmp_path, a, b, "deep", "technical", "pdf")
    evidence = _run(tmp_path, a, b, "deep", "evidence", "pdf")
    assert technical == evidence
    assert (tmp_path / "deep-evidence-pdf" / "report.pdf").stat().st_size > 0
