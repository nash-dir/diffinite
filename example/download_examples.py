#!/usr/bin/env python3
"""Download example datasets for Diffinite benchmarks.

Downloads freely-available source code from public repositories
to set up the example/ directory for benchmark testing.

Safety:
    - No external packages — stdlib only (urllib, zipfile, pathlib)
    - HTTPS only
    - Idempotent: skips download if files already exist
    - Path-traversal protection on zip extraction

Usage:
    python example/download_examples.py              # download all
    python example/download_examples.py --clean      # remove & re-download
    python example/download_examples.py --dataset aosp  # download one dataset
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Dataset definitions
# ---------------------------------------------------------------------------

# 1. AOSP Android 9 vs 11 — same codebase, minor evolutionary edits
_AOSP_PIE = "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/pie-release/core/java/android/os"
_AOSP_11 = "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android-11.0.0_r1/core/java/android/os"

# Benchmark sources pinned to commit SHAs (a branch or tag name can move; a commit
# cannot). Resolved with `git ls-remote <repo> <tag>^{}`.
# platform/libcore tag android-4.4_r1 (Android 4.4 KitKat). The aosp-mirror GitHub
# copy of kitkat-release no longer serves these files (HTTP 404), so they are
# fetched from Google's own Gitiles server, which returns base64 (?format=TEXT).
_LIBCORE_KITKAT = ("https://android.googlesource.com/platform/libcore/+/"
                   "e239af5ac0b3989363b2fed49076fa8a9d69d454")
# openjdk/jdk tag jdk7-b147.
_OPENJDK7 = ("https://raw.githubusercontent.com/openjdk/jdk/"
             "7b2e99178f7cf41ecd86b2ccfba38ea653e815e7/jdk/src/share/classes/java")
# eclipse/eclipse-collections release tag 13.0.0.
_ECLIPSE_COLLECTIONS = ("https://raw.githubusercontent.com/eclipse/eclipse-collections/"
                        "cff067d4fb8b306f394a140d043ec6ee1666093d/eclipse-collections/"
                        "src/main/java/org/eclipse/collections/impl")

DATASETS: dict[str, dict] = {
    "aosp": {
        "description": "AOSP Android 9 vs 11 (Handler/Looper/Message)",
        "dirs": {"left": {}, "right": {}},
        "files": {
            "left/Looper.java":  f"{_AOSP_PIE}/Looper.java",
            "left/Handler.java": f"{_AOSP_PIE}/Handler.java",
            "left/Message.java": f"{_AOSP_PIE}/Message.java",
            "right/Looper.java":  f"{_AOSP_11}/Looper.java",
            "right/Handler.java": f"{_AOSP_11}/Handler.java",
            "right/Message.java": f"{_AOSP_11}/Message.java",
        },
    },

    # 2. Google v. Oracle — AOSP reimplementation of OpenJDK API
    "Case-Oracle": {
        "description": "Google v. Oracle API headers (AOSP vs OpenJDK 7)",
        "dirs": {"AOSP_Google": {}, "OpenJDK_Oracle": {}},
        "files": {
            # AOSP libcore, Android 4.4 KitKat (one of the Android versions in the
            # Oracle v. Google litigation). These classes derive from Apache Harmony
            # and carry ASF licence headers. In this release String.java lives
            # under libdvm/, not luni/.
            **{f"AOSP_Google/{f}": f"{_LIBCORE_KITKAT}/{p}?format=TEXT"
               for f, p in [
                   ("ArrayList.java", "luni/src/main/java/java/util/ArrayList.java"),
                   ("Collections.java", "luni/src/main/java/java/util/Collections.java"),
                   ("List.java", "luni/src/main/java/java/util/List.java"),
                   ("Math.java", "luni/src/main/java/java/lang/Math.java"),
                   ("String.java", "libdvm/src/main/java/java/lang/String.java"),
               ]},
            # OpenJDK 7 b147
            **{f"OpenJDK_Oracle/{f}": f"{_OPENJDK7}/{p}"
               for f, p in [
                   ("ArrayList.java", "util/ArrayList.java"),
                   ("Collections.java", "util/Collections.java"),
                   ("List.java", "util/List.java"),
                   ("Math.java", "lang/Math.java"),
                   ("String.java", "lang/String.java"),
               ]},
        },
    },

    # 3. Negative control — Eclipse Collections vs OpenJDK (independent implementations)
    "Case-NegativeControl": {
        "description": "Eclipse Collections vs OpenJDK (independent implementations, expected low similarity)",
        "dirs": {"Eclipse_Collections": {}, "OpenJDK": {}},
        "files": {
            # Eclipse Collections
            **{f"Eclipse_Collections/{f}": f"{_ECLIPSE_COLLECTIONS}/{p}"
               for f, p in [
                   ("FastList.java", "list/mutable/FastList.java"),
                   ("UnifiedSet.java", "set/mutable/UnifiedSet.java"),
                   ("UnifiedMap.java", "map/mutable/UnifiedMap.java"),
                   ("Iterate.java", "utility/Iterate.java"),
                   ("StringIterate.java", "utility/StringIterate.java"),
               ]},
            # OpenJDK 7 b147
            **{f"OpenJDK/{f}": f"{_OPENJDK7}/{p}"
               for f, p in [
                   ("ArrayList.java", "util/ArrayList.java"),
                   ("HashSet.java", "util/HashSet.java"),
                   ("HashMap.java", "util/HashMap.java"),
                   ("Collections.java", "util/Collections.java"),
                   ("String.java", "lang/String.java"),
               ]},
        },
    },

    # 4. IR-Plag plagiarism dataset (Karnalim et al. 2019, Apache-2.0) — all 7 cases.
    # This is the calibration corpus behind example/validation/calibration.json, so
    # it is pinned to an exact upstream commit and verified by SHA-256: anyone
    # (including an opposing expert) can re-derive the published error rate from
    # byte-identical inputs. Upstream ships the dataset as a zip inside the repo zip.
    "plagiarism": {
        "description": "IR-Plag dataset, cases 01-07 (labeled plagiarism levels L1-L6), pinned",
        "zip": "https://github.com/oscarkarnalim/sourcecodeplagiarismdataset/archive/"
               "f07e95120680b25f78659ed63cd6130fd05b2df8.zip",
        "zip_sha256": "288efbe08cc60837ae6509e49fd0285e7d22cb9b6e4dd6740d86229969fe9b8d",
        "inner_zip": "sourcecodeplagiarismdataset-f07e95120680b25f78659ed63cd6130fd05b2df8/"
                     "IR-Plag-Dataset.zip",
        "inner_zip_sha256": "1b96b320fd05d164b3a7ee17d8cc36992b728d3be099dc7ec39ddb7fae2ec4a4",
        "zip_subdir": "IR-Plag-Dataset",
        "expected_files": 467,
        # _tree_sha256 of the extracted tree; equals the IR-Plag digest published
        # in example/validation/holdout.json (measured 2026-11-10).
        "expected_tree_sha256": "97e2619618dbe9314285457f38f0b75a6d17927c42a775b98b293e58addf17e5",
    },

    # 5. SOCO 2014 training set (PAN@FIRE 2014, Zenodo record 7433031) — the
    # independent corpus used by tests/validation/holdout.py. Pinned by SHA-256
    # (the Zenodo record lists MD5 d07c9f553410c63ce6695c5f5754a874 for the same file).
    "soco14": {
        "description": "SOCO 2014 training set (259 Java + 79 C files, expert re-use labels), pinned",
        "zip": "https://zenodo.org/api/records/7433031/files/"
               "fire14-source-code-training-dataset.zip/content",
        "zip_sha256": "879f8ef1dd94817153f58932416b964e0388a73f2a782460299652eeb116f4c9",
        "zip_subdir": "fire14-source-code-training-dataset",
        "extract_to": "fire14-source-code-training-dataset",
        "expected_files": 340,
        # _tree_sha256 of the tree extracted from the pinned zip above (computed
        # from the archive itself, 2026-11-10).
        "expected_tree_sha256": "c9fee2d4818eb5da069a67e92ba191ff9e4e26950e150df989ce18eebcd3623e",
    },

    # 6. SQLite amalgamation (two adjacent versions)
    "sqlite": {
        "description": "SQLite amalgamation 3.45.0 vs 3.46.0",
        "zips": {
            "left":  "https://www.sqlite.org/2024/sqlite-amalgamation-3450000.zip",
            "right": "https://www.sqlite.org/2024/sqlite-amalgamation-3460000.zip",
        },
    },
}


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _is_gitiles_text(url: str) -> bool:
    """Gitiles (googlesource.com) serves raw file content base64-encoded."""
    return "googlesource.com/" in url and url.endswith("?format=TEXT")


def _download_file(url: str, dest: Path) -> bool:
    """Download a single file (base64-decoding Gitiles ?format=TEXT responses)."""
    try:
        print(f"  ↓ {dest.name:35s} ", end="", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Diffinite/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if _is_gitiles_text(url):
            data = base64.b64decode(data, validate=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"OK ({len(data):,} bytes)")
        return True
    except Exception as exc:
        print(f"FAIL ({exc})")
        return False


def _verify_sha256(data: bytes, expected: str | None, label: str) -> bool:
    """Check a pinned SHA-256; datasets without a pin are accepted as-is."""
    if expected is None:
        return True
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        print(f"  FAIL: {label} SHA-256 {actual} != pinned {expected}")
        return False
    return True


def _safe_extract_zip(zip_path: Path, dest: Path, subdir: str = "") -> int:
    """Extract zip with path-traversal protection. Returns file count."""
    count = 0
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Filter to subdir if specified
            if subdir and not info.filename.startswith(subdir):
                continue
            # Strip subdir prefix to flatten
            rel = info.filename[len(subdir):].lstrip("/") if subdir else Path(info.filename).name
            if not rel:
                continue
            target = (dest / rel).resolve()
            if not str(target).startswith(str(dest_resolved)):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            count += 1
    return count


def _tree_sha256(root: Path) -> str:
    """sha256 over sorted "<posix relative path>\\0<file sha256>\\n" lines.

    Sorted by the POSIX path string so the digest is the same on every OS. Must
    stay identical to tree_sha256 in tests/validation/error_rate.py, which
    checks the calibration corpus against the pins below before measuring it.
    """
    h = hashlib.sha256()
    entries = sorted((p.relative_to(root).as_posix(), p) for p in root.rglob("*") if p.is_file())
    for rel, f in entries:
        h.update(f"{rel}\0{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def _pinned_layout_ok(target: Path, expected: int, expected_tree: str | None = None) -> bool:
    """A pinned dataset counts as present only if its exact pinned bytes are there.

    A file count alone would accept an edited or swapped file, so when the
    dataset pins its extracted tree the digest must match as well.
    """
    if not target.is_dir():
        return False
    if sum(1 for p in target.rglob("*") if p.is_file()) != expected:
        return False
    if expected_tree is not None and _tree_sha256(target) != expected_tree:
        print(f"  {target} differs from the pinned tree digest; it will be re-extracted")
        return False
    return True


def download_dataset(name: str, config: dict, *, force: bool = False) -> bool:
    """Download a single dataset."""
    dest = EXAMPLE_DIR / name
    # Pinned datasets extract into dest/<extract_to> (or dest itself).
    target = dest / config["extract_to"] if "extract_to" in config else dest
    expected = config.get("expected_files")
    expected_tree = config.get("expected_tree_sha256")

    # Check if already exists. For a pinned dataset an older or partial layout
    # (e.g. a case-01-only IR-Plag download) is replaced, not silently reused.
    if expected is not None:
        if _pinned_layout_ok(target, expected, expected_tree) and not force:
            print(f"[{name}] Already present ({expected} files) — skipping (use --clean to re-download)")
            return True
        if target.exists():
            shutil.rmtree(target)
    # A dataset with a file map counts as present only when every expected file is
    # there; a partial earlier download is re-fetched instead of silently reused.
    elif "files" in config and all((dest / rel).is_file() for rel in config["files"]) and not force:
        print(f"[{name}] Already exists — skipping (use --clean to re-download)")
        return True
    elif "files" not in config and dest.exists() and any(dest.rglob("*.c")) and not force:
        print(f"[{name}] Already exists — skipping (use --clean to re-download)")
        return True

    if force and dest.exists():
        shutil.rmtree(dest)

    print(f"\n{'=' * 60}")
    print(f"[{name}] {config['description']}")
    print(f"{'=' * 60}")

    # Case 1: Individual file downloads
    if "files" in config:
        ok = True
        for rel_path, url in config["files"].items():
            file_dest = dest / rel_path
            file_dest.parent.mkdir(parents=True, exist_ok=True)
            if not _download_file(url, file_dest):
                ok = False
        return ok

    # Case 2: Single zip with subdir extraction (optionally hash-pinned / nested)
    if "zip" in config:
        dest.mkdir(parents=True, exist_ok=True)
        zip_path = dest / "_download.zip"
        if not _download_file(config["zip"], zip_path):
            return False
        try:
            if not _verify_sha256(zip_path.read_bytes(), config.get("zip_sha256"), "archive"):
                return False
            if "inner_zip" in config:
                with zipfile.ZipFile(zip_path) as outer:
                    inner = outer.read(config["inner_zip"])
                if not _verify_sha256(inner, config.get("inner_zip_sha256"), "inner archive"):
                    return False
                zip_path.write_bytes(inner)
            subdir = config.get("zip_subdir", "")
            target.mkdir(parents=True, exist_ok=True)
            count = _safe_extract_zip(zip_path, target, subdir)
        finally:
            zip_path.unlink(missing_ok=True)
        print(f"  Extracted {count} files")
        if expected is not None and count != expected:
            print(f"  FAIL: expected {expected} files, extracted {count}; removing partial copy")
            shutil.rmtree(target, ignore_errors=True)
            return False
        if expected_tree is not None and _tree_sha256(target) != expected_tree:
            print("  FAIL: extracted tree does not match the pinned tree digest; "
                  "removing it")
            shutil.rmtree(target, ignore_errors=True)
            return False
        return count > 0

    # Case 3: Multiple zips (sqlite)
    if "zips" in config:
        ok = True
        for side, url in config["zips"].items():
            side_dir = dest / side
            side_dir.mkdir(parents=True, exist_ok=True)
            zip_path = side_dir / "_download.zip"
            if not _download_file(url, zip_path):
                ok = False
                continue
            count = _safe_extract_zip(zip_path, side_dir)
            zip_path.unlink(missing_ok=True)
            print(f"  [{side}] Extracted {count} files")
        return ok

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download example datasets for Diffinite benchmarks.",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove existing downloads and re-download",
    )
    parser.add_argument(
        "--dataset", choices=list(DATASETS.keys()),
        help="Download only this dataset (default: all)",
    )
    args = parser.parse_args()

    print("Diffinite — Example Dataset Downloader")
    print("=" * 60)

    targets = {args.dataset: DATASETS[args.dataset]} if args.dataset else DATASETS
    ok, fail = 0, 0

    for name, config in targets.items():
        if download_dataset(name, config, force=args.clean):
            ok += 1
        else:
            fail += 1

    print(f"\n{'=' * 60}")
    print(f"Done: {ok} OK, {fail} FAIL")

    if ok > 0:
        print("\nRun benchmarks:")
        print("  diffinite example/Case-Oracle/AOSP_Google example/Case-Oracle/OpenJDK_Oracle --strip-comments -o report.pdf")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
