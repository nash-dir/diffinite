"""Data models for Diffinite.

Centralised dataclasses used across the package — file matching,
diff results, deep-compare results, and comment specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Comment specification
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CommentSpec:
    """Language-specific comment marker specification.

    Attributes:
        line_markers:  Strings that start a single-line comment (e.g. ``//``, ``#``).
        block_start:   String that opens a block comment (e.g. ``/*``), or *None*.
        block_end:     String that closes a block comment (e.g. ``*/``), or *None*.
    """

    line_markers: tuple[str, ...] = ()
    block_start: Optional[str] = None
    block_end: Optional[str] = None


# ---------------------------------------------------------------------------
# File matching
# ---------------------------------------------------------------------------
@dataclass
class FileMatch:
    """A matched pair of files from dir_a and dir_b."""

    rel_path_a: str
    rel_path_b: str
    similarity: float  # 0–100


# ---------------------------------------------------------------------------
# Diff result
# ---------------------------------------------------------------------------
@dataclass
class DiffResult:
    """Quantitative + visual diff result for one file pair."""

    match: FileMatch
    ratio: float  # 0.0 – 1.0
    additions: int
    deletions: int
    html_diff: str  # side-by-side HTML table
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Fingerprint / Deep Compare
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FingerprintEntry:
    """A single fingerprint extracted via Winnowing.

    Attributes:
        hash_value: The rolling-hash value selected by winnowing.
        position:   Token-level offset in the source where this fingerprint begins.
    """

    hash_value: int
    position: int


@dataclass
class DeepMatchResult:
    """N:M cross-match result between file sets.

    Attributes:
        file_a:          Relative path from directory A.
        matched_files_b: List of ``(rel_path_b, shared_hash_count, jaccard)`` tuples.
        fingerprint_count_a: Total fingerprints in file A.
        channel_scores:  Per-B-file multi-evidence channel scores.
                         Key = rel_path_b, value = dict of channel → score.
    """

    file_a: str
    matched_files_b: list[tuple[str, int, float]] = field(default_factory=list)
    fingerprint_count_a: int = 0
    channel_scores: dict[str, dict[str, float]] = field(default_factory=dict)
