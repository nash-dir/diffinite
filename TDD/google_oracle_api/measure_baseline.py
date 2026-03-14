"""Baseline measurement: compute multi-channel scores for Oracle vs Google pairs.

Outputs per-file channel scores to stdout for analysis.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import compute_channel_scores, identifier_cosine
from diffinite.differ import read_file

BASE_DIR = Path(__file__).resolve().parent.parent / "example" / "Case-Oracle"
LEFT_DIR = BASE_DIR / "OpenJDK_Oracle"
RIGHT_DIR = BASE_DIR / "AOSP_Google"

FILES = ["String.java", "Math.java", "List.java", "Collections.java", "ArrayList.java"]


def measure_pair(filename: str) -> dict:
    """Compute all channel scores for one Oracle↔Google file pair."""
    left_path = str(LEFT_DIR / filename)
    right_path = str(RIGHT_DIR / filename)

    text_a = read_file(left_path) or ""
    text_b = read_file(right_path) or ""

    if not text_a or not text_b:
        return {"error": f"Failed to read {filename}"}

    ext = ".java"
    cleaned_a = strip_comments(text_a, ext)
    cleaned_b = strip_comments(text_b, ext)

    # Raw Winnowing (no normalisation)
    fp_raw_a = {fp.hash_value for fp in extract_fingerprints(cleaned_a, normalize=False, mode="token", extension=ext)}
    fp_raw_b = {fp.hash_value for fp in extract_fingerprints(cleaned_b, normalize=False, mode="token", extension=ext)}

    # Normalised Winnowing
    fp_norm_a = {fp.hash_value for fp in extract_fingerprints(cleaned_a, normalize=True, mode="token", extension=ext)}
    fp_norm_b = {fp.hash_value for fp in extract_fingerprints(cleaned_b, normalize=True, mode="token", extension=ext)}

    # AST Winnowing
    fp_ast_a = {fp.hash_value for fp in extract_fingerprints(cleaned_a, normalize=True, mode="ast", extension=ext)}
    fp_ast_b = {fp.hash_value for fp in extract_fingerprints(cleaned_b, normalize=True, mode="ast", extension=ext)}

    scores = compute_channel_scores(
        fp_raw_a=fp_raw_a, fp_raw_b=fp_raw_b,
        fp_norm_a=fp_norm_a, fp_norm_b=fp_norm_b,
        fp_ast_a=fp_ast_a, fp_ast_b=fp_ast_b,
        source_a=text_a, source_b=text_b,
        cleaned_a=cleaned_a, cleaned_b=cleaned_b,
        extension=ext,
    )

    # Additional details
    scores["_lines_a"] = len(text_a.splitlines())
    scores["_lines_b"] = len(text_b.splitlines())
    scores["_fp_raw_a"] = len(fp_raw_a)
    scores["_fp_raw_b"] = len(fp_raw_b)
    scores["_fp_ast_a"] = len(fp_ast_a)
    scores["_fp_ast_b"] = len(fp_ast_b)

    return scores


def main():
    print("=" * 80)
    print("BASELINE MULTI-CHANNEL SCORES: Oracle (OpenJDK 7) vs Google (AOSP Froyo)")
    print("=" * 80)

    all_scores = {}
    for f in FILES:
        print(f"\n--- {f} ---")
        scores = measure_pair(f)
        all_scores[f] = scores

        if "error" in scores:
            print(f"  ERROR: {scores['error']}")
            continue

        channels = ["raw_winnowing", "normalized_winnowing", "ast_winnowing",
                     "identifier_cosine", "comment_string_overlap", "composite"]
        for ch in channels:
            if ch in scores:
                print(f"  {ch:30s} = {scores[ch]:.4f}")

        meta = ["_lines_a", "_lines_b", "_fp_raw_a", "_fp_raw_b", "_fp_ast_a", "_fp_ast_b"]
        for m in meta:
            if m in scores:
                print(f"  {m:30s} = {scores[m]}")

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY (averages across all files)")
    print("=" * 80)
    channels = ["raw_winnowing", "normalized_winnowing", "ast_winnowing",
                 "identifier_cosine", "comment_string_overlap"]
    for ch in channels:
        vals = [s[ch] for s in all_scores.values() if ch in s and "error" not in s]
        if vals:
            avg = sum(vals) / len(vals)
            print(f"  {ch:30s} avg = {avg:.4f}  (min={min(vals):.4f}, max={max(vals):.4f})")

    # SSO gap analysis
    print("\n" + "=" * 80)
    print("SSO GAP ANALYSIS (identifier_cosine - raw_winnowing)")
    print("=" * 80)
    for f, s in all_scores.items():
        if "error" in s:
            continue
        gap = s.get("identifier_cosine", 0) - s.get("raw_winnowing", 0)
        ast_gap = s.get("ast_winnowing", 0) - s.get("raw_winnowing", 0)
        print(f"  {f:25s}  id_gap = {gap:+.4f}  ast_gap = {ast_gap:+.4f}")


if __name__ == "__main__":
    main()
