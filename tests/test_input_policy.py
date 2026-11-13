"""Collection policy: sensitive-file preset, --include, disclosure of every
exclusion, and --bundle-sources none.

The feature gate for the sensitive-file preset is measured here: a sentinel
string planted in ``.env`` and ``id_rsa`` must appear in no output artifact
(reports, sidecars, manifest, bundle) under the default policy.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from diffinite import cli
from diffinite.collector import (
    CollectionPolicy,
    collect_files,
    sensitive_preset_rules,
    sensitive_rule,
)
from diffinite.pipeline import run_pipeline

SENTINEL = "SENTINEL_SECRET_7f3a"


@pytest.mark.parametrize(
    ("path", "rule"),
    [
        (".env", ".env"),
        ("app/.env.local", ".env.*"),
        ("app/.ENV.Production", ".env.*"),
        ("deploy/prod.env", "*.env"),
        ("certs/server.KEY", "*.key"),
        ("keys/id_rsa", "id_rsa"),
        ("keys/id_ed25519_sk", "id_ed25519_sk"),
        # Source files named after key types are not keys.
        ("crypto/id_rsa_util.py", None),
        ("ssh/id_ed25519_test.go", None),
        ("home/.ssh/config", ".ssh/**"),
        ("h/.aws/credentials", ".aws/**"),
        ("h/.config/gcloud/application_default_credentials.json", ".config/gcloud/**"),
        (".docker/config.json", ".docker/config.json"),
        ("infra/prod.tfvars", "*.tfvars"),
        (".npmrc", ".npmrc"),
        ("credentials.json", "credentials.json"),
        # Templates and public keys are not secrets.
        (".env.example", None),
        (".env.sample", None),
        ("keys/id_rsa.pub", None),
        # Ordinary source files.
        ("src/key.py", None),
        ("src/env.py", None),
        ("src/environment/settings.py", None),
        ("docker/config.json", None),
    ],
)
def test_sensitive_rule(path, rule):
    assert sensitive_rule(path) == rule


def test_preset_rules_are_listed_for_the_manifest():
    rules = sensitive_preset_rules()
    assert ".env" in rules and ".ssh/**" in rules and "except *.pub" in rules


def _tree(root: Path, secret: str = SENTINEL) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    (root / ".env").write_text(f"API_KEY={secret}\n", encoding="utf-8")
    (root / ".env.example").write_text("API_KEY=\n", encoding="utf-8")
    (root / ".ssh").mkdir()
    (root / ".ssh" / "id_rsa").write_text(f"-----BEGIN {secret}-----\n", encoding="utf-8")
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "i.js").write_text("x\n", encoding="utf-8")


def test_collect_files_records_every_exclusion(tmp_path):
    _tree(tmp_path)
    excluded: list[dict[str, str]] = []
    policy = CollectionPolicy(ignore_patterns=("node_modules/",), sensitive_files="exclude")
    files = collect_files(str(tmp_path), policy=policy, excluded_list=excluded)
    assert files == [".env.example", "README.md", "src/a.py"]
    assert excluded == [
        {"path": ".env", "kind": "file", "source": "sensitive-preset", "rule": ".env"},
        {"path": ".ssh/id_rsa", "kind": "file", "source": "sensitive-preset", "rule": ".ssh/**"},
        {
            "path": "node_modules",
            "kind": "directory",
            "source": "ignore-file",
            "rule": "node_modules/",
        },
    ]


def test_include_filter_applies_before_the_sensitive_preset(tmp_path):
    _tree(tmp_path)
    excluded: list[dict[str, str]] = []
    policy = CollectionPolicy(include_patterns=("*.py",), sensitive_files="error")
    files = collect_files(str(tmp_path), policy=policy, excluded_list=excluded)
    assert files == ["src/a.py"]
    # A file the include filter already leaves out is never reported as sensitive.
    assert {item["source"] for item in excluded} == {"include-filter"}


def test_collect_files_without_policy_keeps_the_old_behaviour(tmp_path):
    _tree(tmp_path)
    assert ".env" in collect_files(str(tmp_path), ["node_modules"])


def _all_output_bytes(out: Path) -> bytes:
    blob = b""
    for path in out.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    blob += name.encode() + archive.read(name)
        else:
            blob += path.read_bytes()
    return blob


def _run(tmp_path: Path, out: Path, **kwargs) -> None:
    run_pipeline(
        str(tmp_path / "a"),
        str(tmp_path / "b"),
        report_md=str(out / "r.md"),
        report_json=str(out / "r.json"),
        report_html=str(out / "r.html"),
        exec_mode="simple",
        workers=1,
        **kwargs,
    )


def test_default_policy_keeps_secrets_out_of_every_artifact(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    out = tmp_path / "out"
    _run(tmp_path, out, bundle_path=str(out / "bundle.zip"))
    assert SENTINEL.encode() not in _all_output_bytes(out)

    report = json.loads((out / "r.json").read_text(encoding="utf-8"))
    exclusion = report["analysis_status"]["exclusion"]
    assert exclusion["excluded_count"] == 4
    assert {(e["side"], e["path"]) for e in exclusion["excluded"]} == {
        ("A", ".env"),
        ("A", ".ssh/id_rsa"),
        ("B", ".env"),
        ("B", ".ssh/id_rsa"),
    }
    assert report["analysis_status"]["state"] == "complete"
    assert report["metadata"]["sensitive_files"] == "exclude"
    assert report["metadata"]["sensitive_preset_version"] == "1"

    manifest = json.loads((out / "manifest.sha256.json").read_text(encoding="utf-8"))
    hashed = {entry["path"] for entry in manifest["source_a"]["files"]}
    assert ".env" not in hashed and ".env.example" in hashed

    md = (out / "r.md").read_text(encoding="utf-8")
    assert "| Inputs excluded by policy | 4 (listed under Excluded Inputs) |" in md
    assert "## Excluded Inputs" in md
    assert "| A: .env | sensitive-file preset rule .env |" in md
    html = (out / "r.html").read_text(encoding="utf-8")
    assert "<h2>Excluded Inputs</h2>" in html and "sensitive-file preset rule .ssh/**" in html


def test_include_mode_compares_sensitive_files(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    out = tmp_path / "out"
    _run(tmp_path, out, sensitive_files="include")
    report = json.loads((out / "r.json").read_text(encoding="utf-8"))
    assert ".env" in {r["file_a"] for r in report["results"]}
    assert report["analysis_status"]["exclusion"]["excluded_count"] == 0
    assert report["metadata"]["sensitive_preset_rules"] == []


def test_error_mode_stops_before_writing_anything(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match=r"Sensitive files found \(4\); nothing was written"):
        _run(tmp_path, out, sensitive_files="error")
    assert not out.exists() or not any(out.iterdir())


def test_include_filter_limits_hashing_and_bundle(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    out = tmp_path / "out"
    _run(tmp_path, out, include_patterns=["src/**"], bundle_path=str(out / "bundle.zip"))
    manifest = json.loads((out / "manifest.sha256.json").read_text(encoding="utf-8"))
    assert [entry["path"] for entry in manifest["source_a"]["files"]] == ["src/a.py"]
    with zipfile.ZipFile(out / "bundle.zip") as archive:
        sources = sorted(n for n in archive.namelist() if n.startswith("source_"))
    assert sources == ["source_a/src/a.py", "source_b/src/a.py"]
    report = json.loads((out / "r.json").read_text(encoding="utf-8"))
    assert report["metadata"]["include_patterns"] == ["src/**"]
    assert "Include filter | src/\\*\\*" in (out / "r.md").read_text(encoding="utf-8")


def test_bundle_without_sources_keeps_the_manifest(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    out = tmp_path / "out"
    _run(tmp_path, out, bundle_path=str(out / "bundle.zip"), bundle_sources="none")
    with zipfile.ZipFile(out / "bundle.zip") as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.sha256.json"))
    assert not [n for n in names if n.startswith("source_")]
    assert {e["path"] for e in manifest["source_a"]["files"]} == {
        ".env.example",
        "README.md",
        "node_modules/x/i.js",
        "src/a.py",
    }
    md = (out / "r.md").read_text(encoding="utf-8")
    assert "source files omitted; the manifest lists their SHA-256 digests" in md


def test_separate_listing_moves_the_list_out_of_the_reports(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    out = tmp_path / "out"
    _run(tmp_path, out, uncompared_mode="separate")
    md = (out / "r.md").read_text(encoding="utf-8")
    assert "Inputs excluded by policy | 4 (listed in the uncompared-files list)" in md
    listing = (out / "r_uncompared.txt").read_text(encoding="utf-8")
    assert "## Excluded by policy (4 entries)" in listing
    assert "  B: .ssh/id_rsa, sensitive-file preset rule .ssh/**" in listing


def test_invalid_policy_values_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="sensitive_files"):
        run_pipeline(str(tmp_path), str(tmp_path), sensitive_files="maybe")
    with pytest.raises(ValueError, match="bundle_sources"):
        run_pipeline(str(tmp_path), str(tmp_path), bundle_sources="some")


def test_cli_flags(monkeypatch, tmp_path):
    seen: list[dict] = []
    monkeypatch.setattr(cli, "run_pipeline", lambda **kwargs: seen.append(kwargs))
    a, b = str(tmp_path), str(tmp_path)
    cli.main([a, b])
    cli.main(
        [
            a,
            b,
            "--sensitive-files",
            "error",
            "--include",
            "*.java",
            "--include=src/**",
            "--bundle-sources",
            "none",
        ]
    )
    first, second = seen
    assert (first["sensitive_files"], first["include_patterns"], first["bundle_sources"]) == (
        "exclude",
        None,
        "full",
    )
    assert second["sensitive_files"] == "error"
    assert second["include_patterns"] == ["*.java", "src/**"]
    assert second["bundle_sources"] == "none"


def test_long_exclusion_list_is_one_table_row_per_input(tmp_path):
    """A long list must break across PDF pages, so it is never one table cell."""
    for side in ("a", "b"):
        (tmp_path / side / "logs").mkdir(parents=True)
        (tmp_path / side / "main.py").write_text("x = 1\n", encoding="utf-8")
        for i in range(60):
            (tmp_path / side / "logs" / f"run_{i}.log").write_text("l\n", encoding="utf-8")
    ignore = tmp_path / "ignore"
    ignore.write_text("*.log\n", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, out, ignore_file=str(ignore))
    html = (out / "r.html").read_text(encoding="utf-8")
    assert html.count("ignore file rule *.log") == 120
    assert "120 (listed under Excluded Inputs)" in html


def test_control_characters_in_excluded_names_are_visible(tmp_path):
    from diffinite.models import AnalysisStatus
    from diffinite.notices import excluded_input_rows, exclusion_label

    status = AnalysisStatus()
    item = {
        "side": "A",
        "path": "x\nB: y.env",
        "kind": "file",
        "source": "sensitive-preset",
        "rule": "*.env",
    }
    status.policy_excluded = [item]
    assert excluded_input_rows(status) == [
        ("A: x\u240aB: y.env", "sensitive-file preset rule *.env")
    ]
    assert "\n" not in exclusion_label(item)


def test_markdown_cells_escape_strikethrough():
    from diffinite.pipeline import _md_cell_text

    assert _md_cell_text("~~old~~.env") == "\\~\\~old\\~\\~.env"


def test_unencodable_excluded_name_is_disclosed_escaped(tmp_path, monkeypatch):
    from diffinite import pipeline

    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    original = pipeline.collect_files

    def collect(directory, ignore_patterns=None, unreadable_list=None, **kwargs):
        files = original(directory, ignore_patterns, unreadable_list, **kwargs)
        excluded = kwargs.get("excluded_list")
        if excluded is not None and directory.endswith("a"):
            excluded.append(
                {"path": "bad\ud800.log", "kind": "file", "source": "ignore-file", "rule": "*.log"}
            )
        return files

    monkeypatch.setattr(pipeline, "collect_files", collect)
    out = tmp_path / "out"
    _run(tmp_path, out)
    report = json.loads((out / "r.json").read_text(encoding="utf-8"))
    paths = {e["path"] for e in report["analysis_status"]["exclusion"]["excluded"]}
    assert "bad\\ud800.log" in paths


def test_change_in_the_excluded_set_during_analysis_is_detected(tmp_path):
    from diffinite.pipeline import _verify_source_state

    _tree(tmp_path / "a")
    policy = CollectionPolicy(sensitive_files="exclude")
    excluded: list[dict[str, str]] = []
    errors: list[str] = []
    files = collect_files(
        str(tmp_path / "a"), unreadable_list=errors, policy=policy, excluded_list=excluded
    )
    expected = [{"side": "A", **item} for item in excluded]
    from diffinite.evidence import compute_file_hashes

    hashes = compute_file_hashes(str(tmp_path / "a"), files)
    assert _verify_source_state("A", str(tmp_path / "a"), files, hashes, [], policy, expected) == []
    (tmp_path / "a" / ".env").unlink()
    (tmp_path / "a" / "new.pem").write_text("k\n", encoding="utf-8")
    changes = _verify_source_state("A", str(tmp_path / "a"), files, hashes, [], policy, expected)
    assert changes == ["A:newly-excluded:new.pem", "A:no-longer-excluded:.env"]


def test_filter_naming_an_excluded_file_says_why(tmp_path):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    selection = tmp_path / "sel.json"
    selection.write_text(json.dumps([".env"]), encoding="utf-8")
    with pytest.raises(
        RuntimeError,
        match=r"collection policy excluded.*\.env \(sensitive-file preset rule \.env\)",
    ):
        _run(tmp_path, tmp_path / "out", filter_json=str(selection))


def test_error_mode_message_is_short_and_lists_files_in_the_log(tmp_path, caplog):
    _tree(tmp_path / "a")
    _tree(tmp_path / "b")
    with pytest.raises(RuntimeError) as info:
        _run(tmp_path, tmp_path / "out", sensitive_files="error")
    message = str(info.value)
    assert message.startswith("Sensitive files found (4); nothing was written.")
    assert ".ssh" not in message
    assert "Sensitive file A:.ssh/id_rsa (rule .ssh/**)" in caplog.text
