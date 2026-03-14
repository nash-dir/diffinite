"""Tuned baseline measurement with academic profile parameters.

Uses the optimised academic parameters found via grid search:
  K=2, W=3, threshold=0.45
  Weights: raw_winnowing=3.0, normalized_winnowing=1.0, id/cs=0.0
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import (
    compute_channel_scores,
    get_weights_for_profile,
    _DEFAULT_WEIGHTS,
    _ACADEMIC_WEIGHTS,
)

DATASET_ROOT = PROJECT_ROOT / "example" / "plagiarism"
CASES = sorted(p.name for p in DATASET_ROOT.iterdir() if p.is_dir())
LEVELS = [f"L{i}" for i in range(1, 7)]


def read_java(path: Path) -> str | None:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def fingerprint_file(text: str, k: int, w: int) -> dict:
    cleaned = strip_comments(text, ".java")
    fps_raw = extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=".java")
    fps_norm = extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=".java")
    return {
        "raw": {fp.hash_value for fp in fps_raw},
        "normalized": {fp.hash_value for fp in fps_norm},
        "text": text,
        "cleaned": cleaned,
    }


def compute_similarity(fp_a: dict, fp_b: dict, weights: dict) -> float:
    scores = compute_channel_scores(
        fp_raw_a=fp_a["raw"], fp_raw_b=fp_b["raw"],
        fp_norm_a=fp_a["normalized"], fp_norm_b=fp_b["normalized"],
        source_a=fp_a["text"], source_b=fp_b["text"],
        cleaned_a=fp_a["cleaned"], cleaned_b=fp_b["cleaned"],
        extension=".java",
        weights=weights,
    )
    return scores.get("composite", 0.0)


def run_measurement(label: str, k: int, w: int, threshold: float, weights: dict):
    print(f"\n{'='*70}")
    print(f" {label}")
    print(f" K={k}, W={w}, threshold={threshold}")
    print(f" Weights: {weights}")
    print(f"{'='*70}\n")

    per_level = defaultdict(lambda: {"tp": 0, "fn": 0, "scores": []})
    total_fp = 0
    total_tn = 0
    neg_scores = []

    for case_name in CASES:
        case_dir = DATASET_ROOT / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = read_java(orig_files[0])
        if not orig_text:
            continue
        orig_fp = fingerprint_file(orig_text, k, w)

        # Plagiarized
        for level in LEVELS:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = read_java(jf)
                if text:
                    score = compute_similarity(orig_fp, fingerprint_file(text, k, w), weights)
                    per_level[level]["scores"].append(score)
                    if score >= threshold:
                        per_level[level]["tp"] += 1
                    else:
                        per_level[level]["fn"] += 1

        # Non-plagiarized
        non_plag_dir = case_dir / "non-plagiarized"
        for jf in sorted(non_plag_dir.rglob("*.java")):
            text = read_java(jf)
            if text:
                score = compute_similarity(orig_fp, fingerprint_file(text, k, w), weights)
                neg_scores.append(score)
                if score >= threshold:
                    total_fp += 1
                else:
                    total_tn += 1

    # Results
    total_tp = sum(v["tp"] for v in per_level.values())
    total_fn = sum(v["fn"] for v in per_level.values())
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = total_fp / (total_fp + total_tn) if (total_fp + total_tn) > 0 else 0.0

    print(f"Per-Level TPR:")
    for level in LEVELS:
        d = per_level[level]
        total = d["tp"] + d["fn"]
        tpr = d["tp"] / total if total > 0 else 0.0
        avg = sum(d["scores"]) / len(d["scores"]) if d["scores"] else 0.0
        print(f"  {level}: TPR={tpr:.4f}  ({d['tp']}/{total})  avg_score={avg:.4f}")

    print(f"\nAggregate:")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  F1-Score:  {f1:.4f}")
    print(f"  FPR:       {fpr:.4f}")
    print(f"  TP={total_tp} FN={total_fn} FP={total_fp} TN={total_tn}")

    avg_neg = sum(neg_scores) / len(neg_scores) if neg_scores else 0.0
    print(f"  Avg neg score: {avg_neg:.4f}")

    return {
        "f1": f1, "precision": precision, "recall": recall,
        "fpr": fpr, "tp": total_tp, "fn": total_fn, "fp": total_fp, "tn": total_tn,
        "per_level": {l: {"tpr": v["tp"]/(v["tp"]+v["fn"]) if (v["tp"]+v["fn"])>0 else 0,
                          "avg": sum(v["scores"])/len(v["scores"]) if v["scores"] else 0}
                      for l, v in per_level.items()},
    }


if __name__ == "__main__":
    # Baseline: default parameters
    baseline = run_measurement(
        "BASELINE (Industrial Defaults)",
        k=5, w=4, threshold=0.10,
        weights=_DEFAULT_WEIGHTS,
    )

    # Tuned: academic profile
    tuned = run_measurement(
        "TUNED (Academic Profile)",
        k=2, w=3, threshold=0.45,
        weights=_ACADEMIC_WEIGHTS,
    )

    # Summary comparison
    print(f"\n{'='*70}")
    print(f" COMPARISON")
    print(f"{'='*70}")
    print(f"{'Metric':<20} {'Baseline':<12} {'Tuned':<12} {'Delta':<12}")
    print("-" * 56)
    for m in ["f1", "precision", "recall", "fpr"]:
        b, t = baseline[m], tuned[m]
        d = t - b
        print(f"  {m:<18} {b:<12.4f} {t:<12.4f} {d:+.4f}")
    print(f"\n  Per-Level TPR:")
    for level in LEVELS:
        b = baseline["per_level"].get(level, {}).get("tpr", 0)
        t = tuned["per_level"].get(level, {}).get("tpr", 0)
        d = t - b
        print(f"    {level}: {b:.4f} → {t:.4f}  ({d:+.4f})")
