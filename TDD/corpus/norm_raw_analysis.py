"""Analyze normalized_winnowing / raw_winnowing ratio for positive vs negative pairs."""
import json, sys
from pathlib import Path

SCORES_FILE = Path(__file__).parent / "scores_all.json"
data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))

print(f"Total pairs: {len(data)}")

# Separate by label
pos = [e for e in data if e["label"] == 1]
neg = [e for e in data if e["label"] == 0]
print(f"Positive: {len(pos)}, Negative: {len(neg)}\n")

def analyze(entries, label_name):
    ratios = []
    for e in entries:
        raw = e["scores"].get("raw_winnowing", 0)
        norm = e["scores"].get("normalized_winnowing", 0)
        if raw > 0.01:  # avoid division by zero
            ratios.append(norm / raw)
        elif norm > 0.05:
            ratios.append(float('inf'))  # Type-2 signal: raw=0 but norm>0

    valid = [r for r in ratios if r != float('inf')]
    inf_count = len(ratios) - len(valid)

    if valid:
        import statistics
        median = statistics.median(valid)
        mean = statistics.mean(valid)
        print(f"[{label_name}] n={len(entries)}, ratio computed={len(ratios)}")
        print(f"  median ratio: {median:.4f}")
        print(f"  mean ratio:   {mean:.4f}")
        print(f"  min={min(valid):.4f}, max={max(valid):.4f}")
        print(f"  inf count (raw≈0, norm>0): {inf_count}")

        # Distribution
        below_1 = sum(1 for r in valid if r < 1.0)
        at_1 = sum(1 for r in valid if 0.95 <= r <= 1.05)
        above_1_2 = sum(1 for r in valid if r > 1.2)
        above_1_5 = sum(1 for r in valid if r > 1.5)
        print(f"  ratio < 1.0:  {below_1}/{len(valid)} ({below_1/len(valid)*100:.1f}%)")
        print(f"  ratio ≈ 1.0:  {at_1}/{len(valid)} ({at_1/len(valid)*100:.1f}%)")
        print(f"  ratio > 1.2:  {above_1_2}/{len(valid)} ({above_1_2/len(valid)*100:.1f}%)")
        print(f"  ratio > 1.5:  {above_1_5}/{len(valid)} ({above_1_5/len(valid)*100:.1f}%)")
    else:
        print(f"[{label_name}] No valid ratios computed")
    print()

analyze(pos, "POSITIVE")
analyze(neg, "NEGATIVE")

# Show SSO-relevant positive pairs (low raw, high norm)
print("--- Type-2 signal candidates (raw < 0.20, norm > raw) ---")
for e in pos:
    raw = e["scores"].get("raw_winnowing", 0)
    norm = e["scores"].get("normalized_winnowing", 0)
    if raw < 0.20 and norm > raw:
        ratio = norm / raw if raw > 0.01 else float('inf')
        print(f"  {e['pair']}: raw={raw:.4f}, norm={norm:.4f}, ratio={ratio:.2f}")
