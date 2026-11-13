"""Audit round 3 — pipeline handoffs (environment, split roots, calibration
re-assessment, selective-report disclosure, worker-pool parent watch)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import diffinite.deep_compare as deep_compare
import diffinite.pipeline as pipeline
from diffinite.models import AnalysisMetadata, AnalysisStatus


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _run(tmp_path: Path, a: dict, b: dict, **kwargs) -> dict:
    left = _tree(tmp_path / "a", a)
    right = _tree(tmp_path / "b", b)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    kwargs.setdefault("exec_mode", "simple")
    kwargs.setdefault("workers", 1)
    kwargs.setdefault("report_json", str(out / "r.json"))
    pipeline.run_pipeline(str(left), str(right), **kwargs)
    return json.loads(Path(kwargs["report_json"]).read_text(encoding="utf-8"))


_JAVA = "".join(f"int v{i} = f({i}, {i * 3});\n" for i in range(60))


# ---------------------------------------------------------------------------
# environment contract: JSON metadata and manifest carry the same dict
# ---------------------------------------------------------------------------
def test_environment_dict_keys_without_lang_aware():
    meta = AnalysisMetadata(
        k=5, w=4, threshold=93.0, exec_mode="deep", python_version="3.12.9", unicodedata_version="15.0.0",
        pygments_version="2.19.1",
    )
    env = pipeline._environment_dict(meta, AnalysisStatus())
    assert env == {
        "python_version": "3.12.9",
        "pygments_version": "2.19.1",
        "unicodedata_version": "15.0.0",
    }


def test_environment_dict_adds_lang_aware_keys_only_when_it_ran():
    status = AnalysisStatus()
    status.deep_lang_aware_fallback_files.append(
        {"side": "A", "path": "x.kt", "tier": "registry:lexer-error-token"}
    )
    meta = AnalysisMetadata(
        k=5, w=4, threshold=93.0, exec_mode="deep", normalize=True, lang_aware=True,
        lang_aware_tiers=((".kt", ("pygments", "registry:lexer-error-token")),),
    )
    env = pipeline._environment_dict(meta, status)
    assert env["lang_aware_tiers"] == {".kt": ["pygments", "registry:lexer-error-token"]}
    assert env["lang_aware_fallback_files"] == [
        {"side": "A", "path": "x.kt", "tier": "registry:lexer-error-token"}
    ]
    # lang_aware set but deep never ran (simple mode): no lang-aware keys.
    simple = AnalysisMetadata(k=5, w=4, threshold=93.0, exec_mode="simple", normalize=True, lang_aware=True)
    assert "lang_aware_tiers" not in pipeline._environment_dict(simple, status)


def test_environment_reaches_json_and_manifest_identically(tmp_path):
    report = _run(
        tmp_path, {"A.java": _JAVA}, {"A.java": _JAVA},
        exec_mode="deep", normalize=True, lang_aware=True,
    )
    env = report["metadata"]["environment"]
    assert env["python_version"] and env["unicodedata_version"]
    assert "pygments_version" in env
    assert ".java" in env["lang_aware_tiers"]
    assert env["lang_aware_fallback_files"] == []
    manifest = json.loads(
        (tmp_path / "out" / "manifest.sha256.json").read_text(encoding="utf-8")
    )
    assert manifest["environment"] == env


# ---------------------------------------------------------------------------
# split_roots: the same explicit list at manifest, bundle and verification
# ---------------------------------------------------------------------------
def test_split_roots_passed_identically_to_manifest_bundle_and_verify(tmp_path, monkeypatch):
    seen: dict[str, object] = {}
    real_manifest = pipeline.write_manifest
    real_bundle = pipeline.create_evidence_bundle
    real_logical = pipeline._logical_report_paths

    def manifest_spy(*args, **kwargs):
        seen["manifest"] = kwargs.get("split_roots")
        seen["environment"] = kwargs.get("environment")
        return real_manifest(*args, **kwargs)

    def bundle_spy(*args, **kwargs):
        seen["bundle"] = kwargs.get("split_roots")
        return real_bundle(*args, **kwargs)

    def logical_spy(report_paths, split_roots=None):
        seen["verify"] = split_roots
        return real_logical(report_paths, split_roots)

    monkeypatch.setattr(pipeline, "write_manifest", manifest_spy)
    monkeypatch.setattr(pipeline, "create_evidence_bundle", bundle_spy)
    monkeypatch.setattr(pipeline, "_logical_report_paths", logical_spy)
    out = tmp_path / "out"
    _run(
        tmp_path, {"m.c": "int a;\n"}, {"m.c": "int b;\n"},
        no_merge=True,
        report_html=str(out / "r.html"),
        bundle_path=str(out / "bundle.zip"),
    )
    expected = [str(out / "r_files")]
    assert seen["manifest"] == expected
    assert seen["bundle"] == expected
    assert seen["verify"] == expected
    assert isinstance(seen["environment"], dict)


# ---------------------------------------------------------------------------
# calibration status re-assessed once the deep unstripped extensions are known
# ---------------------------------------------------------------------------
def test_calibration_status_reassessed_after_deep_comment_extensions(tmp_path):
    body = "<template><div>{{ x }}</div></template>\n" + _JAVA
    report = _run(
        tmp_path, {"c.vue": body}, {"c.vue": body},
        exec_mode="deep", normalize=True, strip_comments=True,
    )
    meta = report["metadata"]
    assert meta["deep_comment_unstripped_extensions"] == [".vue"]
    # Default normalize profile otherwise matches; the kept .vue comments do not.
    assert meta["calibration_status"] == "unvalidated-profile"
    assert "strip_comments" in meta["calibration_profile_mismatches"]


def test_calibration_status_stays_applicable_when_all_stripped(tmp_path):
    report = _run(
        tmp_path, {"A.java": _JAVA}, {"A.java": _JAVA},
        exec_mode="deep", normalize=True, strip_comments=True,
    )
    assert report["metadata"]["calibration_status"] == "applicable"


# ---------------------------------------------------------------------------
# #9 part 2: a selective report states what it left out of the unmatched lists
# ---------------------------------------------------------------------------
def test_filtered_run_discloses_omitted_unmatched_in_every_format(tmp_path):
    flt = tmp_path / "filter.json"
    flt.write_text(json.dumps(["main.c"]), encoding="utf-8")
    out = tmp_path / "out"
    report = _run(
        tmp_path,
        {"main.c": "int a;\n", "zzzzzz.c": "int b;\n"},
        {"main.c": "int a;\n", "qq.h": "int c;\n", "wwwwwwww.txt": "int d;\n"},
        filter_json=str(flt),
        report_md=str(out / "r.md"),
        report_html=str(out / "r.html"),
        no_merge=True,
    )
    assert report["unmatched_b"] == []
    assert report["summary"]["unmatched_b_count"] == 0
    assert report["summary"]["omitted_unmatched_a_count"] == 1
    assert report["summary"]["omitted_unmatched_b_count"] == 2
    note = "unmatched files not listed, 1 in A; 2 in B"
    md = (out / "r.md").read_text(encoding="utf-8")
    assert "| Unmatched files (listed) | 0 in A; 0 in B." in md and note in md
    index = (out / "r_files" / "index.html").read_text(encoding="utf-8")
    assert note in index


def test_unfiltered_run_has_no_selection_note(tmp_path):
    out = tmp_path / "out"
    report = _run(
        tmp_path, {"main.c": "int a;\n"}, {"main.c": "int a;\n", "qq.h": "x\n"},
        report_md=str(out / "r.md"),
    )
    assert report["summary"]["omitted_unmatched_b_count"] == 0
    md = (out / "r.md").read_text(encoding="utf-8")
    assert "| Unmatched files | 0 in A; 1 in B |" in md
    assert "not listed" not in md


def test_separate_uncompared_file_states_selection_omission(tmp_path):
    path = tmp_path / "u.txt"
    status = AnalysisStatus(filter_omitted_unmatched_a=0, filter_omitted_unmatched_b=3)
    pipeline._write_uncompared_file(
        str(path), [], [], "A", "B", pipeline._selection_omitted_note(status)
    )
    text = path.read_text(encoding="utf-8")
    assert "# Selective report (--filter-json): unmatched files not listed, 0 in A; 3 in B" in text


# ---------------------------------------------------------------------------
# #62: every worker pool exits when its parent dies
# ---------------------------------------------------------------------------
def test_pipeline_and_deep_pools_share_parent_watch_initializer(tmp_path, monkeypatch):
    assert pipeline._exit_when_parent_dies is deep_compare.exit_when_parent_dies
    deep_compare.exit_when_parent_dies()  # no parent in the main process: no-op
    captured: dict[str, object] = {}
    real = deep_compare.ProcessPoolExecutor

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(deep_compare, "ProcessPoolExecutor", spy)
    _tree(tmp_path / "a", {"A.java": _JAVA})
    _tree(tmp_path / "b", {"A.java": _JAVA})
    deep_compare.run_deep_compare(
        str(tmp_path / "a"), str(tmp_path / "b"), ["A.java"], ["A.java"], workers=1
    )
    assert captured["initializer"] is deep_compare.exit_when_parent_dies


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION (WinNT.h) and STILL_ACTIVE (WinBase.h)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


_PARENT_SCRIPT = textwrap.dedent(
    """
    import multiprocessing, os, sys
    from concurrent.futures import ProcessPoolExecutor
    from diffinite.deep_compare import exit_when_parent_dies

    if __name__ == "__main__":
        ctx = multiprocessing.get_context("spawn")
        pool = ProcessPoolExecutor(1, mp_context=ctx, initializer=exit_when_parent_dies)
        pid = pool.submit(os.getpid).result()
        print(pid, flush=True)
        os._exit(0)  # die without shutting the pool down, as when killed
    """
)


def test_worker_exits_after_parent_is_gone(tmp_path):
    script = tmp_path / "parent.py"
    script.write_text(_PARENT_SCRIPT, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=120,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    worker_pid = int(proc.stdout.strip().splitlines()[-1])
    deadline = time.monotonic() + 30
    while _pid_alive(worker_pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if _pid_alive(worker_pid):  # pragma: no cover - only on failure
        pytest.fail(f"pool worker {worker_pid} outlived its parent")
