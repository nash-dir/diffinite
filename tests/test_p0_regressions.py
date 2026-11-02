"""Regression tests for cross-layer correctness and evidence completeness."""

from __future__ import annotations

import hashlib
import json
import zipfile
from concurrent.futures import Future
import pytest


def test_raw_auto_threshold_is_explicitly_legacy_uncalibrated(monkeypatch, tmp_path):
    from diffinite import cli

    captured = {}
    monkeypatch.setattr(cli, "run_pipeline", lambda **kwargs: captured.update(kwargs))
    cli.main([str(tmp_path / "a"), str(tmp_path / "b"), "--report-json", str(tmp_path / "r.json")])

    meta = captured["metadata"]
    assert meta.threshold == 5.0
    assert meta.threshold_provenance == "legacy-uncalibrated"


@pytest.mark.parametrize(
    ("normalize", "manual", "expected", "provenance"),
    [
        (False, None, 5.0, "legacy-uncalibrated"),
        (True, None, 93.0, "normalize-default"),
        (False, 17.0, 17.0, "user"),
        (True, 17.0, 17.0, "user"),
    ],
)
def test_effective_threshold_matrix(normalize, manual, expected, provenance):
    from diffinite.cli import _resolve_threshold_deep

    assert _resolve_threshold_deep(manual, normalize) == (expected, provenance)


def test_json_schema_records_canonical_configuration_and_preprocessing(tmp_path):
    from diffinite.cli import main

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.js").write_text("const x = 1; // left\n", encoding="utf-8")
    (right / "a.js").write_text("const x = 1; // right\n", encoding="utf-8")
    output = tmp_path / "report.json"

    main([str(left), str(right), "--normalize", "--report-json", str(output), "--workers", "1"])
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["schema_version"] == 2
    assert report["metadata"]["threshold"] == 93.0
    assert report["metadata"]["threshold_provenance"] == "normalize-default"
    assert report["metadata"]["normalize"] is True
    assert report["metadata"]["calibration_status"] == "unvalidated-profile"
    assert report["metadata"]["calibration_profile_mismatches"] == ["strip_comments"]
    assert "unvalidated profile" in report["metadata"]["calibration_disclosure"].lower()
    assert "0.95%" not in report["metadata"]["calibration_disclosure"]
    assert report["preprocessing"]["line_diff_comments"] == "included"
    assert report["preprocessing"]["deep_compare_comments"] == "included"
    assert report["analysis_status"]["state"] == "complete"


