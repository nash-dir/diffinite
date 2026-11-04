"""Tests for evidence integrity features: hashing, manifest, bundle."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import diffinite.evidence as evidence
from diffinite.evidence import (
    SourceIntegrityError,
    compute_file_hashes,
    create_evidence_bundle,
    create_immutable_snapshot,
    verify_snapshot_matches_manifest,
    write_manifest,
)
from diffinite.models import FileHashEntry


def _write_bundle_manifest(
    path: Path,
    dir_a: Path,
    dir_b: Path,
    files_a: list[str],
    files_b: list[str],
    reports: list[str] | None = None,
) -> None:
    write_manifest(
        str(dir_a),
        str(dir_b),
        compute_file_hashes(str(dir_a), files_a),
        compute_file_hashes(str(dir_b), files_b),
        reports or [],
        str(path),
    )


def _seed_existing_bundle_pair(zip_path: Path) -> tuple[bytes, str]:
    """Create a valid old ZIP/sidecar pair whose exact bytes can be asserted."""
    old_zip = b"previous evidence bundle"
    old_hash = hashlib.sha256(old_zip).hexdigest()
    old_sidecar = f"{old_hash}  {zip_path.name}\n"
    zip_path.write_bytes(old_zip)
    Path(f"{zip_path}.sha256").write_text(old_sidecar, encoding="utf-8")
    return old_zip, old_sidecar


def _assert_existing_bundle_pair(
    zip_path: Path,
    old_zip: bytes,
    old_sidecar: str,
) -> None:
    assert zip_path.read_bytes() == old_zip
    assert Path(f"{zip_path}.sha256").read_text(encoding="utf-8") == old_sidecar


class TestDirectApiBoundaries:
    """Public evidence helpers must not escape or mutate their source roots."""

    def test_hashing_rejects_parent_traversal(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (tmp_path / "outside.py").write_text("secret\n", encoding="utf-8")

        with pytest.raises(SourceIntegrityError, match="Unsafe|relative|path"):
            compute_file_hashes(str(source), ["../outside.py"])

    def test_snapshot_rejects_destination_inside_source(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "a.py").write_text("value = 1\n", encoding="utf-8")
        hashes = compute_file_hashes(str(source), ["a.py"])
        destination = source / "snapshot"

        with pytest.raises(SourceIntegrityError, match="snapshot|source|overlap"):
            create_immutable_snapshot(
                str(source),
                ["a.py"],
                hashes,
                str(destination),
            )

        assert not destination.exists()

    def test_snapshot_rejects_parent_traversal_in_file_list(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        outside = tmp_path / "outside.py"
        outside.write_text("secret\n", encoding="utf-8")
        digest = hashlib.sha256(outside.read_bytes()).hexdigest()
        entry = FileHashEntry(
            rel_path="../outside.py",
            sha256=digest,
            size_bytes=outside.stat().st_size,
            modified_at="test-only",
        )
        destination = tmp_path / "outputs" / "snapshot"

        with pytest.raises(SourceIntegrityError, match="Unsafe|relative|path"):
            create_immutable_snapshot(
                str(source),
                ["../outside.py"],
                [entry],
                str(destination),
            )

        assert not (tmp_path / "outputs" / "outside.py").exists()

    def test_snapshot_verifier_rejects_changed_bytes_and_file_set(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "a.py").write_bytes(b"value = 1\n")
        hashes = compute_file_hashes(str(source), ["a.py"])
        snapshot = tmp_path / "snapshot"
        snapshot_path = create_immutable_snapshot(
            str(source),
            ["a.py"],
            hashes,
            str(snapshot),
        )

        verify_snapshot_matches_manifest(snapshot_path, hashes, side="A")
        (snapshot / "a.py").write_bytes(b"value = 2\n")
        with pytest.raises(SourceIntegrityError, match="snapshot A bytes changed"):
            verify_snapshot_matches_manifest(snapshot_path, hashes, side="A")

        (snapshot / "a.py").write_bytes(b"value = 1\n")
        (snapshot / "injected.py").write_bytes(b"unexpected\n")
        with pytest.raises(SourceIntegrityError, match="snapshot A file set changed"):
            verify_snapshot_matches_manifest(snapshot_path, hashes, side="A")

    def test_bundle_output_cannot_be_inside_a_source_root(self, tmp_path):
        source_a = tmp_path / "source-a"
        source_a.mkdir()
        source_b = tmp_path / "source-b"
        source_b.mkdir()
        (source_a / "a.py").write_text("value = 1\n", encoding="utf-8")
        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, source_a, source_b, ["a.py"], [])
        bundle = source_a / "evidence.zip"

        with pytest.raises(SourceIntegrityError, match="output|source|overlap"):
            create_evidence_bundle(
                str(source_a),
                str(source_b),
                ["a.py"],
                [],
                str(manifest),
                [],
                str(bundle),
            )

        assert not bundle.exists()
        assert not Path(f"{bundle}.sha256").exists()


# ---------------------------------------------------------------------------
# compute_file_hashes
# ---------------------------------------------------------------------------
class TestComputeFileHashes:
    """Verify SHA-256 hash computation."""

    def test_correct_hash(self, tmp_path):
        """Hash matches hashlib reference implementation."""
        content = b"hello diffinite\n"
        (tmp_path / "test.py").write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()

        hashes = compute_file_hashes(str(tmp_path), ["test.py"])

        assert len(hashes) == 1
        assert hashes[0].sha256 == expected
        assert hashes[0].rel_path == "test.py"
        assert hashes[0].size_bytes == len(content)

    def test_multiple_files_sorted(self, tmp_path):
        """Multiple files are returned sorted by rel_path."""
        (tmp_path / "b.txt").write_text("B", encoding="utf-8")
        (tmp_path / "a.txt").write_text("A", encoding="utf-8")

        hashes = compute_file_hashes(str(tmp_path), ["b.txt", "a.txt"])

        assert [h.rel_path for h in hashes] == ["a.txt", "b.txt"]

    def test_empty_file(self, tmp_path):
        """Empty file gets a valid hash."""
        (tmp_path / "empty.txt").write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()

        hashes = compute_file_hashes(str(tmp_path), ["empty.txt"])

        assert hashes[0].sha256 == expected
        assert hashes[0].size_bytes == 0

    def test_skips_missing_file(self, tmp_path):
        """Missing files are silently skipped."""
        hashes = compute_file_hashes(str(tmp_path), ["nonexistent.py"])
        assert hashes == []


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------
class TestWriteManifest:
    """Verify manifest.sha256.json generation."""

    def test_manifest_structure(self, tmp_path):
        """Manifest contains all required keys."""
        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        (d_a / "foo.py").write_text("foo", encoding="utf-8")
        (d_b / "bar.py").write_text("bar", encoding="utf-8")

        hashes_a = compute_file_hashes(str(d_a), ["foo.py"])
        hashes_b = compute_file_hashes(str(d_b), ["bar.py"])

        manifest_path = str(tmp_path / "manifest.sha256.json")
        write_manifest(str(d_a), str(d_b), hashes_a, hashes_b, [], manifest_path)

        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

        # Required top-level keys
        for key in ("tool", "version", "created_at", "source_a", "source_b", "reports"):
            assert key in data, f"Missing key: {key}"

        assert data["tool"] == "diffinite"
        assert data["source_a"]["file_count"] == 1
        assert data["source_b"]["file_count"] == 1
        assert len(data["source_a"]["files"]) == 1
        assert data["source_a"]["files"][0]["path"] == "foo.py"

    def test_manifest_includes_report_hashes(self, tmp_path):
        """Reports are hashed when they exist."""
        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()

        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF-fake-content")

        manifest_path = str(tmp_path / "manifest.sha256.json")
        write_manifest(str(d_a), str(d_b), [], [], [str(report)], manifest_path)

        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        assert len(data["reports"]) == 1
        assert data["reports"][0]["path"] == "report.pdf"
        assert len(data["reports"][0]["sha256"]) == 64  # hex SHA-256

    @pytest.mark.parametrize("artifact_state", ["missing", "empty"])
    def test_manifest_fails_closed_for_invalid_report_artifact(
        self,
        tmp_path,
        artifact_state,
    ):
        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        report = tmp_path / "report.json"
        if artifact_state == "empty":
            report.write_bytes(b"")
        manifest = tmp_path / "manifest.sha256.json"
        old_manifest = b'{"old": true}\n'
        manifest.write_bytes(old_manifest)

        with pytest.raises(SourceIntegrityError, match="report|artifact|empty|missing"):
            write_manifest(
                str(d_a),
                str(d_b),
                [],
                [],
                [str(report)],
                str(manifest),
            )

        assert manifest.read_bytes() == old_manifest

    def test_manifest_rejects_report_symlink(self, tmp_path):
        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        target = tmp_path / "actual-report.json"
        target.write_text("{}\n", encoding="utf-8")
        report = tmp_path / "report.json"
        try:
            report.symlink_to(target)
        except OSError:
            pytest.skip("file symlinks are unavailable on this platform")

        with pytest.raises(SourceIntegrityError, match="symlink|junction"):
            write_manifest(
                str(d_a),
                str(d_b),
                [],
                [],
                [str(report)],
                str(tmp_path / "manifest.sha256.json"),
            )

    def test_manifest_output_cannot_mutate_a_source_root(self, tmp_path):
        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        source = d_a / "manifest.sha256.json"
        original = b"source evidence\n"
        source.write_bytes(original)

        with pytest.raises(SourceIntegrityError, match="Manifest output.*source"):
            write_manifest(str(d_a), str(d_b), [], [], [], str(source))

        assert source.read_bytes() == original

    def test_manifest_output_cannot_replace_a_report_input(self, tmp_path):
        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        report = tmp_path / "report.json"
        original = b'{"report": true}\n'
        report.write_bytes(original)

        with pytest.raises(SourceIntegrityError, match="collides.*report"):
            write_manifest(
                str(d_a),
                str(d_b),
                [],
                [],
                [str(report)],
                str(report),
            )

        assert report.read_bytes() == original


# ---------------------------------------------------------------------------
# create_evidence_bundle
# ---------------------------------------------------------------------------
class TestCreateEvidenceBundle:
    """Verify evidence bundle zip creation."""

    def test_bundle_creates_zip(self, tmp_path):
        """Bundle zip is created with expected structure."""
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        d_b = tmp_path / "src_b"
        d_b.mkdir()
        (d_a / "main.py").write_text("print('a')", encoding="utf-8")
        (d_b / "main.py").write_text("print('b')", encoding="utf-8")

        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, d_b, ["main.py"], ["main.py"])

        zip_path = str(tmp_path / "evidence.zip")
        create_evidence_bundle(
            str(d_a),
            str(d_b),
            ["main.py"],
            ["main.py"],
            str(manifest),
            [],
            zip_path,
        )

        assert Path(zip_path).exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            assert "source_a/main.py" in names
            assert "source_b/main.py" in names
            assert "manifest.sha256.json" in names

    def test_bundle_sha256_sidecar(self, tmp_path):
        """Sidecar .sha256 file is created and matches actual zip hash."""
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        d_b = tmp_path / "src_b"
        d_b.mkdir()
        (d_a / "x.txt").write_text("x", encoding="utf-8")

        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, d_b, ["x.txt"], [])

        zip_path = str(tmp_path / "evidence.zip")
        returned_hash = create_evidence_bundle(
            str(d_a),
            str(d_b),
            ["x.txt"],
            [],
            str(manifest),
            [],
            zip_path,
        )

        # Verify sidecar file
        sidecar = Path(f"{zip_path}.sha256")
        assert sidecar.exists()

        # Verify hash matches
        actual_hash = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
        assert returned_hash == actual_hash
        assert actual_hash in sidecar.read_text(encoding="utf-8")

    def test_checksum_failure_preserves_previous_bundle_pair(
        self,
        tmp_path,
        monkeypatch,
    ):
        """A staged-ZIP checksum failure must not publish half of a new pair."""
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        d_b = tmp_path / "src_b"
        d_b.mkdir()
        (d_a / "x.txt").write_text("new evidence", encoding="utf-8")
        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, d_b, ["x.txt"], [])
        zip_path = tmp_path / "evidence.zip"
        old_zip, old_sidecar = _seed_existing_bundle_pair(zip_path)

        def fail_checksum(_path):
            raise OSError("injected checksum failure")

        monkeypatch.setattr(evidence, "_sha256_file", fail_checksum)

        with pytest.raises(OSError, match="injected checksum failure"):
            create_evidence_bundle(
                str(d_a),
                str(d_b),
                ["x.txt"],
                [],
                str(manifest),
                [],
                str(zip_path),
            )

        _assert_existing_bundle_pair(zip_path, old_zip, old_sidecar)

    def test_sidecar_staging_failure_preserves_previous_bundle_pair(
        self,
        tmp_path,
        monkeypatch,
    ):
        """A sidecar write/fsync failure must leave the old pair untouched."""
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        d_b = tmp_path / "src_b"
        d_b.mkdir()
        (d_a / "x.txt").write_text("new evidence", encoding="utf-8")
        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, d_b, ["x.txt"], [])
        zip_path = tmp_path / "evidence.zip"
        old_zip, old_sidecar = _seed_existing_bundle_pair(zip_path)

        def fail_sidecar_staging(*_args, **_kwargs):
            raise OSError("injected sidecar staging failure")

        monkeypatch.setattr(
            evidence,
            "_stage_hash_sidecar",
            fail_sidecar_staging,
            raising=False,
        )

        with pytest.raises(OSError, match="injected sidecar staging failure"):
            create_evidence_bundle(
                str(d_a),
                str(d_b),
                ["x.txt"],
                [],
                str(manifest),
                [],
                str(zip_path),
            )

        _assert_existing_bundle_pair(zip_path, old_zip, old_sidecar)

    @pytest.mark.parametrize("failed_target", ["zip", "sidecar"])
    def test_publish_replace_failure_restores_previous_bundle_pair(
        self,
        tmp_path,
        monkeypatch,
        failed_target,
    ):
        """Either publication replace may fail without mixing old and new files."""
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        d_b = tmp_path / "src_b"
        d_b.mkdir()
        (d_a / "x.txt").write_text("new evidence", encoding="utf-8")
        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, d_b, ["x.txt"], [])
        zip_path = tmp_path / "evidence.zip"
        sidecar = Path(f"{zip_path}.sha256")
        old_zip, old_sidecar = _seed_existing_bundle_pair(zip_path)
        target = zip_path if failed_target == "zip" else sidecar
        real_replace = evidence.os.replace
        failure_injected = False

        def fail_one_publish(source, destination):
            nonlocal failure_injected
            source_path = Path(source)
            destination_path = Path(destination)
            is_staged_publish = (
                destination_path == target
                and source_path != zip_path
                and source_path != sidecar
                and not source_path.name.endswith(".backup")
            )
            if is_staged_publish and not failure_injected:
                failure_injected = True
                raise OSError(f"injected {failed_target} replace failure")
            real_replace(source, destination)

        monkeypatch.setattr(evidence.os, "replace", fail_one_publish)

        with pytest.raises(OSError, match=f"injected {failed_target} replace failure"):
            create_evidence_bundle(
                str(d_a),
                str(d_b),
                ["x.txt"],
                [],
                str(manifest),
                [],
                str(zip_path),
            )

        assert failure_injected
        _assert_existing_bundle_pair(zip_path, old_zip, old_sidecar)

    def test_incomplete_bundle_rollback_discloses_recovery_backups(
        self,
        tmp_path,
        monkeypatch,
    ):
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        d_b = tmp_path / "src_b"
        d_b.mkdir()
        (d_a / "x.txt").write_text("new evidence", encoding="utf-8")
        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, d_b, ["x.txt"], [])
        zip_path = tmp_path / "evidence.zip"
        sidecar = Path(f"{zip_path}.sha256")
        _seed_existing_bundle_pair(zip_path)
        real_replace = evidence.os.replace

        def fail_publication_and_zip_restore(source, destination):
            source_path = Path(source)
            destination_path = Path(destination)
            if destination_path == sidecar and not source_path.name.endswith(".backup"):
                raise OSError("injected sidecar publication failure")
            if destination_path == zip_path and source_path.name.endswith(".backup"):
                raise OSError("injected zip rollback failure")
            real_replace(source, destination)

        monkeypatch.setattr(evidence.os, "replace", fail_publication_and_zip_restore)

        with pytest.raises(
            SourceIntegrityError,
            match="Recovery backups retained at:.*\\.backup",
        ):
            create_evidence_bundle(
                str(d_a),
                str(d_b),
                ["x.txt"],
                [],
                str(manifest),
                [],
                str(zip_path),
            )


class TestBundleManifestIntegrity:
    """Bundle contents must match the hashed/manifest file set, not a fresh walk."""

    def test_bundle_only_contains_listed_files(self, tmp_path):
        d_a = tmp_path / "src_a"
        d_a.mkdir()
        (d_a / "keep.py").write_text("x = 1", encoding="utf-8")
        # A file on disk that was NOT in the hashed list (e.g. ignored / symlink)
        # must NOT leak into the bundle.
        (d_a / "secret.env").write_text("TOKEN=abc", encoding="utf-8")

        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(manifest, d_a, tmp_path / "empty_b", ["keep.py"], [])
        zip_path = str(tmp_path / "ev.zip")

        create_evidence_bundle(
            str(d_a),
            str(tmp_path / "empty_b"),
            ["keep.py"],
            [],
            str(manifest),
            [],
            zip_path,
        )
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert "source_a/keep.py" in names
        assert "source_a/secret.env" not in names

    def test_report_basename_collision_de_duplicated(self, tmp_path):
        d_a = tmp_path / "a"
        d_a.mkdir()
        manifest = tmp_path / "manifest.sha256.json"
        # Two distinct reports that share a basename.
        r1 = tmp_path / "one" / "report.pdf"
        r1.parent.mkdir()
        r2 = tmp_path / "two" / "report.pdf"
        r2.parent.mkdir()
        r1.write_text("PDF1", encoding="utf-8")
        r2.write_text("PDF2", encoding="utf-8")
        _write_bundle_manifest(
            manifest,
            d_a,
            tmp_path / "b",
            [],
            [],
            [str(r1), str(r2)],
        )
        zip_path = str(tmp_path / "ev.zip")

        create_evidence_bundle(
            str(d_a),
            str(tmp_path / "b"),
            [],
            [],
            str(manifest),
            [str(r1), str(r2)],
            zip_path,
        )
        with zipfile.ZipFile(zip_path) as zf:
            report_members = [n for n in zf.namelist() if n.endswith(".pdf")]
        # Both reports survive as distinct members (no silent overwrite).
        assert len(report_members) == 2
        assert len(set(report_members)) == 2

    @pytest.mark.parametrize("reserved_name", ["source_a", "source_b", "reports"])
    def test_report_cannot_collide_with_bundle_namespace(self, tmp_path, reserved_name):
        d_a = tmp_path / "left"
        d_b = tmp_path / "right"
        d_a.mkdir()
        d_b.mkdir()
        (d_a / "file.py").write_text("x = 1\n", encoding="utf-8")
        report = tmp_path / reserved_name
        report.write_text("report bytes", encoding="utf-8")
        manifest = tmp_path / "manifest.sha256.json"
        _write_bundle_manifest(
            manifest,
            d_a,
            d_b,
            ["file.py"],
            [],
            [str(report)],
        )
        archive_path = tmp_path / f"{reserved_name}.zip"

        create_evidence_bundle(
            str(d_a),
            str(d_b),
            ["file.py"],
            [],
            str(manifest),
            [str(report)],
            str(archive_path),
        )

        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            archive.extractall(tmp_path / f"extract-{reserved_name}")
        assert "source_a/file.py" in names
        assert f"reports/{reserved_name}" in names
        assert reserved_name not in names


class TestManifestPrivacy:
    """Manifest must not leak absolute source-root paths by default."""

    def test_root_is_basename_not_absolute_path(self, tmp_path):
        d_a = tmp_path / "plaintiff_code"
        d_a.mkdir()
        d_b = tmp_path / "defendant_code"
        d_b.mkdir()
        (d_a / "f.py").write_text("a", encoding="utf-8")
        ha = compute_file_hashes(str(d_a), ["f.py"])
        manifest_path = str(tmp_path / "m.json")
        write_manifest(str(d_a), str(d_b), ha, [], [], manifest_path)

        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        assert data["source_a"]["root"] == "plaintiff_code"
        assert str(tmp_path) not in json.dumps(data["source_a"])

    def test_explicit_label_is_honored(self, tmp_path):
        d_a = tmp_path / "a"
        d_a.mkdir()
        manifest_path = str(tmp_path / "m.json")
        write_manifest(
            str(d_a),
            str(tmp_path / "b"),
            [],
            [],
            [],
            manifest_path,
            root_label_a="EXHIBIT-A",
            root_label_b="EXHIBIT-B",
        )
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        assert data["source_a"]["root"] == "EXHIBIT-A"
        assert data["source_b"]["root"] == "EXHIBIT-B"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------
class TestHashBundleCli:
    """Verify --hash and --bundle CLI flags."""

    def test_hash_flag_accepted(self, tmp_path):
        """--hash flag parses and runs without error."""
        from diffinite.cli import main

        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        main(
            [
                str(d_a),
                str(d_b),
                "-o",
                str(tmp_path / "out.pdf"),
                "--hash",
            ]
        )

    def test_bundle_flag_accepted(self, tmp_path):
        """--bundle flag parses and creates zip."""
        from diffinite.cli import main

        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        zip_path = str(tmp_path / "bundle.zip")
        main(
            [
                str(d_a),
                str(d_b),
                "-o",
                str(tmp_path / "out.pdf"),
                "--bundle",
                zip_path,
            ]
        )
        assert Path(zip_path).exists()
        assert Path(f"{zip_path}.sha256").exists()

    def test_manifest_always_created(self, tmp_path):
        """manifest.sha256.json is created even without --hash or --bundle."""
        from diffinite.cli import main

        d_a = tmp_path / "a"
        d_a.mkdir()
        d_b = tmp_path / "b"
        d_b.mkdir()
        output = str(tmp_path / "out.pdf")
        main([str(d_a), str(d_b), "-o", output])

        manifest = tmp_path / "manifest.sha256.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["tool"] == "diffinite"
