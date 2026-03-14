"""Grid search for optimal academic profile parameters.

Searches over K-gram size, Winnowing window, and decision threshold
to maximize F1-Score on the IR-Plag-Dataset.
"""

from __future__ import annotations

import sys
from pathlib import Path
from itertools import product

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import compute_channel_scores

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


def fingerprint(text: str, k: int, w: int) -> dict:
    cleaned = strip_comments(text, ".java")
    fp_raw = extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=".java")
    fp_norm = extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=".java")
    return {
        "raw": {fp.hash_value for fp in fp_raw},
        "normalized": {fp.hash_value for fp in fp_norm},
        "text": text,
        "cleaned": cleaned,
    }


def similarity(fp_a: dict, fp_b: dict) -> float:
    scores = compute_channel_scores(
        fp_raw_a=fp_a["raw"], fp_raw_b=fp_b["raw"],
        fp_norm_a=fp_a["normalized"], fp_norm_b=fp_b["normalized"],
        source_a=fp_a["text"], source_b=fp_b["text"],
        cleaned_a=fp_a["cleaned"], cleaned_b=fp_b["cleaned"],
        extension=".java",
    )
    return scores.get("composite", 0.0)


def collect_all_scores(k: int, w: int):
    """Collect all positive/negative composite scores for given K, W."""
    pos_scores = []  # list of (level, score)
    neg_scores = []

    for case_name in CASES:
        case_dir = DATASET_ROOT / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = read_java(orig_files[0])
        if not orig_text:
            continue
        orig_fp = fingerprint(orig_text, k, w)

        for level in LEVELS:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = read_java(jf)
                if text:
                    score = similarity(orig_fp, fingerprint(text, k, w))
                    pos_scores.append((level, score))

        non_plag_dir = case_dir / "non-plagiarized"
        for jf in sorted(non_plag_dir.rglob("*.java")):
            text = read_java(jf)
            if text:
                score = similarity(orig_fp, fingerprint(text, k, w))
                neg_scores.append(score)

    return pos_scores, neg_scores


def evaluate(pos_scores, neg_scores, threshold):
    """Compute F1, precision, recall, FPR, per-level TPR."""
    from collections import defaultdict
    level_counts = defaultdict(lambda: {"tp": 0, "fn": 0})
    for level, score in pos_scores:
        if score >= threshold:
            level_counts[level]["tp"] += 1
        else:
            level_counts[level]["fn"] += 1

    total_tp = sum(v["tp"] for v in level_counts.values())
    total_fn = sum(v["fn"] for v in level_counts.values())
    fp = sum(1 for s in neg_scores if s >= threshold)
    tn = len(neg_scores) - fp

    precision = total_tp / (total_tp + fp) if (total_tp + fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / len(neg_scores) if neg_scores else 0.0

    level_tpr = {}
    for level in LEVELS:
        c = level_counts.get(level, {"tp": 0, "fn": 0})
        total = c["tp"] + c["fn"]
        level_tpr[level] = c["tp"] / total if total > 0 else 0.0

    return {
        "f1": f1, "precision": precision, "recall": recall,
        "fpr": fpr, "tp": total_tp, "fn": total_fn, "fp": fp, "tn": tn,
        "level_tpr": level_tpr,
    }


def main():
    K_VALUES = [2, 3, 4, 5]
    W_VALUES = [2, 3, 4]
    THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

    best_f1 = 0.0
    best_params = {}
    all_results = []

    for k, w in product(K_VALUES, W_VALUES):
        print(f"\nCollecting scores for K={k}, W={w}...")
        pos_scores, neg_scores = collect_all_scores(k, w)

        for threshold in THRESHOLDS:
            metrics = evaluate(pos_scores, neg_scores, threshold)
            result = {"k": k, "w": w, "threshold": threshold, **metrics}
            all_results.append(result)

            if metrics["f1"] > best_f1:
                best_f1 = metrics["f1"]
                best_params = result

            print(
                f"  T={threshold:.2f}: F1={metrics['f1']:.4f} "
                f"P={metrics['precision']:.4f} R={metrics['recall']:.4f} "
                f"FPR={metrics['fpr']:.4f} "
                f"TP={metrics['tp']} FN={metrics['fn']} FP={metrics['fp']}"
            )

    print(f"\n{'='*70}")
    print(f" BEST RESULT")
    print(f"{'='*70}")
    print(f"  K={best_params['k']}, W={best_params['w']}, threshold={best_params['threshold']:.2f}")
    print(f"  F1={best_params['f1']:.4f}")
    print(f"  Precision={best_params['precision']:.4f}")
    print(f"  Recall={best_params['recall']:.4f}")
    print(f"  FPR={best_params['fpr']:.4f}")
    print(f"  Per-level TPR:")
    for level in LEVELS:
        tpr = best_params["level_tpr"].get(level, 0.0)
        print(f"    {level}: {tpr:.4f}")

    # Also find best results with FPR ≤ 0.10 constraint
    constrained = [r for r in all_results if r["fpr"] <= 0.10]
    if constrained:
        best_constrained = max(constrained, key=lambda r: r["f1"])
        print(f"\n{'='*70}")
        print(f" BEST RESULT (FPR ≤ 0.10)")
        print(f"{'='*70}")
        print(f"  K={best_constrained['k']}, W={best_constrained['w']}, threshold={best_constrained['threshold']:.2f}")
        print(f"  F1={best_constrained['f1']:.4f}")
        print(f"  Precision={best_constrained['precision']:.4f}")
        print(f"  Recall={best_constrained['recall']:.4f}")
        print(f"  FPR={best_constrained['fpr']:.4f}")
        print(f"  Per-level TPR:")
        for level in LEVELS:
            tpr = best_constrained["level_tpr"].get(level, 0.0)
            print(f"    {level}: {tpr:.4f}")
    else:
        print("\n  No configuration achieves FPR ≤ 0.10")


if __name__ == "__main__":
    main()
