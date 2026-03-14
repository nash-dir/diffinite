"""Baseline measurement script for IR-Plag-Dataset.

Measures Diffinite's multi-channel detection performance across all
7 cases and 6 Faidhi-Robinson plagiarism levels (L1–L6).

Outputs per-case, per-level TPR/FPR/F1 and aggregate metrics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

# Ensure diffinite package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints, DEFAULT_K, DEFAULT_W
from diffinite.parser import strip_comments
from diffinite.evidence import compute_channel_scores

DATASET_ROOT = PROJECT_ROOT / "example" / "plagiarism"
CASES = sorted(p.name for p in DATASET_ROOT.iterdir() if p.is_dir())
LEVELS = [f"L{i}" for i in range(1, 7)]


def read_java_file(path: Path) -> str | None:
    """Read a Java file with encoding fallback."""
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def fingerprint_file(text: str, k: int, w: int) -> dict:
    """Extract multi-channel fingerprints for a single source text."""
    cleaned = strip_comments(text, ".java")

    # Raw
    fps_raw = extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=".java")
    raw_set = {fp.hash_value for fp in fps_raw}

    # Normalized
    fps_norm = extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=".java")
    norm_set = {fp.hash_value for fp in fps_norm}

    return {
        "raw": raw_set,
        "normalized": norm_set,
        "text": text,
        "cleaned": cleaned,
    }


def compute_similarity(fp_a: dict, fp_b: dict) -> dict[str, float]:
    """Compute multi-channel similarity scores between two fingerprinted files."""
    scores = compute_channel_scores(
        fp_raw_a=fp_a["raw"],
        fp_raw_b=fp_b["raw"],
        fp_norm_a=fp_a["normalized"],
        fp_norm_b=fp_b["normalized"],
        source_a=fp_a["text"],
        source_b=fp_b["text"],
        cleaned_a=fp_a["cleaned"],
        cleaned_b=fp_b["cleaned"],
        extension=".java",
    )
    return scores


def find_java_files(directory: Path) -> list[Path]:
    """Find all .java files in a directory tree."""
    if not directory.exists():
        return []
    return sorted(directory.rglob("*.java"))


def measure_case(case_dir: Path, k: int, w: int, threshold: float) -> dict:
    """Measure TPR/FPR for a single case directory."""
    original_dir = case_dir / "original"
    plagiarized_dir = case_dir / "plagiarized"
    non_plagiarized_dir = case_dir / "non-plagiarized"

    # Load and fingerprint original
    orig_files = find_java_files(original_dir)
    if not orig_files:
        return {}

    orig_fps = {}
    for f in orig_files:
        text = read_java_file(f)
        if text:
            orig_fps[f.name] = fingerprint_file(text, k, w)

    if not orig_fps:
        return {}

    # For each original file, use the first (typically only one)
    orig_name = list(orig_fps.keys())[0]
    orig_fp = orig_fps[orig_name]

    results = {"case": case_dir.name, "levels": {}}

    # Measure per-level TPR (true positive rate)
    for level in LEVELS:
        level_dir = plagiarized_dir / level
        if not level_dir.exists():
            continue

        plag_files = find_java_files(level_dir)
        tp = 0
        fn = 0
        scores_list = []

        for pf in plag_files:
            text = read_java_file(pf)
            if text is None:
                continue
            plag_fp = fingerprint_file(text, k, w)
            scores = compute_similarity(orig_fp, plag_fp)
            composite = scores.get("composite", 0.0)
            scores_list.append(composite)
            if composite >= threshold:
                tp += 1
            else:
                fn += 1

        total = tp + fn
        tpr = tp / total if total > 0 else 0.0
        avg_score = sum(scores_list) / len(scores_list) if scores_list else 0.0
        results["levels"][level] = {
            "tpr": round(tpr, 4),
            "tp": tp,
            "fn": fn,
            "total": total,
            "avg_composite": round(avg_score, 4),
        }

    # Measure FPR (false positive rate) against non-plagiarized
    non_plag_files = find_java_files(non_plagiarized_dir)
    fp_count = 0
    tn_count = 0
    non_plag_scores = []

    for npf in non_plag_files:
        text = read_java_file(npf)
        if text is None:
            continue
        npf_fp = fingerprint_file(text, k, w)
        scores = compute_similarity(orig_fp, npf_fp)
        composite = scores.get("composite", 0.0)
        non_plag_scores.append(composite)
        if composite >= threshold:
            fp_count += 1
        else:
            tn_count += 1

    total_neg = fp_count + tn_count
    fpr = fp_count / total_neg if total_neg > 0 else 0.0
    avg_neg_score = sum(non_plag_scores) / len(non_plag_scores) if non_plag_scores else 0.0

    results["fpr"] = round(fpr, 4)
    results["fp"] = fp_count
    results["tn"] = tn_count
    results["total_neg"] = total_neg
    results["avg_neg_composite"] = round(avg_neg_score, 4)

    return results


def compute_f1(all_results: list[dict], threshold: float) -> dict:
    """Compute aggregate F1-Score from all case results."""
    total_tp = 0
    total_fn = 0
    total_fp = 0
    total_tn = 0

    for r in all_results:
        for level_data in r.get("levels", {}).values():
            total_tp += level_data["tp"]
            total_fn += level_data["fn"]
        total_fp += r.get("fp", 0)
        total_tn += r.get("tn", 0)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "total_tp": total_tp,
        "total_fn": total_fn,
        "total_fp": total_fp,
        "total_tn": total_tn,
    }


def run_baseline(k: int = DEFAULT_K, w: int = DEFAULT_W, threshold: float = 0.10):
    """Run full baseline measurement."""
    print(f"\n{'='*70}")
    print(f" Diffinite Baseline Measurement")
    print(f" K={k}, W={w}, threshold={threshold}")
    print(f"{'='*70}\n")

    all_results = []
    per_level_agg = defaultdict(lambda: {"tp": 0, "fn": 0, "total": 0, "scores": []})

    for case_name in CASES:
        case_dir = DATASET_ROOT / case_name
        print(f"Processing {case_name}...")
        result = measure_case(case_dir, k, w, threshold)
        if result:
            all_results.append(result)
            for level, data in result.get("levels", {}).items():
                agg = per_level_agg[level]
                agg["tp"] += data["tp"]
                agg["fn"] += data["fn"]
                agg["total"] += data["total"]
                agg["scores"].append(data["avg_composite"])

    # Print per-case results
    print(f"\n{'='*70}")
    print(f" Per-Case Results")
    print(f"{'='*70}")
    print(f"{'Case':<10} {'FPR':<8} {'Avg Neg':<10} | ", end="")
    for L in LEVELS:
        print(f"{L} TPR  ", end="")
    print()
    print("-" * 80)

    for r in all_results:
        print(f"{r['case']:<10} {r['fpr']:<8.4f} {r['avg_neg_composite']:<10.4f} | ", end="")
        for L in LEVELS:
            d = r["levels"].get(L, {})
            tpr = d.get("tpr", 0.0)
            print(f"{tpr:.4f}  ", end="")
        print()

    # Per-level aggregate
    print(f"\n{'='*70}")
    print(f" Per-Level Aggregate TPR")
    print(f"{'='*70}")
    for level in LEVELS:
        agg = per_level_agg[level]
        tpr = agg["tp"] / agg["total"] if agg["total"] > 0 else 0.0
        avg = sum(agg["scores"]) / len(agg["scores"]) if agg["scores"] else 0.0
        print(f"  {level}: TPR={tpr:.4f}  ({agg['tp']}/{agg['total']})  avg_composite={avg:.4f}")

    # Overall metrics
    metrics = compute_f1(all_results, threshold)
    print(f"\n{'='*70}")
    print(f" Overall Metrics")
    print(f"{'='*70}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1-Score:  {metrics['f1']:.4f}")
    print(f"  TP={metrics['total_tp']} FN={metrics['total_fn']} FP={metrics['total_fp']} TN={metrics['total_tn']}")

    return all_results, metrics, per_level_agg


if __name__ == "__main__":
    all_results, metrics, per_level_agg = run_baseline()
