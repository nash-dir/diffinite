"""Regression tests for residual completeness and bundle-integrity threats."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest


def _paired_dirs(tmp_path: Path, name: str = "a.py") -> tuple[Path, Path]:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / name).write_text("value = 1\n", encoding="utf-8")
    (right / name).write_text("value = 2\n", encoding="utf-8")
    return left, right


def test_deep_explicit_encoding_failure_is_fail_closed(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    (left / "a.py").write_bytes(b"value = '\xff'\n")
    (right / "a.py").write_bytes(b"value = '\xfe'\n")

    with pytest.raises(RuntimeError, match="Deep Compare|partial|decode|read"):
        run_pipeline(
            str(left),
            str(right),
            workers=1,
            encoding="ascii",
            report_json=str(tmp_path / "report.json"),
        )


def test_deep_explicit_encoding_failure_is_detailed_when_partial_allowed(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    (left / "a.py").write_bytes(b"value = '\xff'\n")
    (right / "a.py").write_bytes(b"value = '\xfe'\n")
    output = tmp_path / "report.json"

    run_pipeline(
        str(left),
        str(right),
        workers=1,
        encoding="ascii",
        allow_partial=True,
        report_json=str(output),
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["analysis_status"]["state"] == "incomplete"
    assert report["analysis_status"]["deep"]["failed_file_count"] == 2
    assert {item["path"] for item in report["analysis_status"]["deep"]["failed_files"]} == {"a.py"}
    assert all(
        "decode" in item["reason"] or "read" in item["reason"]
        for item in report["analysis_status"]["deep"]["failed_files"]
    )


def test_simple_mode_reports_normalize_as_not_applied(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    output = tmp_path / "report.json"
    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        normalize=True,
        lang_aware=True,
        report_json=str(output),
        workers=1,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["normalize"] is False
    assert report["metadata"]["lang_aware"] is False
    assert report["metadata"]["threshold_provenance"] == "legacy-uncalibrated"
    assert report["preprocessing"]["fingerprint_normalize"] is False
    assert report["preprocessing"]["lang_aware"] is False


def test_bundle_refuses_source_bytes_that_no_longer_match_manifest(tmp_path):
    from diffinite.evidence import (
        SourceIntegrityError,
        compute_file_hashes,
        create_evidence_bundle,
        write_manifest,
    )

    left, right = _paired_dirs(tmp_path)
    hashes_a = compute_file_hashes(str(left), ["a.py"])
    hashes_b = compute_file_hashes(str(right), ["a.py"])
    manifest = tmp_path / "manifest.sha256.json"
    write_manifest(str(left), str(right), hashes_a, hashes_b, [], str(manifest))
    (left / "a.py").write_text("value = 999\n", encoding="utf-8")
    bundle = tmp_path / "evidence.zip"

    with pytest.raises(SourceIntegrityError, match="manifest|hash|changed"):
        create_evidence_bundle(
            str(left),
            str(right),
            ["a.py"],
            ["a.py"],
            str(manifest),
            [],
            str(bundle),
        )
    assert not bundle.exists()
    assert not Path(f"{bundle}.sha256").exists()


def test_bundle_rejects_noncanonical_archive_paths(tmp_path):
    from diffinite.evidence import SourceIntegrityError, create_evidence_bundle

    left, right = _paired_dirs(tmp_path)
    digest = hashlib.sha256((left / "a.py").read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.sha256.json"
    manifest.write_text(
        json.dumps(
            {
                "source_a": {"files": [{"path": "folder/../a.py", "sha256": digest}]},
                "source_b": {"files": []},
                "reports": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SourceIntegrityError, match="Unsafe.*archive path"):
        create_evidence_bundle(
            str(left),
            str(right),
            ["folder/../a.py"],
            [],
            str(manifest),
            [],
            str(tmp_path / "evidence.zip"),
        )


def test_bundle_output_cannot_overwrite_an_evidence_input(tmp_path):
    from diffinite.evidence import (
        SourceIntegrityError,
        create_evidence_bundle,
        write_manifest,
    )

    left, right = _paired_dirs(tmp_path)
    report = tmp_path / "report.zip"
    original_report = b"report bytes"
    report.write_bytes(original_report)
    manifest = tmp_path / "manifest.sha256.json"
    write_manifest(str(left), str(right), [], [], [str(report)], str(manifest))

    with pytest.raises(SourceIntegrityError, match="collides|overwrite"):
        create_evidence_bundle(
            str(left),
            str(right),
            [],
            [],
            str(manifest),
            [str(report)],
            str(report),
        )
    assert report.read_bytes() == original_report


def test_no_merge_reports_are_hashed_and_bundled(monkeypatch, tmp_path):
    from diffinite.pipeline import run_pipeline

    monkeypatch.chdir(tmp_path)
    left, right = _paired_dirs(tmp_path)
    report_anchor = tmp_path / "report.html"
    bundle = tmp_path / "evidence.zip"
    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(report_anchor),
        bundle_path=str(bundle),
    )

    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    report_entries = {item["path"]: item for item in manifest["reports"]}
    assert "report_files/index.html" in report_entries
    index_bytes = (tmp_path / "report_files" / "index.html").read_bytes()
    assert (
        report_entries["report_files/index.html"]["sha256"]
        == hashlib.sha256(index_bytes).hexdigest()
    )
    with zipfile.ZipFile(bundle) as archive:
        assert archive.read("report_files/index.html") == index_bytes


def test_no_merge_html_and_pdf_with_same_stem_both_survive(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)

    def fake_html_to_pdf(_html, destination):
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return True

    monkeypatch.setattr(pipeline, "html_to_pdf", fake_html_to_pdf)
    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(tmp_path / "report.html"),
        report_pdf=str(tmp_path / "report.pdf"),
    )

    output_tree = tmp_path / "report_files"
    assert (output_tree / "index.html").is_file()
    assert (output_tree / "000_cover.pdf").is_file()
    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    report_paths = {entry["path"] for entry in manifest["reports"]}
    assert "report_files/index.html" in report_paths
    assert "report_files/000_cover.pdf" in report_paths


def test_no_merge_replaces_verified_prior_tree_with_exact_current_artifact_set(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    output_tree = tmp_path / "report_files"

    def fake_html_to_pdf(_html, destination):
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return True

    monkeypatch.setattr(pipeline, "html_to_pdf", fake_html_to_pdf)
    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(tmp_path / "report.html"),
        report_pdf=str(tmp_path / "report.pdf"),
    )
    stale_pdf_paths = tuple(output_tree.rglob("*.pdf"))
    assert stale_pdf_paths

    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(tmp_path / "report.html"),
    )

    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    assert not any(stale.exists() for stale in stale_pdf_paths)
    manifest_tree_paths = {
        entry["path"] for entry in manifest["reports"] if entry["path"].startswith("report_files/")
    }
    actual_tree_paths = {
        path.relative_to(tmp_path).as_posix() for path in output_tree.rglob("*") if path.is_file()
    }
    assert actual_tree_paths == manifest_tree_paths


def test_no_merge_refuses_to_delete_unknown_file_from_prior_split_tree(tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    anchor = tmp_path / "report.html"
    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(anchor),
    )
    output_tree = tmp_path / "report_files"
    notes = output_tree / "notes.txt"
    notes.write_bytes(b"user notes must survive")
    prior_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in output_tree.rglob("*")
        if path.is_file()
    }
    prior_manifest = (tmp_path / "manifest.sha256.json").read_bytes()

    with pytest.raises(pipeline.SourceIntegrityError, match="unknown files"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            no_merge=True,
            report_html=str(anchor),
        )

    assert notes.read_bytes() == b"user notes must survive"
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in output_tree.rglob("*")
        if path.is_file()
    } == prior_files
    assert (tmp_path / "manifest.sha256.json").read_bytes() == prior_manifest


def test_pdf_render_failure_does_not_leave_a_success_manifest(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    output = tmp_path / "report.pdf"
    monkeypatch.setattr(pipeline, "html_to_pdf", lambda *args, **kwargs: False)

    with pytest.raises(RuntimeError, match="PDF|render"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_pdf=str(output),
        )
    assert not output.exists()
    assert not (tmp_path / "manifest.sha256.json").exists()
