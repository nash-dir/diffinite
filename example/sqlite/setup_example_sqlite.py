#!/usr/bin/env python3
"""Download and extract two SQLite amalgamation versions for diff testing.

This script sets up the TDD/left/ and TDD/right/
directories with SQLite amalgamation source files from two adjacent
releases, providing a real-world C codebase for testing diffinite's
code-comparison logic.

Safety guarantees:
    - No external packages — only stdlib (urllib, zipfile, hashlib, pathlib)
    - No subprocess / os.system calls
    - HTTPS only, sqlite.org domain only
    - Path-traversal protection on zip extraction
    - Idempotent: skips download if files already exist
    - Graceful degradation: warns on hash mismatch but does not abort

Usage:
    python TDD/setup_example_sqlite.py          # normal
    python TDD/setup_example_sqlite.py --clean   # remove & re-download
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, Request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# SQLite amalgamation versions to compare
# left  = older version (baseline)
# right = newer version (comparison target)
VERSIONS = {
    "left": {
        "label": "3.45.0",
        "year": 2024,
        "code": "3450000",
        # SHA-256 of the zip file (set to None to skip verification)
        "sha256": None,
    },
    "right": {
        "label": "3.46.0",
        "year": 2024,
        "code": "3460000",
        "sha256": None,
    },
}

# Files we expect inside each amalgamation zip
EXPECTED_FILES = ["sqlite3.c", "sqlite3.h", "sqlite3ext.h", "shell.c"]

# Base URL pattern — only sqlite.org over HTTPS
URL_TEMPLATE = "https://www.sqlite.org/{year}/sqlite-amalgamation-{code}.zip"

# Allowed domain for downloads
ALLOWED_DOMAIN = "www.sqlite.org"

# Script directory (TDD/)
SCRIPT_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> None:
    """Ensure URL uses HTTPS and targets the allowed domain only."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    if parsed.hostname != ALLOWED_DOMAIN:
        raise ValueError(
            f"Refusing URL from untrusted domain '{parsed.hostname}' "
            f"(allowed: {ALLOWED_DOMAIN})"
        )


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> list[str]:
    """Extract zip contents with path-traversal protection.

    Returns list of extracted file names (basenames only).
    """
    extracted: list[str] = []
    dest_resolved = dest.resolve()

    for info in zf.infolist():
        # Skip directories
        if info.is_dir():
            continue

        # Flatten: only extract the basename, ignore subdirectory structure
        basename = Path(info.filename).name

        # Path-traversal check
        target = (dest / basename).resolve()
        if not str(target).startswith(str(dest_resolved)):
            logger.warning("Skipping suspicious path: %s", info.filename)
            continue

        # Extract
        with zf.open(info) as src, open(target, "wb") as dst:
            dst.write(src.read())

        extracted.append(basename)
        logger.info("  Extracted: %s → %s", info.filename, target.name)

    return extracted


def _verify_sha256(filepath: Path, expected: str | None) -> bool:
    """Verify SHA-256 hash of downloaded file. Returns True if OK or skipped."""
    if expected is None:
        logger.info("  SHA-256 verification skipped (no hash configured)")
        return True

    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    actual = sha.hexdigest()

    if actual == expected:
        logger.info("  SHA-256 OK: %s", actual[:16] + "…")
        return True
    else:
        logger.warning(
            "  SHA-256 MISMATCH!\n"
            "    Expected: %s\n"
            "    Actual:   %s\n"
            "  Proceeding anyway (file may still be valid for a different sub-release).",
            expected, actual,
        )
        return False


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def download_version(side: str, config: dict, *, force: bool = False) -> bool:
    """Download and extract one SQLite amalgamation version.

    Args:
        side:   'left' or 'right'
        config: Version config dict from VERSIONS
        force:  If True, remove existing and re-download

    Returns:
        True if the target directory is ready (downloaded or already existed).
    """
    dest = SCRIPT_DIR / side
    marker_file = dest / "sqlite3.c"

    # Idempotency check
    if marker_file.exists() and not force:
        logger.info("[%s] Already exists (%s) — skipping", side, config["label"])
        return True

    # Clean if force
    if force and dest.exists():
        logger.info("[%s] Cleaning existing directory …", side)
        shutil.rmtree(dest)

    dest.mkdir(parents=True, exist_ok=True)

    url = URL_TEMPLATE.format(year=config["year"], code=config["code"])
    _validate_url(url)

    logger.info("[%s] Downloading SQLite %s …", side, config["label"])
    logger.info("  URL: %s", url)

    zip_path = dest / f"sqlite-amalgamation-{config['code']}.zip"

    try:
        req = Request(url, headers={"User-Agent": "diffinite-setup/1.0"})
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
            zip_path.write_bytes(data)

        size_mb = len(data) / (1024 * 1024)
        logger.info("  Downloaded %.1f MB", size_mb)

    except URLError as exc:
        logger.error("[%s] Download failed: %s", side, exc)
        return False

    # Verify hash
    _verify_sha256(zip_path, config.get("sha256"))

    # Extract
    logger.info("[%s] Extracting …", side)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            extracted = _safe_extract(zf, dest)
    except zipfile.BadZipFile as exc:
        logger.error("[%s] Bad zip file: %s", side, exc)
        return False

    # Clean up zip
    zip_path.unlink(missing_ok=True)

    # Verify expected files
    missing = [f for f in EXPECTED_FILES if f not in extracted]
    if missing:
        logger.warning(
            "[%s] Missing expected files: %s", side, ", ".join(missing)
        )

    logger.info("[%s] Ready ✓ (%d files)", side, len(extracted))
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download SQLite amalgamation example data for diffinite testing.",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove existing downloads and re-download",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Diffinite — SQLite Amalgamation Example Setup")
    logger.info("=" * 60)

    ok = True
    for side, config in VERSIONS.items():
        if not download_version(side, config, force=args.clean):
            ok = False

    if ok:
        logger.info("")
        logger.info("Setup complete ✓")
        logger.info("  left/  → SQLite %s", VERSIONS["left"]["label"])
        logger.info("  right/ → SQLite %s", VERSIONS["right"]["label"])
        logger.info("")
        logger.info("Usage:")
        logger.info("  diffinite TDD/left TDD/right -o sqlite_diff.pdf")
        return 0
    else:
        logger.error("Setup failed — check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())