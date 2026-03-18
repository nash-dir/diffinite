"""Diffinite — Forensic source-code diff tool.

Compare two source directories, track logic movement across files
(N:M cross-matching), and generate syntax-highlighted PDF reports.
"""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    __version__: str = _pkg_version("diffinite")
except PackageNotFoundError:
    # Fallback for editable installs or running from source without install
    __version__ = "0.0.0-dev"

