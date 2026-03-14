"""Weight calibration grid search.

Searches over channel weight ratios and thresholds to find the optimal
configuration for academic-scale code plagiarism detection.

The key insight from the K/W grid search is that no K/W/threshold combo
alone achieves FPR ≤ 0.10 — the channel weights are the primary lever
for separating plagiarized from independent academic code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from itertools import product
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import (
    compute_channel_scores,
    _jaccard_from_sets,
    identifier_cosine,
    comment_string_overlap,
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


def extract_all_channels(text: str, k: int, w: int) -> dict:
    """Extract all channel data for a single file."""
    cleaned = strip_comments(text, ".java")
    fp_raw = extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=".java")
    fp_norm = extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=".java")
    return {
        "raw": {fp.hash_value for fp in fp_raw},
        "normalized": {fp.hash_value for fp in fp_norm},
        "text": text,
        "cleaned": cleaned,
    }


def compute_scores_with_weights(ch_a: dict, ch_b: dict, weights: dict[str, float]) -> float:
    """Compute composite score with custom weights."""
    scores = {}

    # Winnowing channels
    scores["raw_winnowing"] = _jaccard_from_sets(ch_a["raw"], ch_b["raw"])
    scores["normalized_winnowing"] = _jaccard_from_sets(ch_a["normalized"], ch_b["normalized"])

    # Identifier cosine
    scores["identifier_cosine"] = identifier_cosine(ch_a["cleaned"], ch_b["cleaned"])

    # Comment/string overlap
    scores["comment_string_overlap"] = comment_string_overlap(
        ch_a["text"], ch_b["text"], ".java"
    )

    # Weighted composite
    total_weight = 0.0
    weighted_sum = 0.0
    for channel, score in scores.items():
        w = weights.get(channel, 0.0)
        weighted_sum += score * w
        total_weight += w

    return weighted_sum / total_weight if total_weight > 0 else 0.0


def collect_channel_data(k: int, w: int):
    """Pre-compute all channel data for the entire dataset."""
    all_pairs = []  # list of (label, composite_func_args)

    for case_name in CASES:
        case_dir = DATASET_ROOT / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = read_java(orig_files[0])
        if not orig_text:
            continue
        orig_ch = extract_all_channels(orig_text, k, w)

        # Plagiarized
        for level in LEVELS:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = read_java(jf)
                if text:
                    ch = extract_all_channels(text, k, w)
                    all_pairs.append(("pos", level, orig_ch, ch))

        # Non-plagiarized
        non_plag_dir = case_dir / "non-plagiarized"
        for jf in sorted(non_plag_dir.rglob("*.java")):
            text = read_java(jf)
            if text:
                ch = extract_all_channels(text, k, w)
                all_pairs.append(("neg", "N/A", orig_ch, ch))

    return all_pairs


def evaluate(all_pairs, weights, threshold):
    """Evaluate metrics for a given weight/threshold configuration."""
    level_counts = defaultdict(lambda: {"tp": 0, "fn": 0})
    fp = 0
    tn = 0

    for label, level, ch_a, ch_b in all_pairs:
        score = compute_scores_with_weights(ch_a, ch_b, weights)
        if label == "pos":
            if score >= threshold:
                level_counts[level]["tp"] += 1
            else:
                level_counts[level]["fn"] += 1
        else:
            if score >= threshold:
                fp += 1
            else:
                tn += 1

    total_tp = sum(v["tp"] for v in level_counts.values())
    total_fn = sum(v["fn"] for v in level_counts.values())
    total_neg = fp + tn

    precision = total_tp / (total_tp + fp) if (total_tp + fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / total_neg if total_neg > 0 else 0.0

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
    # Use K=2, W=3 as the best K/W from the previous grid search
    K, W = 2, 3
    print(f"Pre-computing channel data (K={K}, W={W})...")
    all_pairs = collect_channel_data(K, W)
    print(f"  {len(all_pairs)} pairs loaded")

    # Weight configurations to test
    # Format: {channel: weight}
    weight_configs = [
        # Baseline (current defaults)
        {"name": "default", "raw_winnowing": 1.0, "normalized_winnowing": 2.0,
         "identifier_cosine": 1.5, "comment_string_overlap": 1.0},
        # Winnowing-only: removes noisy channels for short code
        {"name": "winnow_only", "raw_winnowing": 1.0, "normalized_winnowing": 2.0,
         "identifier_cosine": 0.0, "comment_string_overlap": 0.0},
        # Normalized-heavy: focuses on structure
        {"name": "norm_heavy", "raw_winnowing": 0.5, "normalized_winnowing": 3.0,
         "identifier_cosine": 0.5, "comment_string_overlap": 0.0},
        # Pure normalized
        {"name": "pure_norm", "raw_winnowing": 0.0, "normalized_winnowing": 1.0,
         "identifier_cosine": 0.0, "comment_string_overlap": 0.0},
        # Pure raw
        {"name": "pure_raw", "raw_winnowing": 1.0, "normalized_winnowing": 0.0,
         "identifier_cosine": 0.0, "comment_string_overlap": 0.0},
        # Balanced winnowing
        {"name": "balanced_winnow", "raw_winnowing": 1.0, "normalized_winnowing": 1.0,
         "identifier_cosine": 0.0, "comment_string_overlap": 0.0},
        # Raw + light norm
        {"name": "raw_light_norm", "raw_winnowing": 2.0, "normalized_winnowing": 1.0,
         "identifier_cosine": 0.0, "comment_string_overlap": 0.0},
        # Include identifier but no comments
        {"name": "winnow_id", "raw_winnowing": 1.0, "normalized_winnowing": 2.0,
         "identifier_cosine": 1.0, "comment_string_overlap": 0.0},
        # Norm + light identifier
        {"name": "norm_light_id", "raw_winnowing": 0.5, "normalized_winnowing": 3.0,
         "identifier_cosine": 0.3, "comment_string_overlap": 0.0},
        # Heavy raw, light normalized
        {"name": "heavy_raw", "raw_winnowing": 3.0, "normalized_winnowing": 1.0,
         "identifier_cosine": 0.0, "comment_string_overlap": 0.0},
        # All channels but comment-light
        {"name": "full_light_comment", "raw_winnowing": 1.0, "normalized_winnowing": 2.0,
         "identifier_cosine": 1.5, "comment_string_overlap": 0.3},
        # Pure raw with tiny identifier
        {"name": "raw_tiny_id", "raw_winnowing": 3.0, "normalized_winnowing": 0.5,
         "identifier_cosine": 0.2, "comment_string_overlap": 0.0},
    ]

    THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]

    best_f1 = 0.0
    best_config = {}
    best_constrained = None  # FPR ≤ 0.10

    for wc in weight_configs:
        name = wc["name"]
        weights = {k: v for k, v in wc.items() if k != "name"}
        print(f"\n--- {name} ---")

        for threshold in THRESHOLDS:
            metrics = evaluate(all_pairs, weights, threshold)
            f1 = metrics["f1"]
            fpr = metrics["fpr"]

            if f1 > best_f1:
                best_f1 = f1
                best_config = {"name": name, "threshold": threshold, **metrics, "weights": weights}

            if fpr <= 0.10 and (best_constrained is None or f1 > best_constrained["f1"]):
                best_constrained = {"name": name, "threshold": threshold, **metrics, "weights": weights}

            # Only print notable results
            if f1 > 0.85 or fpr < 0.15:
                print(
                    f"  T={threshold:.2f}: F1={f1:.4f} P={metrics['precision']:.4f} "
                    f"R={metrics['recall']:.4f} FPR={fpr:.4f}"
                )

    print(f"\n{'='*70}")
    print(f" BEST OVERALL F1")
    print(f"{'='*70}")
    print(f"  Config: {best_config['name']}")
    print(f"  Weights: {best_config['weights']}")
    print(f"  Threshold: {best_config['threshold']:.2f}")
    print(f"  F1={best_config['f1']:.4f} P={best_config['precision']:.4f} R={best_config['recall']:.4f} FPR={best_config['fpr']:.4f}")
    for level in LEVELS:
        print(f"    {level}: TPR={best_config['level_tpr'].get(level, 0.0):.4f}")

    if best_constrained:
        print(f"\n{'='*70}")
        print(f" BEST WITH FPR ≤ 0.10")
        print(f"{'='*70}")
        print(f"  Config: {best_constrained['name']}")
        print(f"  Weights: {best_constrained['weights']}")
        print(f"  Threshold: {best_constrained['threshold']:.2f}")
        print(f"  F1={best_constrained['f1']:.4f} P={best_constrained['precision']:.4f} R={best_constrained['recall']:.4f} FPR={best_constrained['fpr']:.4f}")
        for level in LEVELS:
            print(f"    {level}: TPR={best_constrained['level_tpr'].get(level, 0.0):.4f}")
    else:
        print("\n  No configuration achieves FPR ≤ 0.10")


if __name__ == "__main__":
    main()
