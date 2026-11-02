"""Release lock and bundled license inventory consistency checks."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "vscode-extension" / "scripts" / "requirements-bundle.lock"
LICENSES = ROOT / "vscode-extension" / "DEPENDENCY_LICENSES.md"
THIRD_PARTY_LICENSES = ROOT / "vscode-extension" / "third-party-licenses"
RUNTIME_LOCK = ROOT / "vscode-extension" / "scripts" / "requirements-bundle.lock"


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked_packages() -> set[str]:
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)==", re.MULTILINE)
    return {_canonical(name) for name in pattern.findall(LOCK.read_text(encoding="utf-8"))}


def _locked_versions() -> dict[str, str]:
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)", re.MULTILINE)
    return {
        _canonical(name): version
        for name, version in pattern.findall(LOCK.read_text(encoding="utf-8"))
    }


def test_runtime_requirements_are_present_in_release_lock():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    direct = {
        _canonical(re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0])
        for requirement in project["dependencies"]
    }
    assert direct <= _locked_packages()


def test_license_inventory_matches_locked_runtime_packages():
    row_pattern = re.compile(r"^\|\s*([^|]+?)\s*\|\s*[^|]+\|", re.MULTILINE)
    rows = {
        canonical
        for name in row_pattern.findall(LICENSES.read_text(encoding="utf-8"))
        if (canonical := _canonical(name.strip())) not in {"", "-", "name"}
    }
    assert rows == _locked_packages() | {"diffinite"}


def test_license_inventory_versions_match_release_lock():
    row_pattern = re.compile(
        r"^\|\s*([A-Za-z0-9_.-]+)\s*\|\s*([^|\s]+)\s*\|",
        re.MULTILINE,
    )
    rows = {
        _canonical(name): version
        for name, version in row_pattern.findall(LICENSES.read_text(encoding="utf-8"))
        if name.lower() != "name" and set(name) != {"-"}
    }
    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    expected = _locked_versions() | {"diffinite": project_version}
    assert rows == expected


def test_license_inventory_has_no_duplicate_or_unknown_primary_rows():
    row_pattern = re.compile(
        r"^\|\s*([A-Za-z0-9_.-]+)\s*\|\s*([^|\s]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
        re.MULTILINE,
    )
    rows = [
        row
        for row in row_pattern.findall(LICENSES.read_text(encoding="utf-8"))
        if row[0] != "Name" and set(row[0]) != {"-"}
    ]
    canonical_names = [_canonical(row[0]) for row in rows]
    assert len(canonical_names) == len(set(canonical_names))
    expected_names = {
        _canonical(name)
        for name in re.findall(
            r"(?m)^([A-Za-z0-9_.-]+)==",
            RUNTIME_LOCK.read_text(encoding="utf-8"),
        )
    } | {"diffinite"}
    assert set(canonical_names) == expected_names
    assert all(row[3].strip() != "UNKNOWN" for row in rows)


def test_referenced_license_fallbacks_are_present_and_substantive():
    references = re.findall(
        r"See (third-party-licenses/[A-Za-z0-9_.-]+\.txt)",
        LICENSES.read_text(encoding="utf-8"),
    )
    assert references
    for reference in references:
        path = ROOT / "vscode-extension" / reference
        content = path.read_text(encoding="utf-8")
        assert path.is_relative_to(THIRD_PARTY_LICENSES)
        assert content.strip()
        assert "license" in content.lower()
        assert "UNKNOWN" not in content
