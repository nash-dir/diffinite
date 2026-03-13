"""File collection and fuzzy 1:1 matching.

Collects relative file paths under a directory and matches files from
two directories using ``rapidfuzz`` string similarity with a greedy
best-match strategy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from rapidfuzz import fuzz

from diffinite.models import FileMatch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FUZZY_THRESHOLD: float = 60  # minimum similarity score (0-100)


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
def collect_files(directory: str) -> list[str]:
    """Recursively collect relative file paths under *directory*.

    Args:
        directory: Root directory to scan.

    Returns:
        Sorted list of relative POSIX-style paths.
    """
    root = Path(directory).resolve()
    paths: list[str] = []
    for item in root.rglob("*"):
        if item.is_file():
            paths.append(item.relative_to(root).as_posix())
    paths.sort()
    return paths


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------
def match_files(
    files_a: list[str],
    files_b: list[str],
    threshold: float = FUZZY_THRESHOLD,
) -> Tuple[list[FileMatch], list[str], list[str]]:
    """Match files from two lists using exact + fuzzy string similarity.

    Phase 1 (exact): O(N) — match files with identical relative paths.
    Phase 2 (fuzzy): O(R²) — greedy best-match over remaining unmatched
    files, where R ≪ N in typical workloads.

    Args:
        files_a:   Relative paths from directory A.
        files_b:   Relative paths from directory B.
        threshold: Minimum similarity score (0–100) to accept a fuzzy match.

    Returns:
        Tuple of (matched pairs, unmatched_a, unmatched_b).
    """
    matches: list[FileMatch] = []

    # Phase 1: Exact match (O(N))
    set_b = set(files_b)
    exact_matched_a: set[int] = set()
    exact_matched_b: set[str] = set()

    for i, fa in enumerate(files_a):
        if fa in set_b:
            matches.append(FileMatch(fa, fa, 100.0))
            exact_matched_a.add(i)
            exact_matched_b.add(fa)

    remaining_a = [(i, fa) for i, fa in enumerate(files_a) if i not in exact_matched_a]
    remaining_b = [(j, fb) for j, fb in enumerate(files_b) if fb not in exact_matched_b]

    # Phase 2: Fuzzy match on remainder (O(R²), R = unmatched count)
    if remaining_a and remaining_b:
        candidates: list[Tuple[float, int, int]] = []
        for ri, (i, fa) in enumerate(remaining_a):
            for rj, (j, fb) in enumerate(remaining_b):
                score = fuzz.ratio(fa, fb)
                if score >= threshold:
                    candidates.append((score, ri, rj))

        candidates.sort(key=lambda x: x[0], reverse=True)

        used_ri: set[int] = set()
        used_rj: set[int] = set()
        for score, ri, rj in candidates:
            if ri in used_ri or rj in used_rj:
                continue
            _, fa = remaining_a[ri]
            _, fb = remaining_b[rj]
            matches.append(FileMatch(fa, fb, score))
            used_ri.add(ri)
            used_rj.add(rj)

        unmatched_a = [fa for ri, (_, fa) in enumerate(remaining_a) if ri not in used_ri]
        unmatched_b = [fb for rj, (_, fb) in enumerate(remaining_b) if rj not in used_rj]
    else:
        unmatched_a = [fa for _, fa in remaining_a]
        unmatched_b = [fb for _, fb in remaining_b]

    return matches, unmatched_a, unmatched_b
