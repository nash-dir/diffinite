"""Fine-grained threshold sweep with academic profile weights.

Sweeps threshold 0.50–0.90 in steps of 0.05 to find the sweet spot 
for maximizing F1 while pushing FPR as low as possible.
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import compute_channel_scores, _ACADEMIC_WEIGHTS

DATASET_ROOT = PROJECT_ROOT / "example" / "plagiarism"
CASES = sorted(p.name for p in DATASET_ROOT.iterdir() if p.is_dir())
LEVELS = [f"L{i}" for i in range(1, 7)]

def read_java(path):
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except:
            continue
    return None

def fp(text, k=2, w=3):
    cleaned = strip_comments(text, ".java")
    r = {f.hash_value for f in extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=".java")}
    n = {f.hash_value for f in extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=".java")}
    return {"raw": r, "normalized": n, "text": text, "cleaned": cleaned}

def sim(a, b):
    s = compute_channel_scores(
        fp_raw_a=a["raw"], fp_raw_b=b["raw"],
        fp_norm_a=a["normalized"], fp_norm_b=b["normalized"],
        source_a=a["text"], source_b=b["text"],
        cleaned_a=a["cleaned"], cleaned_b=b["cleaned"],
        extension=".java", weights=_ACADEMIC_WEIGHTS,
    )
    return s.get("composite", 0.0)

# Collect all scores once
print("Collecting scores...")
pos_scores = []  # (level, score)
neg_scores = []

for case_name in CASES:
    case_dir = DATASET_ROOT / case_name
    orig_files = sorted((case_dir / "original").rglob("*.java"))
    if not orig_files: continue
    orig_text = read_java(orig_files[0])
    if not orig_text: continue
    orig_fp = fp(orig_text)

    for level in LEVELS:
        level_dir = case_dir / "plagiarized" / level
        if not level_dir.exists(): continue
        for jf in sorted(level_dir.rglob("*.java")):
            text = read_java(jf)
            if text:
                pos_scores.append((level, sim(orig_fp, fp(text))))

    for jf in sorted((case_dir / "non-plagiarized").rglob("*.java")):
        text = read_java(jf)
        if text:
            neg_scores.append(sim(orig_fp, fp(text)))

print(f"  {len(pos_scores)} positive, {len(neg_scores)} negative\n")

# Sweep
print(f"{'T':<6} {'F1':<8} {'P':<8} {'R':<8} {'FPR':<8} {'TP':<5} {'FN':<5} {'FP':<5} {'TN':<5} | ", end="")
for L in LEVELS:
    print(f"{L:<8}", end="")
print()
print("-" * 110)

for t100 in range(30, 91, 5):
    threshold = t100 / 100.0
    level_tp = defaultdict(int)
    level_fn = defaultdict(int)
    for level, score in pos_scores:
        if score >= threshold:
            level_tp[level] += 1
        else:
            level_fn[level] += 1
    
    tp = sum(level_tp.values())
    fn = sum(level_fn.values())
    fp_c = sum(1 for s in neg_scores if s >= threshold)
    tn = len(neg_scores) - fp_c
    
    p = tp / (tp + fp_c) if (tp + fp_c) > 0 else 0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    fpr = fp_c / len(neg_scores) if neg_scores else 0
    
    print(f"{threshold:<6.2f} {f1:<8.4f} {p:<8.4f} {r:<8.4f} {fpr:<8.4f} {tp:<5} {fn:<5} {fp_c:<5} {tn:<5} | ", end="")
    for L in LEVELS:
        lt = level_tp[L] + level_fn[L]
        ltpr = level_tp[L] / lt if lt > 0 else 0
        print(f"{ltpr:<8.4f}", end="")
    print()
