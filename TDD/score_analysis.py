"""Score distribution analysis for finding discriminative strategy.

Prints per-channel score distributions for plagiarized vs non-plagiarized
pairs to identify which channels are most discriminative.
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


def extract_channels(text: str, k: int, w: int) -> dict:
    cleaned = strip_comments(text, ".java")
    fp_raw = extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=".java")
    fp_norm = extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=".java")
    return {
        "raw": {fp.hash_value for fp in fp_raw},
        "normalized": {fp.hash_value for fp in fp_norm},
        "text": text,
        "cleaned": cleaned,
    }


def main():
    K, W = 2, 3

    pos_channels = defaultdict(list)  # {channel: [scores]}
    neg_channels = defaultdict(list)
    pos_by_level = defaultdict(lambda: defaultdict(list))

    for case_name in CASES:
        case_dir = DATASET_ROOT / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = read_java(orig_files[0])
        if not orig_text:
            continue
        orig_ch = extract_channels(orig_text, K, W)

        # Plagiarized
        for level in LEVELS:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = read_java(jf)
                if text:
                    ch = extract_channels(text, K, W)
                    raw_j = _jaccard_from_sets(orig_ch["raw"], ch["raw"])
                    norm_j = _jaccard_from_sets(orig_ch["normalized"], ch["normalized"])
                    id_cos = identifier_cosine(orig_ch["cleaned"], ch["cleaned"])
                    cs_ovl = comment_string_overlap(orig_ch["text"], ch["text"], ".java")
                    for name, val in [("raw", raw_j), ("norm", norm_j), ("id_cos", id_cos), ("cs_ovl", cs_ovl)]:
                        pos_channels[name].append(val)
                        pos_by_level[level][name].append(val)

        # Non-plagiarized
        non_plag_dir = case_dir / "non-plagiarized"
        for jf in sorted(non_plag_dir.rglob("*.java")):
            text = read_java(jf)
            if text:
                ch = extract_channels(text, K, W)
                raw_j = _jaccard_from_sets(orig_ch["raw"], ch["raw"])
                norm_j = _jaccard_from_sets(orig_ch["normalized"], ch["normalized"])
                id_cos = identifier_cosine(orig_ch["cleaned"], ch["cleaned"])
                cs_ovl = comment_string_overlap(orig_ch["text"], ch["text"], ".java")
                for name, val in [("raw", raw_j), ("norm", norm_j), ("id_cos", id_cos), ("cs_ovl", cs_ovl)]:
                    neg_channels[name].append(val)

    # Print statistics
    print(f"{'='*80}")
    print(f" Per-Channel Score Distribution (K={K}, W={W})")
    print(f"{'='*80}")

    for ch_name in ["raw", "norm", "id_cos", "cs_ovl"]:
        pos = sorted(pos_channels[ch_name])
        neg = sorted(neg_channels[ch_name])
        print(f"\n--- {ch_name} ---")
        print(f"  Plagiarized  (N={len(pos)}): min={min(pos):.4f}  p25={pos[len(pos)//4]:.4f}  median={pos[len(pos)//2]:.4f}  p75={pos[3*len(pos)//4]:.4f}  max={max(pos):.4f}  mean={sum(pos)/len(pos):.4f}")
        print(f"  Non-plag     (N={len(neg)}): min={min(neg):.4f}  p25={neg[len(neg)//4]:.4f}  median={neg[len(neg)//2]:.4f}  p75={neg[3*len(neg)//4]:.4f}  max={max(neg):.4f}  mean={sum(neg)/len(neg):.4f}")

        # Find threshold where FPR ≤ 0.10
        # Sort neg scores descending to find 90th percentile
        neg_sorted = sorted(neg, reverse=True)
        p90_neg = neg_sorted[int(0.1 * len(neg_sorted))] if neg_sorted else 0.0
        # Count how many positives would be caught at this threshold
        tp = sum(1 for s in pos if s >= p90_neg)
        tpr = tp / len(pos) if pos else 0.0
        print(f"  At FPR≤0.10 threshold ({p90_neg:.4f}): TPR={tpr:.4f} ({tp}/{len(pos)})")

    # Per-level analysis for best discriminative channel
    print(f"\n{'='*80}")
    print(f" Per-Level TPR at FPR≤0.10 (raw channel)")
    print(f"{'='*80}")
    neg_raw = sorted(neg_channels["raw"], reverse=True)
    p90_raw = neg_raw[int(0.1 * len(neg_raw))] if neg_raw else 0.0
    for level in LEVELS:
        scores = pos_by_level[level]["raw"]
        tp = sum(1 for s in scores if s >= p90_raw)
        print(f"  {level}: TPR={tp/len(scores):.4f} ({tp}/{len(scores)}) at threshold={p90_raw:.4f}")

    # Try combined discriminator: raw_winnow + norm_winnow (max)
    print(f"\n{'='*80}")
    print(f" Combined Discriminator Strategies")
    print(f"{'='*80}")

    # Strategy: max(raw, norm)
    pos_max = [max(r, n) for r, n in zip(pos_channels["raw"], pos_channels["norm"])]
    neg_max = [max(r, n) for r, n in zip(neg_channels["raw"], neg_channels["norm"])]
    neg_max_sorted = sorted(neg_max, reverse=True)
    p90_max = neg_max_sorted[int(0.1 * len(neg_max_sorted))] if neg_max_sorted else 0.0
    tp = sum(1 for s in pos_max if s >= p90_max)
    print(f"  max(raw, norm) at FPR≤0.10 threshold ({p90_max:.4f}): TPR={tp/len(pos_max):.4f}")

    # Strategy: raw * 0.4 + norm * 0.6
    pos_wt = [0.4*r + 0.6*n for r, n in zip(pos_channels["raw"], pos_channels["norm"])]
    neg_wt = [0.4*r + 0.6*n for r, n in zip(neg_channels["raw"], neg_channels["norm"])]
    neg_wt_sorted = sorted(neg_wt, reverse=True)
    p90_wt = neg_wt_sorted[int(0.1 * len(neg_wt_sorted))] if neg_wt_sorted else 0.0
    tp = sum(1 for s in pos_wt if s >= p90_wt)
    print(f"  0.4*raw + 0.6*norm at FPR≤0.10 threshold ({p90_wt:.4f}): TPR={tp/len(pos_wt):.4f}")

    # Strategy: just raw
    print(f"\n  Pure raw at FPR≤0.10 threshold ({p90_raw:.4f}): TPR={sum(1 for s in pos_channels['raw'] if s >= p90_raw)/len(pos_channels['raw']):.4f}")

    # Strategy: norm only
    neg_norm = sorted(neg_channels["norm"], reverse=True)
    p90_norm = neg_norm[int(0.1 * len(neg_norm))] if neg_norm else 0.0
    tp_norm = sum(1 for s in pos_channels["norm"] if s >= p90_norm)
    print(f"  Pure norm at FPR≤0.10 threshold ({p90_norm:.4f}): TPR={tp_norm/len(pos_channels['norm']):.4f}")

    # Strategy: require BOTH raw AND norm above threshold (AND gate)
    for t_raw_pct, t_norm_pct in [(0.15, 0.15), (0.20, 0.20), (0.10, 0.10), (0.10, 0.15)]:
        neg_raw_s = sorted(neg_channels["raw"], reverse=True)
        neg_norm_s = sorted(neg_channels["norm"], reverse=True)
        t_raw = neg_raw_s[int(t_raw_pct * len(neg_raw_s))]
        t_norm = neg_norm_s[int(t_norm_pct * len(neg_norm_s))]

        neg_both = sum(1 for r, n in zip(neg_channels["raw"], neg_channels["norm"]) if r >= t_raw and n >= t_norm)
        pos_both = sum(1 for r, n in zip(pos_channels["raw"], pos_channels["norm"]) if r >= t_raw and n >= t_norm)
        fpr_both = neg_both / len(neg_channels["raw"]) if neg_channels["raw"] else 0.0
        tpr_both = pos_both / len(pos_channels["raw"]) if pos_channels["raw"] else 0.0
        print(f"  AND(raw≥{t_raw:.4f}, norm≥{t_norm:.4f}): TPR={tpr_both:.4f} FPR={fpr_both:.4f}")


if __name__ == "__main__":
    main()