def test_json_quotes_calibration_only_for_the_exact_validated_profile(tmp_path):
    from diffinite.calibration import NORMALIZE_FP_RATE_PCT
    from diffinite.cli import main

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.js").write_text("const x = 1; // left\n", encoding="utf-8")
    (right / "a.js").write_text("const x = 1; // right\n", encoding="utf-8")
    output = tmp_path / "report.json"

    main(
        [
            str(left),
            str(right),
            "--normalize",
            "--strip-comments",
            "--report-json",
            str(output),
            "--workers",
            "1",
        ]
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["metadata"]["calibration_status"] == "applicable"
    assert report["metadata"]["calibration_profile_mismatches"] == []
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" in report["metadata"]["calibration_disclosure"]


def test_library_report_metadata_is_derived_from_actual_execution(tmp_path):
    from diffinite.models import AnalysisMetadata
    from diffinite.pipeline import run_pipeline

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.py").write_text("value = 1\n", encoding="utf-8")
    (right / "a.py").write_text("value = 2\n", encoding="utf-8")
    output = tmp_path / "report.json"
    stale = AnalysisMetadata(
        exec_mode="simple",
        k=99,
        w=99,
        threshold=93.0,
        autojunk=True,
        threshold_provenance="normalize-default",
        normalize=False,
    )

    run_pipeline(
        str(left),
        str(right),
        exec_mode="deep",
        workers=1,
        kgram_size=5,
        window_size=4,
        min_jaccard=0.17,
        normalize=True,
        autojunk=False,
        metadata=stale,
        report_json=str(output),
    )
    metadata = json.loads(output.read_text(encoding="utf-8"))["metadata"]
    assert metadata["exec_mode"] == "deep"
    assert metadata["k"] == 5
    assert metadata["w"] == 4
    assert metadata["threshold"] == 17.0
    assert metadata["threshold_provenance"] == "user"
    assert metadata["normalize"] is True
    assert metadata["autojunk"] is False


def test_semantic_configuration_is_identical_in_json_and_manifest(tmp_path):
    from diffinite.pipeline import run_pipeline

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.py").write_text("value = 1\n", encoding="utf-8")
    (right / "a.py").write_text("value = 2\n", encoding="utf-8")
    output = tmp_path / "report.json"

    run_pipeline(
        str(left),
        str(right),
        report_json=str(output),
        workers=1,
        threshold=73.0,
        by_word=True,
        strip_comments=True,
        squash_blanks=True,
        normalize_ws=True,
        encoding="utf-8",
        binary_handling="error",
        max_file_size_mb=3.5,
        max_diff_html_size_mb=1.25,
        max_index_entries=1234,
        detect_moved=True,
        autojunk=False,
        uncompared_mode="none",
        allow_partial=True,
        collapse_identical=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    config = report["metadata"]
    assert manifest["analysis_configuration"] == config
    assert config["filename_threshold"] == 73.0
    assert config["by_word"] is True
    assert config["strip_comments"] is True
    assert config["squash_blanks"] is True
    assert config["normalize_whitespace"] is True
    assert config["encoding"] == "utf-8"
    assert config["binary_handling"] == "error"
    assert config["max_file_size_mb"] == 3.5
    assert config["max_diff_html_size_mb"] == 1.25
    assert config["max_index_entries"] == 1234
    assert config["detect_moved"] is True
    assert config["autojunk"] is False
    assert config["uncompared_mode"] == "none"
    assert config["allow_partial"] is True
    assert config["collapse_identical"] is True
    assert report["comparison_unit"] == "word"
    assert report["preprocessing"]["line_diff_comments"] == "stripped"
    assert report["preprocessing"]["normalize_whitespace"] is True


def test_deep_compare_obeys_actual_comment_preprocessing(tmp_path):
    from diffinite.deep_compare import run_deep_compare

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    comment = "// alpha beta gamma delta epsilon zeta eta theta iota kappa\n"
    (left / "a.js").write_text(comment, encoding="utf-8")
    (right / "a.js").write_text(comment, encoding="utf-8")

    included = run_deep_compare(
        str(left),
        str(right),
        ["a.js"],
        ["a.js"],
        workers=1,
        min_jaccard=0.01,
        strip_comments=False,
    )
    stripped = run_deep_compare(
        str(left),
        str(right),
        ["a.js"],
        ["a.js"],
        workers=1,
        min_jaccard=0.01,
        strip_comments=True,
    )

    assert included
    assert stripped == []


def test_policy_excluded_binary_pair_is_counted_as_processed(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "asset.bin").write_bytes(b"\x00\x01left")
    (right / "asset.bin").write_bytes(b"\x00\x01right")
    output = tmp_path / "report.json"
    monkeypatch.setattr(pipeline, "read_file", lambda *args, **kwargs: None)

    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        binary_handling="exclude",
        report_json=str(output),
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["results"] == []
    assert report["analysis_status"]["diff"]["requested_pair_count"] == 1
    assert report["analysis_status"]["diff"]["successful_pair_count"] == 1
    assert report["analysis_status"]["diff"]["failed_pair_count"] == 0
    assert report["analysis_status"]["state"] == "complete"


class _OneWorkerFailsExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def submit(self, fn, worker_id, chunk, *args):
        future = Future()
        if worker_id == 2:
            future.set_exception(RuntimeError("deterministic worker failure"))
        else:
            future.set_result(fn(worker_id, chunk, *args))
        return future


def _two_pair_dirs(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    for name in ("a.py", "b.py"):
        (left / name).write_text("x = 1\n", encoding="utf-8")
        (right / name).write_text("x = 2\n", encoding="utf-8")
    return left, right


def test_partial_render_worker_failure_is_fail_closed_by_default(monkeypatch, tmp_path):
    import concurrent.futures
    from diffinite.pipeline import run_pipeline

    left, right = _two_pair_dirs(tmp_path)
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", _OneWorkerFailsExecutor)

    with pytest.raises(RuntimeError, match="worker|incomplete|missing"):
        run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=2,
            report_json=str(tmp_path / "report.json"),
        )


def test_allow_partial_records_failed_pairs(monkeypatch, tmp_path):
    import concurrent.futures
    from diffinite.pipeline import run_pipeline

    left, right = _two_pair_dirs(tmp_path)
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", _OneWorkerFailsExecutor)
    output = tmp_path / "report.json"
    html_output = tmp_path / "report.html"

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=2,
        report_json=str(output),
        report_html=str(html_output),
        no_merge=True,
        allow_partial=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["analysis_status"]["state"] == "incomplete"
    assert report["analysis_status"]["diff"]["failed_pair_count"] == 1
    assert report["analysis_status"]["diff"]["failed_pairs"][0]["file_a"] == "b.py"
    index_html = (tmp_path / "report_files" / "index.html").read_text(encoding="utf-8")
    pair_html = (tmp_path / "report_files" / "entries" / "a.py.html").read_text(encoding="utf-8")
    for rendered in (index_html, pair_html):
        assert "Incomplete analysis" in rendered
        assert "1/2 processed" in rendered
        assert "b.py" in rendered


def test_truncated_diff_is_serialized_as_incomplete_without_full_result_claim(tmp_path):
    from diffinite.pipeline import run_pipeline

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.py").write_text("\n".join(f"left_{i} = {i}" for i in range(80)), encoding="utf-8")
    (right / "a.py").write_text("\n".join(f"right_{i} = {i}" for i in range(80)), encoding="utf-8")
    output = tmp_path / "report.json"

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        max_diff_html_size_mb=0.0001,
        report_json=str(output),
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    result = report["results"][0]
    assert result["truncation"]["truncated"] is True
    assert result["truncation"]["omitted_bytes"] > 0
    assert "full diff" not in result["html_diff"].lower()
    assert report["analysis_status"]["state"] == "incomplete"


def test_source_change_after_initial_hash_fails_closed(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    source = left / "a.py"
    source.write_bytes(b"x = 1\n")
    (right / "a.py").write_bytes(b"x = 1\n")

    original = pipeline.compute_file_hashes
    calls = 0

    def mutate_after_hash(root, files):
        nonlocal calls
        result = original(root, files)
        calls += 1
        if calls == 1:
            source.write_bytes(b"x = 999\n")
        return result

    monkeypatch.setattr(pipeline, "compute_file_hashes", mutate_after_hash)

    with pytest.raises(RuntimeError, match="changed|integrity|snapshot"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "report.json"),
            bundle_path=str(tmp_path / "evidence.zip"),
        )
    assert not (tmp_path / "evidence.zip").exists()


def test_every_bundled_source_matches_manifest_hash(tmp_path):
    from diffinite.pipeline import run_pipeline

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.py").write_bytes(b"alpha\n")
    (right / "a.py").write_bytes(b"beta\n")
    bundle = tmp_path / "evidence.zip"

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        report_json=str(tmp_path / "report.json"),
        bundle_path=str(bundle),
    )

    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.sha256.json"))
        for side_key, prefix in (("source_a", "source_a/"), ("source_b", "source_b/")):
            for entry in manifest[side_key]["files"]:
                bundled = archive.read(prefix + entry["path"])
                assert hashlib.sha256(bundled).hexdigest() == entry["sha256"]
