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
            # AOSP (Android 4.4 KitKat — the version at issue in the case)
            **{f"AOSP_Google/{f}": f"https://raw.githubusercontent.com/aosp-mirror/platform_libcore/kitkat-release/luni/src/main/java/java/{p}"
               for f, p in [
                   ("ArrayList.java", "util/ArrayList.java"),
                   ("Collections.java", "util/Collections.java"),
                   ("List.java", "util/List.java"),
                   ("Math.java", "lang/Math.java"),
                   ("String.java", "lang/String.java"),
               ]},
            # OpenJDK 7 b147
            **{f"OpenJDK_Oracle/{f}": f"https://raw.githubusercontent.com/openjdk/jdk/jdk7-b147/jdk/src/share/classes/java/{p}"
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
            **{f"Eclipse_Collections/{f}": f"https://raw.githubusercontent.com/eclipse/eclipse-collections/master/eclipse-collections/src/main/java/org/eclipse/collections/impl/{p}"
               for f, p in [
                   ("FastList.java", "list/mutable/FastList.java"),
                   ("UnifiedSet.java", "set/mutable/UnifiedSet.java"),
                   ("UnifiedMap.java", "map/mutable/UnifiedMap.java"),
                   ("Iterate.java", "utility/Iterate.java"),
                   ("StringIterate.java", "utility/StringIterate.java"),
               ]},
            # OpenJDK 7
            **{f"OpenJDK/{f}": f"https://raw.githubusercontent.com/openjdk/jdk/jdk7-b147/jdk/src/share/classes/java/{p}"
               for f, p in [
                   ("ArrayList.java", "util/ArrayList.java"),
                   ("HashSet.java", "util/HashSet.java"),
                   ("HashMap.java", "util/HashMap.java"),
                   ("Collections.java", "util/Collections.java"),
                   ("String.java", "lang/String.java"),
               ]},
        },
    },

    # 4. IR-Plag plagiarism dataset (case-01)
    "plagiarism": {
        "description": "IR-Plag dataset case-01 (labeled plagiarism levels L1-L6)",
        "zip": "https://github.com/oscarkarnalim/sourcecodeplagiarismdataset/archive/refs/heads/master.zip",
        "zip_subdir": "sourcecodeplagiarismdataset-master/IR-Plag-Dataset/case-01",
    },

    # 5. SQLite amalgamation (two adjacent versions)
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

def _download_file(url: str, dest: Path) -> bool:
    """Download a single file."""
    try:
        print(f"  ↓ {dest.name:35s} ", end="", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Diffinite/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"OK ({len(data):,} bytes)")
        return True
    except Exception as exc:
        print(f"FAIL ({exc})")
        return False


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


def download_dataset(name: str, config: dict, *, force: bool = False) -> bool:
    """Download a single dataset."""
    dest = EXAMPLE_DIR / name

    # Check if already exists
    if dest.exists() and any(dest.rglob("*.java") if name != "sqlite" else dest.rglob("*.c")) and not force:
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

    # Case 2: Single zip with subdir extraction
    if "zip" in config:
        dest.mkdir(parents=True, exist_ok=True)
        zip_path = dest / "_download.zip"
        if not _download_file(config["zip"], zip_path):
            return False
        subdir = config.get("zip_subdir", "")
        count = _safe_extract_zip(zip_path, dest, subdir)
        zip_path.unlink(missing_ok=True)
        print(f"  Extracted {count} files")
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
        print(f"\nRun benchmarks:")
        print(f"  diffinite example/Case-Oracle/AOSP_Google example/Case-Oracle/OpenJDK_Oracle --no-comments -o report.pdf")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
