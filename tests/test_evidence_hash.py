"""Tests for evidence integrity features: hashing, manifest, bundle."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from diffinite.evidence import (
    _sha256_file,
    compute_file_hashes,
    create_evidence_bundle,
    write_manifest,
)
from diffinite.models import FileHashEntry


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
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
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
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()

        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF-fake-content")

        manifest_path = str(tmp_path / "manifest.sha256.json")
        write_manifest(str(d_a), str(d_b), [], [], [str(report)], manifest_path)

        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        assert len(data["reports"]) == 1
        assert data["reports"][0]["path"] == "report.pdf"
        assert len(data["reports"][0]["sha256"]) == 64  # hex SHA-256


# ---------------------------------------------------------------------------
# create_evidence_bundle
# ---------------------------------------------------------------------------
class TestCreateEvidenceBundle:
    """Verify evidence bundle zip creation."""

    def test_bundle_creates_zip(self, tmp_path):
        """Bundle zip is created with expected structure."""
        d_a = tmp_path / "src_a"; d_a.mkdir()
        d_b = tmp_path / "src_b"; d_b.mkdir()
        (d_a / "main.py").write_text("print('a')", encoding="utf-8")
        (d_b / "main.py").write_text("print('b')", encoding="utf-8")

        manifest = tmp_path / "manifest.sha256.json"
        manifest.write_text("{}", encoding="utf-8")

        zip_path = str(tmp_path / "evidence.zip")
        create_evidence_bundle(
            str(d_a), str(d_b), ["main.py"], ["main.py"], str(manifest), [], zip_path,
        )

        assert Path(zip_path).exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            assert "source_a/main.py" in names
            assert "source_b/main.py" in names
            assert "manifest.sha256.json" in names

    def test_bundle_sha256_sidecar(self, tmp_path):
        """Sidecar .sha256 file is created and matches actual zip hash."""
        d_a = tmp_path / "src_a"; d_a.mkdir()
        d_b = tmp_path / "src_b"; d_b.mkdir()
        (d_a / "x.txt").write_text("x", encoding="utf-8")

        manifest = tmp_path / "manifest.sha256.json"
        manifest.write_text("{}", encoding="utf-8")

        zip_path = str(tmp_path / "evidence.zip")
        returned_hash = create_evidence_bundle(
            str(d_a), str(d_b), ["x.txt"], [], str(manifest), [], zip_path,
        )

        # Verify sidecar file
        sidecar = Path(f"{zip_path}.sha256")
        assert sidecar.exists()

        # Verify hash matches
        actual_hash = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
        assert returned_hash == actual_hash
        assert actual_hash in sidecar.read_text(encoding="utf-8")


class TestBundleManifestIntegrity:
    """Bundle contents must match the hashed/manifest file set, not a fresh walk."""

    def test_bundle_only_contains_listed_files(self, tmp_path):
        d_a = tmp_path / "src_a"; d_a.mkdir()
        (d_a / "keep.py").write_text("x = 1", encoding="utf-8")
        # A file on disk that was NOT in the hashed list (e.g. ignored / symlink)
        # must NOT leak into the bundle.
        (d_a / "secret.env").write_text("TOKEN=abc", encoding="utf-8")

        manifest = tmp_path / "manifest.sha256.json"
        manifest.write_text("{}", encoding="utf-8")
        zip_path = str(tmp_path / "ev.zip")

        create_evidence_bundle(
            str(d_a), str(tmp_path / "empty_b"),
            ["keep.py"], [], str(manifest), [], zip_path,
        )
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert "source_a/keep.py" in names
        assert "source_a/secret.env" not in names

    def test_report_basename_collision_de_duplicated(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        manifest = tmp_path / "manifest.sha256.json"
        manifest.write_text("{}", encoding="utf-8")
        # Two distinct reports that share a basename.
        r1 = tmp_path / "one" / "report.pdf"; r1.parent.mkdir()
        r2 = tmp_path / "two" / "report.pdf"; r2.parent.mkdir()
        r1.write_text("PDF1", encoding="utf-8")
        r2.write_text("PDF2", encoding="utf-8")
        zip_path = str(tmp_path / "ev.zip")

        create_evidence_bundle(
            str(d_a), str(tmp_path / "b"),
            [], [], str(manifest), [str(r1), str(r2)], zip_path,
        )
        with zipfile.ZipFile(zip_path) as zf:
            report_members = [n for n in zf.namelist() if n.endswith(".pdf")]
        # Both reports survive as distinct members (no silent overwrite).
        assert len(report_members) == 2
        assert len(set(report_members)) == 2


class TestManifestPrivacy:
    """Manifest must not leak absolute source-root paths by default."""

    def test_root_is_basename_not_absolute_path(self, tmp_path):
        d_a = tmp_path / "plaintiff_code"; d_a.mkdir()
        d_b = tmp_path / "defendant_code"; d_b.mkdir()
        (d_a / "f.py").write_text("a", encoding="utf-8")
        ha = compute_file_hashes(str(d_a), ["f.py"])
        manifest_path = str(tmp_path / "m.json")
        write_manifest(str(d_a), str(d_b), ha, [], [], manifest_path)

        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        assert data["source_a"]["root"] == "plaintiff_code"
        assert str(tmp_path) not in json.dumps(data["source_a"])

    def test_explicit_label_is_honored(self, tmp_path):
        d_a = tmp_path / "a"; d_a.mkdir()
        manifest_path = str(tmp_path / "m.json")
        write_manifest(
            str(d_a), str(tmp_path / "b"), [], [], [], manifest_path,
            root_label_a="EXHIBIT-A", root_label_b="EXHIBIT-B",
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

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--hash",
        ])

    def test_bundle_flag_accepted(self, tmp_path):
        """--bundle flag parses and creates zip."""
        from diffinite.cli import main

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        zip_path = str(tmp_path / "bundle.zip")
        main([
            str(d_a), str(d_b),
            "-o", str(tmp_path / "out.pdf"),
            "--bundle", zip_path,
        ])
        assert Path(zip_path).exists()
        assert Path(f"{zip_path}.sha256").exists()

    def test_manifest_always_created(self, tmp_path):
        """manifest.sha256.json is created even without --hash or --bundle."""
        from diffinite.cli import main

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        output = str(tmp_path / "out.pdf")
        main([str(d_a), str(d_b), "-o", output])

        manifest = tmp_path / "manifest.sha256.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["tool"] == "diffinite"
