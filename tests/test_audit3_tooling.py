"""Regression tests for the docs-tooling handoffs of the third audit round.

- run_benchmarks ``--check``: a case skipped on both sides is "not verified".
- README documents ``--check`` / ``--allow-skips`` and the ignore rules the
  collector actually implements (checked against ``should_ignore``).
- release.yml says that only "Re-run failed jobs" completes a partial publish.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from diffinite.collector import should_ignore

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bench():
    path = ROOT / "example" / "benchmark" / "run_benchmarks.py"
    spec = importlib.util.spec_from_file_location("_audit3_run_benchmarks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skipped() -> dict:
    return {"title": "t", "command": "c", "skipped": "dataset not downloaded"}


# ------------------------------------------------ run_benchmarks: skipped on both sides
def test_case_skipped_on_both_sides_is_not_verified(bench):
    committed = {"cases": {"a": _skipped()}, "cross_language": {"x": _skipped()}}
    now = {"cases": {"a": _skipped()}, "cross_language": {"x": _skipped()}}
    drift, checked, unverified = bench.compare_results(committed, now)
    assert drift == []
    assert checked == []
    assert unverified == ["cases/a", "cross_language/x"]


def test_every_key_is_accounted_for(bench):
    committed = {"cases": {"both": _skipped(), "ok": {"title": "t"}, "old_skip": _skipped(),
                           "gone": {"title": "t"}}, "cross_language": {}}
    now = {"cases": {"both": _skipped(), "ok": {"title": "t"}, "old_skip": {"title": "t"},
                     "new": {"title": "t"}}, "cross_language": {}}
    drift, checked, unverified = bench.compare_results(committed, now)
    names = {f"cases/{k}" for k in committed["cases"].keys() | now["cases"].keys()}
    accounted = set(checked) | set(unverified) | {d.split(":", 1)[0] for d in drift}
    assert accounted == names
    assert unverified == ["cases/both"]
    assert checked == ["cases/ok"]


def test_check_exits_1_when_everything_was_skipped_on_both_sides(bench, monkeypatch, tmp_path,
                                                                  capsys):
    (tmp_path / "results.json").write_text(
        json.dumps({"cases": {"a": _skipped()}, "cross_language": {}}), encoding="utf-8")
    monkeypatch.setattr(bench, "BENCH", tmp_path)
    monkeypatch.setattr(bench, "collect", lambda write_reports: {
        "cases": {"a": _skipped()}, "cross_language": {}})
    monkeypatch.setattr(sys, "argv", ["run_benchmarks.py", "--check"])
    assert bench.main() == 1
    out = capsys.readouterr().out
    assert "0 checked, 1 not verified, 0 drifted" in out
    assert "cases/a" in out
    monkeypatch.setattr(sys, "argv", ["run_benchmarks.py", "--check", "--allow-skips"])
    assert bench.main() == 0


# ------------------------------------------------ README: --check / --allow-skips
def test_readme_documents_check_exit_code_and_allow_skips():
    section = README.split("run_benchmarks.py --check", 1)[1][:1500]
    assert "--allow-skips" in section
    assert "exits 1" in section
    assert "not verified" in section


# ------------------------------------------------ README: ignore rules match the code
@pytest.mark.parametrize(
    ("path", "pattern", "is_dir", "expected"),
    [
        ("src/a.py", "src/*.py", False, True),
        ("src/a/b.py", "src/*.py", False, False),  # * never crosses /
        ("THUMBS.DB", "Thumbs.db", False, False),  # case-sensitive on every OS
        ("Thumbs.db", "Thumbs.db", False, True),
        ("a/b/node_modules/x.js", "node_modules", False, True),  # bare name, any depth
        ("a/build", "build/", False, False),  # trailing / = directories only
        ("a/build", "build/", True, True),
        ("a/build", "/build", True, False),  # leading / anchors to the root
        ("build", "/build", True, True),
        ("x.gen.cs", "**/*.gen.cs", False, True),  # **/ includes the root level
        ("abc", "abc/**", True, False),  # trailing /** = inside only
        ("abc/d.txt", "abc/**", False, True),
        ("foo", "!foo", False, False),  # ! negation unsupported: literal name
        ("!foo", "!foo", False, True),
    ],
)
def test_readme_ignore_rules_match_should_ignore(path, pattern, is_dir, expected):
    assert should_ignore(path, [pattern], is_dir=is_dir) is expected


def test_readme_states_ignore_limits():
    section = README.split("#### Ignore patterns", 1)[1].split("####", 1)[0]
    assert "case-sensitive on every OS" in section
    assert "`!` negation" in section
    assert "`\\` escapes" in section
    for example in ("src/*.py", "build/", "/build", "**/", "/**"):
        assert example in section


# ------------------------------------------------ README: disclosures that exist in the code
def test_readme_documents_completeness_disclosure_and_pair_labels():
    assert "### Completeness Disclosure" in README
    for phrase in (
        "skipped (binary or not decodable as text)",
        "below the k-gram size",
        "excluded",
        "Not compared by difflib (<reason>); SHA-256 identical",
        "Requested = processed + failed + excluded",
    ):
        assert phrase in README, phrase


def test_readme_environment_keys_are_the_contract_keys():
    section = README.split("#### Integrity manifest: environment", 1)[1].split("Report checksum", 1)[0]
    keys = set(re.findall(r"^\| `([a-z_]+)` \|", section, flags=re.M))
    assert keys == {"python_version", "pygments_version", "unicodedata_version",
                    "lang_aware_tiers", "lang_aware_fallback_files"}
    source = "".join(
        (ROOT / "src" / "diffinite" / name).read_text(encoding="utf-8")
        for name in ("pipeline.py", "deep_compare.py")
    )
    for key in keys:
        assert key in source, key


# ------------------------------------------------ release.yml: rerun guidance
def test_release_comments_name_rerun_failed_jobs_for_partial_publish():
    marketplace = RELEASE.split("publish-marketplaces:", 1)[0].rsplit("\n\n", 1)[1]
    assert 'Only "Re-run failed jobs"' in marketplace
    assert '"Re-run all jobs" rebuilds the VSIX' in marketplace
    assert RELEASE.count('"Re-run failed jobs"') >= 3
