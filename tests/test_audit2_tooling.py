"""Regression tests for the 2026-11-10 audit, release-tooling group.

Findings #8, #42, #43, #44, #75, #76, #77, #78, #79, #80, #81. Workflow checks are
static (the workflows only run on GitHub); the shell, Python and harness logic is
executed where it can run offline.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation import error_rate, holdout

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
CI = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
BUNDLE_SCRIPT = (ROOT / "vscode-extension" / "scripts" / "build_bundle.ps1").read_text(
    encoding="utf-8"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def release_jobs() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(RELEASE)["jobs"]


@pytest.fixture(scope="module")
def dl():
    return _load("_audit2_download_examples", ROOT / "example" / "download_examples.py")


@pytest.fixture(scope="module")
def bench():
    return _load("_audit2_run_benchmarks", ROOT / "example" / "benchmark" / "run_benchmarks.py")


@pytest.fixture(scope="module")
def doctor():
    return _load(
        "_audit2_vsix_doctor", ROOT / ".claude" / "skills" / "vsce-debug" / "scripts" / "vsix_doctor.py"
    )


def _step(jobs: dict, job: str, name: str) -> dict:
    for step in jobs[job]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"step not found: {job} / {name}")


# ---------------------------------------------------------------- #8 GH_REPO
def test_gh_release_has_a_repository_without_a_checkout(release_jobs):
    yaml = pytest.importorskip("yaml")
    workflow_env = yaml.safe_load(RELEASE)["env"]
    assert workflow_env["GH_REPO"] == "${{ github.repository }}"
    for job in ("upload-vsix-release", "publish-github-release"):
        steps = release_jobs[job]["steps"]
        assert any("gh release" in str(s.get("run", "")) for s in steps)
        assert not any("actions/checkout" in str(s.get("uses", "")) for s in steps)


# ---------------------------------------------------------------- #75 peel annotated tags
_PEEL = re.compile(
    r"(?s)(          # github\.sha is the tagged commit\..*?"
    r"Release tag moved after this workflow was triggered\.\"\n\s*exit 1\n\s*fi\n)"
)


def _run_tag_guard(snippet: str, refs: dict[str, str], source_sha: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    cases = "\n".join(f'    *"{path}"*) echo "{out}" ;;' for path, out in refs.items())
    script = (
        "set -euo pipefail\n"
        "gh() {\n  case \"$*\" in\n" + cases + "\n    *) echo unexpected >&2; return 1 ;;\n  esac\n}\n"
        + snippet
        + "echo GUARD-OK\n"
    )
    env = {"GITHUB_REPOSITORY": "o/r", "RELEASE_TAG": "v1.0.0", "SOURCE_REF_SHA": source_sha}
    return subprocess.run(
        [bash, "-c", script], capture_output=True, text=True, env={**env, "PATH": "/usr/bin:/bin"}
    )


@pytest.mark.parametrize("step_name", ["Create or reuse draft GitHub Release",
                                       "Publish verified draft GitHub Release"])
def test_tag_guard_peels_annotated_tags_and_still_rejects_a_moved_tag(release_jobs, step_name):
    job = "upload-vsix-release" if step_name.startswith("Create") else "publish-github-release"
    run = _step(release_jobs, job, step_name)["run"]
    match = _PEEL.search("\n".join("          " + line for line in run.splitlines()) + "\n")
    assert match, "tag guard not found"
    snippet = match.group(1)

    lightweight = {"git/ref/tags/v1.0.0": "commit c0ffee"}
    assert "GUARD-OK" in _run_tag_guard(snippet, lightweight, "c0ffee").stdout

    annotated = {"git/ref/tags/v1.0.0": "tag 7a90b1", "git/tags/7a90b1": "commit c0ffee"}
    result = _run_tag_guard(snippet, annotated, "c0ffee")
    assert "GUARD-OK" in result.stdout, result.stdout + result.stderr

    moved = {"git/ref/tags/v1.0.0": "tag 7a90b1", "git/tags/7a90b1": "commit beef00"}
    result = _run_tag_guard(snippet, moved, "c0ffee")
    assert result.returncode != 0
    assert "Release tag moved" in result.stdout


# ---------------------------------------------------------------- #42 release gate
def test_release_gate_runs_the_ci_workflow_and_the_locked_bundle(release_jobs):
    yaml = pytest.importorskip("yaml")
    ci_on = yaml.safe_load(CI)[True]  # PyYAML reads the bare key `on` as True
    assert "workflow_call" in ci_on
    assert release_jobs["ci"]["uses"] == "./.github/workflows/ci.yml"
    for build_job in ("build-vsix", "build-python"):
        needs = release_jobs[build_job]["needs"]
        assert "ci" in needs and "test" in needs

    gate = "\n".join(str(s.get("run", "")) for s in release_jobs["test"]["steps"])
    assert release_jobs["test"]["runs-on"] == "windows-latest"
    assert "--require-hashes --no-deps -r vscode-extension/scripts/requirements-bundle.lock" in gate
    assert "pip install --no-deps -e ." in gate
    assert "python -m pytest" in gate
    assert "pip install -e \".[dev]\"" not in gate

    build_python = "\n".join(str(s.get("run", "")) for s in release_jobs["build-python"]["steps"])
    assert "pip install dist/*.whl" in build_python
    assert "-m diffinite --help" in build_python


# ---------------------------------------------------------------- #77 one Python version source
def test_python_version_has_one_source_with_a_pinned_hash():
    assert "PY_EMBED_URL" not in RELEASE
    assert "PY_VERSION" not in RELEASE
    assert "-pythonVersion" not in RELEASE
    assert "-pythonVersion" not in CI
    assert "$pinnedPythonHashes = @{" in BUNDLE_SCRIPT
    assert re.search(r'"3\.12\.9" = "[0-9A-F]{64}"', BUNDLE_SCRIPT)
    assert "No pinned SHA-256 for Python $pythonVersion" in BUNDLE_SCRIPT
    # The version check happens before the bundle directory is deleted.
    assert BUNDLE_SCRIPT.index("No pinned SHA-256") < BUNDLE_SCRIPT.index("Remove-Item $binPythonDir")
    # The recorded build metadata reads the version from the bundled interpreter.
    assert "platform.python_version()" in RELEASE


# ---------------------------------------------------------------- #76 idempotent, ordered publishing
def test_registry_publishing_is_rerunnable_and_pypi_runs_last(release_jobs):
    assert "publish-marketplaces" in release_jobs["publish-pypi"]["needs"]
    vsce = _step(release_jobs, "publish-marketplaces", "Publish to VSCode Marketplace")["run"]
    ovsx = _step(release_jobs, "publish-marketplaces", "Publish to Open VSX")["run"]
    for run, query in ((vsce, "vsce show"), (ovsx, "open-vsx.org/api/")):
        assert query in run
        assert "TargetPlatform" in run
        assert "Get-RemoteSha256" in run and "Get-FileHash" in run
        assert "with different bytes" in run
        assert "--skip-duplicate" not in run  # a duplicate is never accepted unverified
        # Failures are collected so every VSIX is attempted; the step fails once.
        loop = run[run.index("foreach ($vsix in $vsixFiles)"):run.rindex("if ($failures.Count -gt 0)")]
        assert loop.index("try {") < loop.index("publish") < loop.rindex("} catch {")
        assert "$failures += " in loop[loop.rindex("} catch {"):]
        assert "throw" not in loop[loop.rindex("} catch {"):]


# ---------------------------------------------------------------- #43 / #79 corpus digest
def _manual_digest(root: Path) -> str:
    h = hashlib.sha256()
    for rel in sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()):
        h.update(f"{rel}\0{hashlib.sha256((root / rel).read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def test_tree_digest_orders_by_posix_path_string_on_every_os(tmp_path, dl):
    # Upper-case 'S' (0x53) sorts before 'c' (0x63) as a string; Windows Path
    # ordering is case-insensitive and put 'c/000.c' first.
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "000.c").write_bytes(b"int x;\n")
    (tmp_path / "SOCO14-c.qrel").write_bytes(b"000.c 001.c\n")
    expected = _manual_digest(tmp_path)
    assert error_rate.tree_sha256(tmp_path) == expected
    assert dl._tree_sha256(tmp_path) == expected


def test_pinned_corpus_is_checked_by_content_not_file_count(tmp_path, dl):
    (tmp_path / "case-01").mkdir()
    f = tmp_path / "case-01" / "a.java"
    f.write_bytes(b"class A {}\n")
    pin = dl._tree_sha256(tmp_path)
    assert dl._pinned_layout_ok(tmp_path, 1, pin)
    f.write_bytes(b"class B {}\n")  # same file count, different bytes
    assert not dl._pinned_layout_ok(tmp_path, 1, pin)


def test_calibration_corpora_pin_their_extracted_tree(dl):
    for name in ("plagiarism", "soco14"):
        assert re.fullmatch(r"[0-9a-f]{64}", dl.DATASETS[name]["expected_tree_sha256"])
    assert error_rate.pinned_tree_sha256("plagiarism") == dl.DATASETS["plagiarism"][
        "expected_tree_sha256"
    ]


def test_error_rate_refuses_an_unpinned_corpus_and_records_the_digest(tmp_path, monkeypatch):
    (tmp_path / "x.java").write_bytes(b"class X {}\n")
    monkeypatch.setattr(error_rate, "pinned_tree_sha256", lambda dataset: "0" * 64)
    with pytest.raises(SystemExit, match="not the pinned plagiarism corpus"):
        error_rate.verify_corpus(tmp_path, "plagiarism")

    digest = error_rate.tree_sha256(tmp_path)
    monkeypatch.setattr(error_rate, "pinned_tree_sha256", lambda dataset: digest)
    assert error_rate.verify_corpus(tmp_path, "plagiarism") == digest

    score = error_rate.PairScore(case="case-01", mode="normalize", label="neg", level=None,
                                 jaccard=0.1, tokens_min=100, tokens_max=100)
    md = tmp_path / "error_rate.md"
    error_rate.write_md_summary([score, error_rate.PairScore(
        case="case-01", mode="raw", label="neg", level=None, jaccard=0.1,
        tokens_min=100, tokens_max=100)], md, digest)
    assert digest in md.read_text(encoding="utf-8")


# ---------------------------------------------------------------- #80 engine-identical threshold
def test_harness_threshold_matches_the_engine_at_exact_fractions():
    jaccard = 57 / 100
    assert jaccard * 100 < 57  # the old comparison missed this pair
    assert error_rate.is_flagged(jaccard, 57)
    neg = error_rate.PairScore(case="c", mode="normalize", label="neg", level=None,
                               jaccard=jaccard, tokens_min=50, tokens_max=50)
    pos = error_rate.PairScore(case="c", mode="normalize", label="pos", level=1,
                               jaccard=jaccard, tokens_min=50, tokens_max=50)
    assert error_rate.fp_rate([neg], "normalize", 57) == (1, 1)
    assert error_rate.recall([pos], "normalize", 57) == (1, 1)

    pair = holdout.Pair(case="c", label="neg", level=None, jaccard=jaccard, a_in_b=0.0, b_in_a=0.0)
    assert holdout.fixed_threshold_by_case([pair], 57)[0]["fp"] == 1
    assert holdout._select_threshold([pair], 0.0) == 58


def test_no_harness_comparison_scales_jaccard_by_100():
    for path in (ROOT / "tests" / "validation" / "error_rate.py",
                 ROOT / "tests" / "validation" / "holdout.py"):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"\w\.jaccard \* 100 >=", src), path
        assert "/ union * 100" not in src


# ---------------------------------------------------------------- #78 --check
def _case(**over) -> dict:
    base = {"title": "t", "command": "c", "input_digest": "d", "pairs": [], "deep": [],
            "unmatched_a": 0, "unmatched_b": 0, "analysis_state": "complete",
            "threshold_pct": 93.0, "threshold_provenance": "normalize-default",
            "comment_mode": "stripped"}
    base.update(over)
    return base


def test_check_compares_published_threshold_and_comment_fields(bench):
    committed = {"cases": {"a": _case()}, "cross_language": {}}
    for field, value in (("threshold_pct", 78.0), ("threshold_provenance", "user"),
                         ("comment_mode", "included")):
        drift, checked, _ = bench.compare_results(
            committed, {"cases": {"a": _case(**{field: value})}, "cross_language": {}})
        assert drift == [f"cases/a: {field} differs (result changed)"]
        assert checked == []


def test_check_reports_missing_and_skipped_cases(bench):
    committed = {"cases": {"a": _case(), "gone": _case()}, "cross_language": {}}
    now = {"cases": {"a": {"title": "t", "command": "c", "skipped": "dataset not downloaded"},
                     "new": _case()}, "cross_language": {}}
    drift, checked, unverified = bench.compare_results(committed, now)
    assert unverified == ["cases/a"]
    assert checked == []
    assert "cases/gone: in results.json but not produced by this run" in drift
    assert "cases/new: not in results.json (regenerate it)" in drift


def test_check_exits_nonzero_when_a_committed_case_was_not_reproduced(bench, monkeypatch, tmp_path,
                                                                       capsys):
    (tmp_path / "results.json").write_text(
        json.dumps({"cases": {"a": _case()}, "cross_language": {}}), encoding="utf-8")
    monkeypatch.setattr(bench, "BENCH", tmp_path)
    monkeypatch.setattr(bench, "collect", lambda write_reports: {
        "cases": {"a": {"title": "t", "command": "c", "skipped": "dataset not downloaded"}},
        "cross_language": {}})
    monkeypatch.setattr(sys, "argv", ["run_benchmarks.py", "--check"])
    assert bench.main() == 1
    assert "0 checked, 1 not verified" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["run_benchmarks.py", "--check", "--allow-skips"])
    assert bench.main() == 0

    monkeypatch.setattr(bench, "collect", lambda write_reports: {
        "cases": {"a": _case()}, "cross_language": {}})
    monkeypatch.setattr(sys, "argv", ["run_benchmarks.py", "--check"])
    assert bench.main() == 0
    assert "1 checked, 0 not verified, 0 drifted" in capsys.readouterr().out


# ---------------------------------------------------------------- #44 cp1252 under -I
def test_cp1252_check_really_encodes_as_cp1252_in_isolated_mode(doctor):
    # U+2192 (arrow) has no cp1252 mapping; U+00E9 does.
    bad = subprocess.run([sys.executable, "-I", "-c", doctor.CP1252_PRELUDE + "print('→')"],
                         capture_output=True)
    assert bad.returncode != 0
    assert b"UnicodeEncodeError" in bad.stderr
    good = subprocess.run([sys.executable, "-I", "-c", doctor.CP1252_PRELUDE + "print('café')"],
                          capture_output=True)
    assert good.returncode == 0
    assert good.stdout.startswith(b"caf\xe9")


def test_cp1252_help_check_runs_the_module_help(doctor):
    result = doctor.run_help_under_cp1252(Path(sys.executable))
    if result.returncode != 0 and b"No module named" in result.stderr:
        pytest.skip("diffinite is not importable by an isolated interpreter here")
    assert result.returncode == 0, result.stderr
    assert b"usage:" in result.stdout.lower()


# ---------------------------------------------------------------- #81 host test
def test_host_phase2_asserts_the_selected_pairs_came_back():
    src = (ROOT / "vscode-extension" / "test" / "host" / "index.js").read_text(encoding="utf-8")
    step = src[src.index("phase 2 selective analysis"):src.index("showResults(")]
    assert "phase2.results.length > 0" in step
    assert "assert.deepEqual" in step and "selected()" in step
    assert step.index("assert.deepEqual") < step.index("every((r)")
