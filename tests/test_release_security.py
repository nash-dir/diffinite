"""Static security contracts for the privileged release workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from packaging.version import Version


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
).read_text(encoding="utf-8")
CI_WORKFLOW = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
    encoding="utf-8"
)
BUNDLE_SCRIPT = (
    Path(__file__).resolve().parents[1] / "vscode-extension" / "scripts" / "build_bundle.ps1"
).read_text(encoding="utf-8")
LOCK_SCRIPT = (
    Path(__file__).resolve().parents[1] / "vscode-extension" / "scripts" / "update_lockfile.ps1"
).read_text(encoding="utf-8")
RUNTIME_LOCK = (
    Path(__file__).resolve().parents[1]
    / "vscode-extension"
    / "scripts"
    / "requirements-bundle.lock"
).read_text(encoding="utf-8")
BUILD_LOCK = (
    Path(__file__).resolve().parents[1] / "vscode-extension" / "scripts" / "requirements-build.lock"
).read_text(encoding="utf-8")
PACKAGE_JSON = json.loads(
    (Path(__file__).resolve().parents[1] / "vscode-extension" / "package.json").read_text(
        encoding="utf-8"
    )
)
PACKAGE_LOCK = json.loads(
    (Path(__file__).resolve().parents[1] / "vscode-extension" / "package-lock.json").read_text(
        encoding="utf-8"
    )
)


def _job(name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        WORKFLOW,
    )
    assert match, f"release job not found: {name}"
    return match.group("body")


def _step(job: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(?P<body>.*?)(?=^      - (?:name:|uses:)|\Z)",
        job,
    )
    assert match, f"release step not found: {name}"
    return match.group("body")


def _locked_version(lock_text: str, package: str) -> Version:
    match = re.search(rf"(?m)^{re.escape(package)}==([^ \\]+)", lock_text)
    assert match, f"locked package not found: {package}"
    return Version(match.group(1))


def test_release_is_tag_driven_and_manual_dispatch_cannot_publish():
    top = WORKFLOW.split("permissions:", maxsplit=1)[0]
    assert re.search(
        r'(?m)^on:\n  push:\n    tags:\n      - "v\*"\n  workflow_dispatch:$',
        top,
    )
    assert "release:" not in top
    assert "types: [published]" not in top
    assert "github.event.release" not in WORKFLOW

    for job_name in (
        "build-python",
        "upload-vsix-release",
        "publish-marketplaces",
        "publish-pypi",
        "publish-github-release",
    ):
        job_header = _job(job_name).split("steps:", maxsplit=1)[0]
        assert re.search(
            r"(?m)^    if: github\.event_name == 'push'$",
            job_header,
        )


def test_release_permissions_are_job_scoped():
    top = WORKFLOW.split("jobs:", maxsplit=1)[0]
    assert re.search(r"(?m)^permissions:\n  contents: read$", top)
    assert "id-token: write" not in top

    assert "contents: write" in _job("upload-vsix-release")
    assert "contents: write" in _job("publish-github-release")
    pypi = _job("publish-pypi")
    assert "contents: read" in pypi
    assert "id-token: write" in pypi


def test_every_external_action_is_pinned_to_an_immutable_commit():
    for workflow in (CI_WORKFLOW, WORKFLOW):
        action_refs = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", workflow)
        assert action_refs
        assert all(re.search(r"@[0-9a-f]{40}$", ref) for ref in action_refs), action_refs


def test_ci_token_is_read_only_and_checkout_never_persists_credentials():
    top = CI_WORKFLOW.split("jobs:", maxsplit=1)[0]
    assert re.search(r"(?m)^permissions:\n  contents: read$", top)
    assert CI_WORKFLOW.count("persist-credentials: false") == CI_WORKFLOW.count("actions/checkout@")


def test_all_node_tooling_uses_the_lock_compatible_runtime():
    assert 'node-version: "20"' not in CI_WORKFLOW
    assert 'node-version: "20"' not in WORKFLOW
    assert 'node-version: "22"' in CI_WORKFLOW
    assert WORKFLOW.count('node-version: "22"') == 2


def test_marketplace_tokens_are_exposed_only_to_publish_steps():
    vsce_job = _job("publish-marketplaces")
    job_prefix = vsce_job.split("steps:", maxsplit=1)[0]
    assert "OVSX_PAT" not in job_prefix

    marketplace = _step(vsce_job, "Publish to VSCode Marketplace")
    assert "VSCE_PAT: ${{ secrets.VSCE_PAT }}" in marketplace
    assert "$env:VSCE_PAT" in marketplace
    assert "-p ${{ secrets.VSCE_PAT }}" not in marketplace
    assert "-p $env:VSCE_PAT" not in marketplace

    open_vsx = _step(vsce_job, "Publish to Open VSX")
    assert "OVSX_PAT: ${{ secrets.OVSX_PAT }}" in open_vsx
    assert "$env:OVSX_PAT" in open_vsx
    assert "-p $env:OVSX_PAT" not in open_vsx
    assert "npm install" not in open_vsx

    install = _step(vsce_job, "Install locked publishing tools")
    assert "OVSX_PAT" not in install
    assert "VSCE_PAT" not in install
    assert "npm ci --ignore-scripts" in install
    assert "npm install" not in install
    assert "npx --no-install vsce" in marketplace
    assert "npx --no-install ovsx" in open_vsx
    assert "Residual risk: external registries do not offer a shared transaction" in WORKFLOW


def test_publisher_clis_and_transitive_packages_are_integrity_locked():
    assert PACKAGE_JSON["devDependencies"]["@vscode/vsce"] == "3.2.2"
    assert PACKAGE_JSON["devDependencies"]["ovsx"] == "1.0.2"
    for package_name in ("node_modules/@vscode/vsce", "node_modules/ovsx"):
        entry = PACKAGE_LOCK["packages"][package_name]
        assert entry["integrity"].startswith("sha512-")
    assert "npm install -g" not in WORKFLOW
    assert "npx --no-install vsce package" in _job("build-vsix")


def test_python_package_uses_current_spdx_license_metadata():
    tomllib = pytest.importorskip("tomllib")

    project_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(project_path.read_text(encoding="utf-8"))
    assert project["project"]["license"] == "Apache-2.0"
    assert not any(
        classifier.startswith("License ::") for classifier in project["project"]["classifiers"]
    )
    assert "setuptools>=77.0.0" in project["build-system"]["requires"]


def test_release_runs_are_serialized_per_ref_without_cancelling_in_flight_publish():
    top = WORKFLOW.split("jobs:", maxsplit=1)[0]
    assert re.search(
        r"(?m)^concurrency:\n  group: release-\$\{\{ github\.workflow \}\}-"
        r"\$\{\{ github\.ref \}\}$",
        top,
    )
    assert re.search(r"(?m)^  cancel-in-progress: false$", top)


def test_build_and_privileged_publish_jobs_are_separated():
    vsix_build = _job("build-vsix")
    assert "contents: read" in vsix_build
    assert "secrets." not in vsix_build
    assert "persist-credentials: false" in vsix_build

    release_upload = _job("upload-vsix-release")
    assert re.search(
        r"(?m)^    needs:\n      - build-vsix\n      - build-python$",
        release_upload,
    )
    assert "actions/checkout" not in release_upload

    marketplace = _job("publish-marketplaces")
    assert "needs: upload-vsix-release" in marketplace
    assert "contents: write" not in marketplace
    assert "actions/checkout" not in marketplace
    assert 'node-version: "22"' in marketplace

    lock_upload = vsix_build.index("- name: Upload locked publisher tool manifest")
    first_npm_execution = vsix_build.index("run: npm ci")
    assert lock_upload < first_npm_execution

    python_build = _job("build-python")
    assert "id-token: write" not in python_build
    assert "persist-credentials: false" in python_build

    pypi_publish = _job("publish-pypi")
    assert re.search(
        r"(?m)^    needs:\n      - build-python\n      - upload-vsix-release$",
        pypi_publish,
    )
    assert "actions/checkout" not in pypi_publish
    assert "pip install" not in pypi_publish
    assert "python -m build" not in pypi_publish

    github_publish = _job("publish-github-release")
    assert "contents: write" in github_publish
    assert "actions/checkout" not in github_publish
    assert "secrets." not in github_publish


def test_public_github_release_is_the_final_fail_closed_transition():
    upload_job = _job("upload-vsix-release")
    draft = _step(upload_job, "Create or reuse draft GitHub Release")
    final_job = _job("publish-github-release")
    publish = _step(final_job, "Publish verified draft GitHub Release")

    assert 'gh release create "$RELEASE_TAG"' in draft
    assert "--draft" in draft
    assert "--verify-tag" in draft
    assert ".isDraft == true" in draft
    assert "Refusing to upload to a public release" in draft

    assert re.search(
        r"(?m)^    needs:\n"
        r"      - upload-vsix-release\n"
        r"      - publish-marketplaces\n"
        r"      - publish-pypi$",
        final_job,
    )
    assert "always()" not in final_job
    assert "continue-on-error" not in final_job
    assert 'gh release edit "$RELEASE_TAG" --draft=false --verify-tag' in publish
    assert ".isDraft == true" in publish
    assert ".isDraft == false" in publish
    assert "sha256sum" in publish
    assert ".digest" in publish
    assert "application/octet-stream" in publish
    assert "Unexpected release asset set" in publish
    assert publish.index("Unexpected release asset set") < publish.index("--draft=false")
    assert publish.index("sha256sum") < publish.index("--draft=false")

    # No earlier job or action may make the release public. Therefore any
    # failed build, verification, upload, or external publisher leaves at most
    # a private draft behind.
    assert WORKFLOW.count("--draft=false") == 1
    assert WORKFLOW.index("publish-github-release:") < WORKFLOW.index("--draft=false")
    draft_upload = _step(upload_job, "Upload VSIX files to draft Release")
    assert 'gh release upload "$RELEASE_TAG" "${pending_assets[@]}"' in draft_upload
    assert "--clobber" not in draft_upload
    assert "--draft=false" not in draft_upload


def test_release_tag_cannot_move_between_build_and_publication():
    draft = _step(_job("upload-vsix-release"), "Create or reuse draft GitHub Release")
    publish = _step(_job("publish-github-release"), "Publish verified draft GitHub Release")

    for step in (draft, publish):
        assert "SOURCE_REF_SHA: ${{ github.sha }}" in step
        assert "git/ref/tags/$RELEASE_TAG" in step
        assert 'current_ref_sha" != "$SOURCE_REF_SHA' in step
        assert "Release tag moved after this workflow was triggered" in step


def test_release_asset_upload_fails_closed_instead_of_overwriting():
    job = _job("upload-vsix-release")
    prepare = _step(job, "Prepare idempotent VSIX upload set")
    upload = _step(job, "Upload VSIX files to draft Release")
    verify = _step(job, "Verify draft VSIX asset digests")

    assert "id: prepare_vsix" in prepare
    assert "pending-vsix" in prepare
    assert "sha256sum" in prepare
    assert ".digest" in prepare
    assert "application/octet-stream" in prepare
    assert "Release asset collision" in prepare
    assert "has_pending=true" in prepare
    assert "has_pending=false" in prepare

    assert "if: steps.prepare_vsix.outputs.has_pending == 'true'" in upload
    assert "pending-vsix/*.vsix" in upload
    assert 'gh release upload "$RELEASE_TAG" "${pending_assets[@]}"' in upload
    assert "--clobber" not in upload

    prepare_index = job.index("- name: Prepare idempotent VSIX upload set")
    upload_index = job.index("- name: Upload VSIX files to draft Release")
    verify_index = job.index("- name: Verify draft VSIX asset digests")
    assert prepare_index < upload_index < verify_index
    assert "sha256sum" in verify
    assert ".digest" in verify
    assert "application/octet-stream" in verify
    assert ".draft == true" in verify
    assert "Unexpected release asset set" in verify
    assert "diff -u" in verify
    assert "exit 1" in verify


def test_release_tag_is_passed_via_env_and_metadata_uses_a_json_serializer():
    vsix_version = _step(_job("build-vsix"), "Verify version matches release tag")
    python_version = _step(_job("build-python"), "Verify version matches release tag")
    metadata = _step(_job("build-vsix"), "Record build metadata")

    for step in (vsix_version, python_version, metadata):
        assert "RELEASE_TAG:" in step
        run_script = step.split("run:", maxsplit=1)[1]
        assert "${{ github.event.release.tag_name }}" not in run_script

    assert "JSON.stringify" in metadata
    assert "process.env.RELEASE_TAG" in metadata


def test_build_metadata_is_reproducible_for_the_same_commit():
    metadata_step = _step(_job("build-vsix"), "Record build metadata")
    assert "git show -s --format=%cI" in metadata_step
    assert '"source_commit_time"' in metadata_step
    assert "date -u" not in metadata_step
    assert '"built_at"' not in metadata_step


def test_windows_bundle_preserves_version_provenance_and_smokes_after_prune():
    prune = BUNDLE_SCRIPT.index("Prune-Folder $binPythonDir")
    post_prune = BUNDLE_SCRIPT.index("Running post-prune bundle verification")
    assert post_prune > prune
    assert 'Name -notlike "diffinite-*.dist-info"' in BUNDLE_SCRIPT
    assert '$_.Name -ne "METADATA"' in BUNDLE_SCRIPT
    assert "Expected exactly one diffinite dist-info directory" in BUNDLE_SCRIPT
    assert "from diffinite import __version__" in BUNDLE_SCRIPT[post_prune:]
    assert "--metrics-only" not in BUNDLE_SCRIPT[post_prune:]
    assert "--report-json" in BUNDLE_SCRIPT[post_prune:]
    assert "--report-pdf" in BUNDLE_SCRIPT[post_prune:]
    assert "from pypdf import PdfReader" in BUNDLE_SCRIPT[post_prune:]
    assert "ConvertFrom-Json" in BUNDLE_SCRIPT[post_prune:]


def test_python_build_and_bundle_tools_are_hash_locked_without_isolation():
    python_build = _job("build-python")
    assert "--require-hashes" in python_build
    assert "requirements-build.lock" in python_build
    assert "python -m build --no-isolation" in python_build
    assert "pip install build" not in python_build

    assert "requirements-build.lock" in BUNDLE_SCRIPT
    assert "--require-hashes" in BUNDLE_SCRIPT
    assert "--no-build-isolation" in BUNDLE_SCRIPT
    assert "pip install setuptools wheel" not in BUNDLE_SCRIPT
    assert "pip install pip-licenses" not in BUNDLE_SCRIPT

    assert "pip-compile with Python 3.12" in RUNTIME_LOCK
    assert "pip-compile with Python 3.12" in BUILD_LOCK
    assert "setuptools==" in BUILD_LOCK
    assert "--hash=sha256:" in BUILD_LOCK


def test_bootstrap_and_runtime_locks_exclude_audited_vulnerable_versions():
    assert '$expectedPipVersion = "26.2.2"' in BUNDLE_SCRIPT
    assert "actualPipVersion -ne $expectedPipVersion" in BUNDLE_SCRIPT
    minimums = {
        "certifi": "2026.10.18",
        "cryptography": "50.0.0",
        "idna": "3.15",
        "lxml": "6.1.0",
        "pillow": "13.0.0",
        "pypdf": "6.16.1",
        "urllib3": "2.8.0",
    }
    for package, minimum in minimums.items():
        assert _locked_version(RUNTIME_LOCK, package) >= Version(minimum)


def test_ci_audits_the_exact_hashed_runtime_lock():
    audit_job = re.search(
        r"(?ms)^  dependency-audit:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        CI_WORKFLOW,
    )
    assert audit_job
    body = audit_job.group("body")
    assert "pip-audit==2.9.0" in body
    assert "requirements-bundle.lock" in body
    assert "--disable-pip --strict" in body


def test_lock_regeneration_uses_tracked_inputs_and_release_python_family():
    assert "$workspaceRoot\\pyproject.toml" in LOCK_SCRIPT
    assert "requirements-build.in" in LOCK_SCRIPT
    assert 'resolverVersion -ne "3.12"' in LOCK_SCRIPT
    assert "requirements.txt" not in LOCK_SCRIPT
    assert '$expectedPipToolsVersion = "7.6.0"' in LOCK_SCRIPT
    assert "actualPipToolsVersion -ne $expectedPipToolsVersion" in LOCK_SCRIPT


def test_license_generation_is_isolated_and_fails_closed_on_bad_inventory():
    bundled_python_invocations = re.findall(
        r'(?m)^& (?:"\$binPythonDir\\python\.exe"|\$pythonExeTemplate)([^\n]*)',
        BUNDLE_SCRIPT,
    )
    assert bundled_python_invocations
    assert all(args.lstrip().startswith("-I ") for args in bundled_python_invocations)
    assert "-I -m piplicenses" in BUNDLE_SCRIPT
    assert "Duplicate package in dependency license inventory" in BUNDLE_SCRIPT
    assert "Missing package from dependency license inventory" in BUNDLE_SCRIPT
    assert "Unexpected package in dependency license inventory" in BUNDLE_SCRIPT
    assert "third-party-licenses" in BUNDLE_SCRIPT
    assert "Missing vetted license fallback" in BUNDLE_SCRIPT


def test_release_builds_are_gated_on_the_test_suite():
    """No artifact is built (and so none published) unless pytest passed."""
    yaml = pytest.importorskip("yaml")
    jobs = yaml.safe_load(WORKFLOW)["jobs"]
    assert any("pytest" in str(step.get("run", "")) for step in jobs["test"]["steps"])
    for build_job in ("build-vsix", "build-python"):
        needs = jobs[build_job].get("needs")
        assert needs == "test" or "test" in (needs or [])


def test_pip_bootstrap_uses_an_immutable_hash_pinned_wheel():
    """A rolling get-pip.py URL cannot be hash-pinned; the pip wheel can."""
    assert not re.search(r"Invoke-WebRequest[^\n]*bootstrap\.pypa\.io", BUNDLE_SCRIPT)
    assert "https://files.pythonhosted.org/packages/" in BUNDLE_SCRIPT
    assert re.search(r'\$expectedPipWheelHash = "[0-9A-F]{64}"', BUNDLE_SCRIPT)
    assert "actualPipWheelHash -ne $expectedPipWheelHash" in BUNDLE_SCRIPT
    assert "'install', '--no-index'" in BUNDLE_SCRIPT
