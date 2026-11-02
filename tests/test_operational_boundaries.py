"""Regression tests for source/output boundaries and completeness accounting."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
from pathlib import Path

import pytest


def _paired_dirs(tmp_path: Path, names: tuple[str, ...] = ("a.py",)) -> tuple[Path, Path]:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    for name in names:
        (left / name).write_text(f"left_{name!r}\n", encoding="utf-8")
        (right / name).write_text(f"right_{name!r}\n", encoding="utf-8")
    return left, right


def _boundary_kwargs(tmp_path: Path) -> dict:
    """Minimal complete kwargs for direct output-boundary tests."""
    return {
        "report_pdf": None,
        "report_html": None,
        "report_md": None,
        "report_json": str(tmp_path / "report.json"),
        "manifest_path": str(tmp_path / "manifest.sha256.json"),
        "bundle_path": None,
        "unreadable_log": None,
        "ignore_file": None,
        "filter_json": None,
        "pdf_font": None,
        "no_merge": False,
        "metrics_only": False,
        "show_bates_number": False,
        "uncompared_mode": "inline",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exec_mode": "unsupported"},
        {"workers": 0},
        {"kgram_size": 0},
        {"window_size": 0},
        {"max_index_entries": 0},
        {"threshold": float("nan")},
        {"min_jaccard": float("inf")},
        {"max_file_size_mb": 0},
        {"max_diff_html_size_mb": float("nan")},
    ],
)
def test_library_rejects_invalid_analysis_limits_before_writing(tmp_path, kwargs):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    output = tmp_path / "report.json"
    with pytest.raises(ValueError):
        run_pipeline(
            str(left),
            str(right),
            report_json=str(output),
            **kwargs,
        )
    assert not output.exists()


def test_file_output_cannot_be_a_source_ancestor_directory(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import _validate_output_boundaries

    left, right = _paired_dirs(tmp_path)
    sentinel = (left / "a.py").read_bytes()
    kwargs = _boundary_kwargs(tmp_path / "elsewhere")
    kwargs["report_json"] = str(tmp_path)

    with pytest.raises(SourceIntegrityError, match="directory|overlap|source"):
        _validate_output_boundaries(str(left), str(right), **kwargs)

    assert (left / "a.py").read_bytes() == sentinel


def test_output_targets_cannot_have_an_ancestor_relationship(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import _validate_output_boundaries

    left, right = _paired_dirs(tmp_path)
    kwargs = _boundary_kwargs(tmp_path / "outputs")
    kwargs["report_json"] = str(tmp_path / "outputs" / "artifact")
    kwargs["unreadable_log"] = str(tmp_path / "outputs" / "artifact" / "errors.log")

    with pytest.raises(SourceIntegrityError, match="collision|overlap|ancestor"):
        _validate_output_boundaries(str(left), str(right), **kwargs)


def test_split_output_directory_cannot_contain_a_read_policy(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import _validate_output_boundaries

    left, right = _paired_dirs(tmp_path)
    kwargs = _boundary_kwargs(tmp_path / "outputs")
    kwargs.update(
        {
            "report_json": None,
            "report_html": str(tmp_path / "outputs" / "report.html"),
            "ignore_file": str(tmp_path / "outputs" / "report_files" / "entries" / "policy.html"),
            "no_merge": True,
        }
    )

    with pytest.raises(SourceIntegrityError, match="policy|input|overlap|collision"):
        _validate_output_boundaries(str(left), str(right), **kwargs)


def test_output_path_rejects_a_lexical_symlink_component(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import _validate_output_boundaries

    left, right = _paired_dirs(tmp_path)
    real_output = tmp_path / "real-output"
    real_output.mkdir()
    redirect = tmp_path / "redirect"
    try:
        redirect.symlink_to(real_output, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    kwargs = _boundary_kwargs(tmp_path / "elsewhere")
    kwargs["report_json"] = str(redirect / "report.json")
    with pytest.raises(SourceIntegrityError, match="symlink|junction|redirect"):
        _validate_output_boundaries(str(left), str(right), **kwargs)


def test_output_path_rejects_a_lexical_junction_component(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    junction = tmp_path / "junction"
    junction.mkdir()
    real_redirect_check = pipeline._path_is_redirect

    monkeypatch.setattr(
        pipeline,
        "_path_is_redirect",
        lambda path: Path(path) == junction or real_redirect_check(Path(path)),
    )
    kwargs = _boundary_kwargs(tmp_path / "elsewhere")
    kwargs["report_json"] = str(junction / "report.json")

    with pytest.raises(pipeline.SourceIntegrityError, match="symlink|junction"):
        pipeline._validate_output_boundaries(str(left), str(right), **kwargs)


def test_existing_hardlinked_output_is_rejected_before_source_mutation(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import _validate_output_boundaries

    left, right = _paired_dirs(tmp_path)
    source = left / "a.py"
    original = source.read_bytes()
    output = tmp_path / "report.json"
    try:
        os.link(source, output)
    except OSError:
        pytest.skip("hard links are unavailable on this filesystem")

    kwargs = _boundary_kwargs(tmp_path)
    kwargs["report_json"] = str(output)
    with pytest.raises(SourceIntegrityError, match="hard-linked"):
        _validate_output_boundaries(str(left), str(right), **kwargs)

    assert source.read_bytes() == original


def test_output_transaction_keeps_recovery_copy_on_kind_mismatch(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import _OutputTarget, _OutputTransaction

    target = tmp_path / "report.json"
    old_bytes = b'{"old": true}\n'
    target.write_bytes(old_bytes)
    transaction = _OutputTransaction(
        [
            _OutputTarget("JSON report", target, is_directory=False),
        ]
    )

    target.unlink()
    target.mkdir()
    sentinel = target / "do-not-delete.txt"
    sentinel.write_text("concurrent data", encoding="utf-8")

    with pytest.raises(SourceIntegrityError, match="recovery|backup") as raised:
        transaction.rollback()

    assert sentinel.read_text(encoding="utf-8") == "concurrent data"
    recovery_path = transaction.recovery_path
    assert recovery_path is not None
    assert recovery_path.exists()
    assert str(recovery_path) in str(raised.value)
    assert old_bytes in [path.read_bytes() for path in recovery_path.rglob("*") if path.is_file()]
    shutil.rmtree(recovery_path)


def test_output_transaction_revalidates_paths_before_each_operation(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    target = tmp_path / "report.json"
    target.write_text("old\n", encoding="utf-8")
    calls = 0
    original_check = pipeline._reject_redirecting_components

    def fail_after_backup(path, *, label):
        nonlocal calls
        calls += 1
        original_check(path, label=label)
        if calls > 1:
            raise pipeline.SourceIntegrityError("simulated path retarget")

    monkeypatch.setattr(pipeline, "_reject_redirecting_components", fail_after_backup)
    transaction = pipeline._OutputTransaction(
        [
            pipeline._OutputTarget("JSON report", target, is_directory=False),
        ]
    )
    operation_ran = False

    def mutate():
        nonlocal operation_ran
        operation_ran = True
        target.write_text("new\n", encoding="utf-8")

    with pytest.raises(pipeline.SourceIntegrityError, match="retarget"):
        transaction.run(mutate)

    assert operation_ran is False
    assert target.read_text(encoding="utf-8") == "old\n"


def test_collector_prunes_and_discloses_link_like_directories(monkeypatch, tmp_path):
    from diffinite.collector import collect_files

    root = tmp_path / "source"
    linked = root / "linked"
    linked.mkdir(parents=True)
    (root / "ordinary.py").write_text("ordinary\n", encoding="utf-8")
    (linked / "outside.py").write_text("must not be traversed\n", encoding="utf-8")

    original_is_symlink = Path.is_symlink

    def classify_link(self):
        return self == linked or original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", classify_link)
    skipped: list[str] = []

    assert collect_files(str(root), unreadable_list=skipped) == ["ordinary.py"]
    assert skipped == ["linked (skipped: linked or reparse-point directory)"]


def test_report_output_cannot_overwrite_a_collected_source(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    source = left / "a.py"
    original = source.read_bytes()

    with pytest.raises(SourceIntegrityError, match="output|source|input"):
        run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(source),
        )

    assert source.read_bytes() == original
    assert not (left / "manifest.sha256.json").exists()


def test_default_output_is_rejected_when_working_directory_is_a_source(monkeypatch, tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    monkeypatch.chdir(left)

    with pytest.raises(SourceIntegrityError, match="output|source|input"):
        run_pipeline(str(left), str(right), exec_mode="simple", workers=1)

    assert not (left / "report.pdf").exists()
    assert not (left / "manifest.sha256.json").exists()


def test_split_output_directory_cannot_contain_a_source_root(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import run_pipeline

    left = tmp_path / "report_files" / "left"
    right = tmp_path / "right"
    left.mkdir(parents=True)
    right.mkdir()
    (left / "a.py").write_text("left\n", encoding="utf-8")
    (right / "a.py").write_text("right\n", encoding="utf-8")

    with pytest.raises(SourceIntegrityError, match="overlaps.*source"):
        run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            no_merge=True,
            report_html=str(tmp_path / "report.html"),
        )


def test_manifest_cannot_collide_with_a_requested_report(tmp_path):
    from diffinite.evidence import SourceIntegrityError
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    output = tmp_path / "manifest.sha256.json"
    with pytest.raises(SourceIntegrityError, match="collision"):
        run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(output),
        )
    assert not output.exists()


def test_skipped_collection_entry_fails_closed_by_default(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    original_collect = pipeline.collect_files
    unreadable_log = tmp_path / "unreadable.log"

    def collect_with_skip(directory, ignore_patterns=None, unreadable_list=None):
        files = original_collect(directory, ignore_patterns, unreadable_list)
        if Path(directory).resolve() == left.resolve() and unreadable_list is not None:
            unreadable_list.append(str(left / "hidden.py"))
        return files

    monkeypatch.setattr(pipeline, "collect_files", collect_with_skip)

    with pytest.raises(RuntimeError, match="collection|skipped|incomplete"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "report.json"),
            unreadable_log=str(unreadable_log),
        )

    assert not (tmp_path / "report.json").exists()
    assert "A:hidden.py" in unreadable_log.read_text(encoding="utf-8")
    assert str(tmp_path) not in unreadable_log.read_text(encoding="utf-8")


def test_collection_failure_preserves_existing_unreadable_log(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    original_collect = pipeline.collect_files
    unreadable_log = tmp_path / "unreadable.log"
    prior_bytes = b"prior-run diagnostic\r\n"
    unreadable_log.write_bytes(prior_bytes)

    def collect_with_skip(directory, ignore_patterns=None, unreadable_list=None):
        files = original_collect(directory, ignore_patterns, unreadable_list)
        if Path(directory).resolve() == left.resolve() and unreadable_list is not None:
            unreadable_list.append(str(left / "hidden.py"))
        return files

    monkeypatch.setattr(pipeline, "collect_files", collect_with_skip)

    with pytest.raises(RuntimeError, match="collection|skipped|incomplete"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "report.json"),
            unreadable_log=str(unreadable_log),
        )

    assert unreadable_log.read_bytes() == prior_bytes


def test_hash_failure_preserves_existing_unreadable_log(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    original_hash = pipeline.compute_file_hashes
    unreadable_log = tmp_path / "unreadable.log"
    prior_bytes = b"prior-run diagnostic\n"
    unreadable_log.write_bytes(prior_bytes)

    def omit_left_hash(directory, files):
        hashes = original_hash(directory, files)
        if Path(directory).resolve() == left.resolve():
            return []
        return hashes

    monkeypatch.setattr(pipeline, "compute_file_hashes", omit_left_hash)

    with pytest.raises(RuntimeError, match="hashing failed"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "report.json"),
            unreadable_log=str(unreadable_log),
        )

    assert unreadable_log.read_bytes() == prior_bytes
    assert not (tmp_path / "report.json").exists()


def test_hash_failure_creates_new_privacy_safe_unreadable_log(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    original_hash = pipeline.compute_file_hashes
    unreadable_log = tmp_path / "unreadable.log"

    def omit_left_hash(directory, files):
        hashes = original_hash(directory, files)
        if Path(directory).resolve() == left.resolve():
            return []
        return hashes

    monkeypatch.setattr(pipeline, "compute_file_hashes", omit_left_hash)

    with pytest.raises(RuntimeError, match="hashing failed"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "report.json"),
            unreadable_log=str(unreadable_log),
        )

    content = unreadable_log.read_text(encoding="utf-8")
    assert "A:a.py" in content
    assert str(tmp_path) not in content
    assert not (tmp_path / "report.json").exists()


def test_allow_partial_discloses_privacy_safe_collection_failures(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    original_collect = pipeline.collect_files
    output = tmp_path / "report.json"

    def collect_with_skip(directory, ignore_patterns=None, unreadable_list=None):
        files = original_collect(directory, ignore_patterns, unreadable_list)
        if Path(directory).resolve() == right.resolve() and unreadable_list is not None:
            unreadable_list.append("nested/link.py (skipped: symbolic link)")
        return files

    monkeypatch.setattr(pipeline, "collect_files", collect_with_skip)
    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        allow_partial=True,
        report_json=str(output),
    )

    status = json.loads(output.read_text(encoding="utf-8"))["analysis_status"]
    assert status["state"] == "incomplete"
    assert "collection-file-skipped" in status["reasons"]
    assert status["collection"] == {
        "failed_file_count": 1,
        "failed_files": [
            {
                "side": "B",
                "path": "nested/link.py",
                "reason": "skipped: symbolic link",
            }
        ],
    }
    assert str(tmp_path) not in json.dumps(status)


def test_preserve_tree_names_are_injective_and_do_not_hit_reserved_index(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path, ("same.py", "same.js", "index"))
    output = tmp_path / "report.html"
    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        preserve_tree=True,
        report_html=str(output),
    )

    tree = tmp_path / "report_files"
    expected = {
        "entries/same.py.html",
        "entries/same.js.html",
        "entries/index.html",
    }
    assert {path.relative_to(tree).as_posix() for path in tree.rglob("*.html")} == {
        "index.html",
        *expected,
    }
    index = (tree / "index.html").read_text(encoding="utf-8")
    for link in expected:
        assert f'href="{link}"' in index


def test_preserve_tree_pdf_names_do_not_collide_with_cover(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path, ("same.py", "same.js", "000_cover"))

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
        preserve_tree=True,
        report_pdf=str(tmp_path / "report.pdf"),
    )

    tree = tmp_path / "report_files"
    assert (tree / "000_cover.pdf").is_file()
    assert (tree / "entries" / "same.py.pdf").is_file()
    assert (tree / "entries" / "same.js.pdf").is_file()
    assert (tree / "entries" / "000_cover.pdf").is_file()


def test_metrics_only_manifest_excludes_stale_skipped_formats(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    stale_html = tmp_path / "report.html"
    stale_html.write_text("old report", encoding="utf-8")
    Path(f"{stale_html}.sha256").write_text("old checksum", encoding="utf-8")
    output = tmp_path / "report.json"

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        metrics_only=True,
        report_html=str(stale_html),
        report_json=str(output),
    )

    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    assert {entry["path"] for entry in manifest["reports"]} == {"report.json"}


def test_json_report_uses_privacy_safe_root_labels(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    output = tmp_path / "report.json"
    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        report_json=str(output),
        dir_alias_a="Client A",
        dir_alias_b="Reference B",
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dir_a"] == "Client A"
    assert report["dir_b"] == "Reference B"
    assert str(tmp_path) not in output.read_text(encoding="utf-8")


def test_ignore_policy_and_filter_are_embedded_for_reproduction(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path, ("a.py", "b.py", "ignored.tmp"))
    ignore_file = tmp_path / "case.diffignore"
    ignore_bytes = b"# case policy\n*.tmp\n"
    ignore_file.write_bytes(ignore_bytes)
    filter_file = tmp_path / "selection.json"
    filter_bytes = b'["a.py"]'
    filter_file.write_bytes(filter_bytes)
    output = tmp_path / "report.json"

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        ignore_file=str(ignore_file),
        filter_json=str(filter_file),
        report_json=str(output),
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    config = report["metadata"]
    assert config["ignore_patterns"] == ["*.tmp"]
    assert config["ignore_file_sha256"] == hashlib.sha256(ignore_bytes).hexdigest()
    assert config["filter_applied"] is True
    assert config["filter_paths"] == ["a.py"]
    assert config["filter_file_sha256"] == hashlib.sha256(filter_bytes).hexdigest()
    assert [item["file_a"] for item in report["results"]] == ["a.py"]

    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    assert manifest["analysis_configuration"] == config
    assert {item["path"] for item in manifest["source_a"]["files"]} == {
        "a.py",
        "b.py",
    }


@pytest.mark.parametrize("option", ["ignore_file", "filter_json"])
def test_explicit_missing_policy_input_fails_instead_of_being_ignored(tmp_path, option):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    kwargs = {option: str(tmp_path / "missing-policy-file")}
    with pytest.raises(RuntimeError, match="ignore|filter|policy|read"):
        run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "report.json"),
            **kwargs,
        )
    assert not (tmp_path / "report.json").exists()


def test_no_merge_removes_stale_merged_anchor_and_sidecars(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    anchor = tmp_path / "report.html"
    anchor.write_text("old merged report", encoding="utf-8")
    sidecars = (Path(f"{anchor}.sha256"), Path(f"{anchor}.sig"))
    for sidecar in sidecars:
        sidecar.write_text("old sidecar", encoding="utf-8")

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(anchor),
    )

    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in manifest["reports"]}
    assert not anchor.exists()
    assert not any(sidecar.exists() for sidecar in sidecars)
    assert "report.html" not in paths
    assert "report.html.sha256" not in paths
    assert "report.html.sig" not in paths
    assert "report_files/index.html" in paths


def test_no_merge_removes_stale_merged_pdf_anchor_index_and_sidecars(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    anchor = tmp_path / "report.pdf"
    stale_paths = (
        anchor,
        anchor.with_suffix(".csv"),
        Path(f"{anchor}.sha256"),
        Path(f"{anchor}.sig"),
    )
    for stale in stale_paths:
        stale.write_bytes(b"old merged evidence")

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
        report_pdf=str(anchor),
    )

    assert not any(stale.exists() for stale in stale_paths)
    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in manifest["reports"]}
    assert "report_files/000_cover.pdf" in paths
    assert not any(path in paths for path in ("report.pdf", "report.csv"))


def test_no_merge_failure_restores_prior_merged_and_split_evidence(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    anchor = tmp_path / "report.html"
    checksum = Path(f"{anchor}.sha256")
    split_tree = tmp_path / "report_files"
    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        no_merge=True,
        report_html=str(anchor),
    )
    anchor.write_bytes(b"old merged report")
    checksum.write_bytes(b"old checksum")
    original_tree = {
        path.relative_to(split_tree).as_posix(): path.read_bytes()
        for path in split_tree.rglob("*")
        if path.is_file()
    }
    original_manifest = (tmp_path / "manifest.sha256.json").read_bytes()

    original_generate = pipeline._generate_individual_html

    def generate_then_fail(*args, **kwargs):
        original_generate(*args, **kwargs)
        raise RuntimeError("injected split publication failure")

    monkeypatch.setattr(pipeline, "_generate_individual_html", generate_then_fail)
    with pytest.raises(RuntimeError, match="injected split publication failure"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            no_merge=True,
            report_html=str(anchor),
        )

    assert anchor.read_bytes() == b"old merged report"
    assert checksum.read_bytes() == b"old checksum"
    assert {
        path.relative_to(split_tree).as_posix(): path.read_bytes()
        for path in split_tree.rglob("*")
        if path.is_file()
    } == original_tree
    assert (tmp_path / "manifest.sha256.json").read_bytes() == original_manifest


def test_no_merge_rejects_an_unexpected_generated_artifact(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    original_generate = pipeline._generate_individual_html

    def generate_with_unexpected_file(*args, **kwargs):
        original_generate(*args, **kwargs)
        anchor = Path(args[8])
        tree = anchor.parent / f"{anchor.stem}_files"
        (tree / "unexpected.html").write_text("not generated", encoding="utf-8")

    monkeypatch.setattr(
        pipeline,
        "_generate_individual_html",
        generate_with_unexpected_file,
    )

    with pytest.raises(pipeline.SourceIntegrityError, match="artifact set mismatch"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            no_merge=True,
            report_html=str(tmp_path / "report.html"),
        )

    assert not (tmp_path / "report_files").exists()
    assert not (tmp_path / "manifest.sha256.json").exists()


def test_post_bundle_report_mutation_rolls_back_the_entire_output_set(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    report = tmp_path / "report.json"
    manifest = tmp_path / "manifest.sha256.json"
    bundle = tmp_path / "evidence.zip"
    original_bundle = pipeline.create_evidence_bundle

    def create_then_mutate(*args, **kwargs):
        digest = original_bundle(*args, **kwargs)
        report.write_text('{"changed": true}\n', encoding="utf-8")
        return digest

    monkeypatch.setattr(pipeline, "create_evidence_bundle", create_then_mutate)

    with pytest.raises(
        pipeline.SourceIntegrityError,
        match="report changed|output commit",
    ):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(report),
            bundle_path=str(bundle),
        )

    assert not report.exists()
    assert not manifest.exists()
    assert not bundle.exists()
    assert not Path(f"{bundle}.sha256").exists()


def test_success_removes_stale_optional_diagnostic_outputs(tmp_path):
    from diffinite.pipeline import run_pipeline

    left, right = _paired_dirs(tmp_path)
    report = tmp_path / "report.json"
    uncompared = tmp_path / "report_uncompared.txt"
    unreadable = tmp_path / "unreadable.log"
    uncompared.write_text("old unmatched files\n", encoding="utf-8")
    unreadable.write_text("old read failures\n", encoding="utf-8")

    run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        report_json=str(report),
        uncompared_mode="separate",
        unreadable_log=str(unreadable),
    )

    assert not uncompared.exists()
    assert not unreadable.exists()


def test_current_unreadable_log_is_hashed_as_a_report_artifact(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    report = tmp_path / "report.json"
    unreadable = tmp_path / "unreadable.log"
    original_collect = pipeline.collect_files

    def collect_with_diagnostic(*args, **kwargs):
        files = original_collect(*args, **kwargs)
        failures = kwargs.get("unreadable_list")
        if failures is not None:
            failures.append("blocked.py (simulated collection failure)")
        return files

    monkeypatch.setattr(pipeline, "collect_files", collect_with_diagnostic)
    pipeline.run_pipeline(
        str(left),
        str(right),
        exec_mode="simple",
        workers=1,
        report_json=str(report),
        unreadable_log=str(unreadable),
        allow_partial=True,
    )

    manifest = json.loads((tmp_path / "manifest.sha256.json").read_text(encoding="utf-8"))
    report_paths = {entry["path"] for entry in manifest["reports"]}
    assert "unreadable.log" in report_paths


def test_failed_later_format_restores_prior_report_set(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    json_report = tmp_path / "report.json"
    pdf_report = tmp_path / "report.pdf"
    manifest = tmp_path / "manifest.sha256.json"
    old_json = b'{"prior": true}\n'
    old_pdf = b"%PDF-prior\n"
    old_manifest = b'{"prior_manifest": true}\n'
    json_report.write_bytes(old_json)
    pdf_report.write_bytes(old_pdf)
    manifest.write_bytes(old_manifest)
    monkeypatch.setattr(pipeline, "html_to_pdf", lambda *args, **kwargs: False)

    with pytest.raises(RuntimeError, match="PDF|render"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(json_report),
            report_pdf=str(pdf_report),
        )

    assert json_report.read_bytes() == old_json
    assert pdf_report.read_bytes() == old_pdf
    assert manifest.read_bytes() == old_manifest


def test_source_file_added_during_output_rolls_back_prior_report_set(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline
    from diffinite.evidence import SourceIntegrityError

    left, right = _paired_dirs(tmp_path)
    json_report = tmp_path / "report.json"
    manifest = tmp_path / "manifest.sha256.json"
    old_json = b'{"prior": true}\n'
    old_manifest = b'{"prior_manifest": true}\n'
    json_report.write_bytes(old_json)
    manifest.write_bytes(old_manifest)
    original_generate = pipeline._generate_json_report

    def generate_then_add_source(*args, **kwargs):
        original_generate(*args, **kwargs)
        (left / "added_during_run.py").write_text("new evidence\n", encoding="utf-8")

    monkeypatch.setattr(pipeline, "_generate_json_report", generate_then_add_source)

    with pytest.raises(SourceIntegrityError, match="A:added:added_during_run.py"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(json_report),
        )

    assert json_report.read_bytes() == old_json
    assert manifest.read_bytes() == old_manifest


def test_bundle_failure_restores_prior_reports_and_manifest(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    json_report = tmp_path / "report.json"
    manifest = tmp_path / "manifest.sha256.json"
    bundle = tmp_path / "evidence.zip"
    old_json = b'{"prior": true}\n'
    old_manifest = b'{"prior_manifest": true}\n'
    old_bundle = b"prior bundle"
    old_sidecar = b"prior checksum"
    json_report.write_bytes(old_json)
    manifest.write_bytes(old_manifest)
    bundle.write_bytes(old_bundle)
    Path(f"{bundle}.sha256").write_bytes(old_sidecar)

    def fail_bundle(*args, **kwargs):
        raise OSError("injected bundle publication failure")

    monkeypatch.setattr(pipeline, "create_evidence_bundle", fail_bundle)
    with pytest.raises(OSError, match="injected bundle"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(json_report),
            bundle_path=str(bundle),
        )

    assert json_report.read_bytes() == old_json
    assert manifest.read_bytes() == old_manifest
    assert bundle.read_bytes() == old_bundle
    assert Path(f"{bundle}.sha256").read_bytes() == old_sidecar


def test_snapshot_changed_during_analysis_rolls_back_and_cleans(monkeypatch, tmp_path):
    import diffinite.pipeline as pipeline
    from diffinite.evidence import SourceIntegrityError

    left, right = _paired_dirs(tmp_path)
    json_report = tmp_path / "report.json"
    manifest = tmp_path / "manifest.sha256.json"
    old_json = b'{"prior": true}\n'
    old_manifest = b'{"prior_manifest": true}\n'
    json_report.write_bytes(old_json)
    manifest.write_bytes(old_manifest)

    snapshot_roots: list[Path] = []
    original_snapshot = pipeline.create_immutable_snapshot

    def capture_snapshot(*args, **kwargs):
        result = original_snapshot(*args, **kwargs)
        snapshot_roots.append(Path(result))
        return result

    original_worker = pipeline._process_match_chunk

    def tamper_snapshot(worker_id, chunk, dir_a, dir_b, *args, **kwargs):
        if chunk:
            source = Path(dir_a) / chunk[0].rel_path_a
            source.write_text("tampered analysis bytes\n", encoding="utf-8")
        return original_worker(worker_id, chunk, dir_a, dir_b, *args, **kwargs)

    monkeypatch.setattr(pipeline, "create_immutable_snapshot", capture_snapshot)
    monkeypatch.setattr(pipeline, "_process_match_chunk", tamper_snapshot)

    with pytest.raises(SourceIntegrityError, match="snapshot A bytes changed"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(json_report),
        )

    assert json_report.read_bytes() == old_json
    assert manifest.read_bytes() == old_manifest
    assert snapshot_roots
    assert not snapshot_roots[0].parent.exists()


def test_manifest_digest_failure_restores_old_and_removes_new_outputs(
    monkeypatch,
    tmp_path,
):
    import diffinite.pipeline as pipeline

    left, right = _paired_dirs(tmp_path)
    json_report = tmp_path / "report.json"
    manifest = tmp_path / "manifest.sha256.json"
    old_json = b'{"prior": true}\n'
    json_report.write_bytes(old_json)

    snapshot_roots: list[Path] = []
    original_snapshot = pipeline.create_immutable_snapshot

    def capture_snapshot(*args, **kwargs):
        result = original_snapshot(*args, **kwargs)
        snapshot_roots.append(Path(result))
        return result

    original_hash = pipeline._sha256_file

    def fail_manifest_digest(path):
        if Path(path) == manifest:
            raise OSError("injected manifest digest failure")
        return original_hash(path)

    monkeypatch.setattr(pipeline, "create_immutable_snapshot", capture_snapshot)
    monkeypatch.setattr(pipeline, "_sha256_file", fail_manifest_digest)

    with pytest.raises(OSError, match="injected manifest digest failure"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(json_report),
        )

    assert json_report.read_bytes() == old_json
    assert not manifest.exists()
    assert snapshot_roots
    assert not snapshot_roots[0].parent.exists()
