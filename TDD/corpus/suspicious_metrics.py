"""Measure SUSPICIOUS recall recovery on the full corpus."""
import json, sys
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.evidence import classify_similarity_pattern

SCORES_FILE = Path(__file__).parent / "scores_all.json"
data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))

classifications = Counter()
suspicious_by_label = {"pos": 0, "neg": 0}
strict_pos_by_label = {"pos": 0, "neg": 0}

for e in data:
    cls = classify_similarity_pattern(e["scores"])
    classifications[cls] += 1
    label = "pos" if e["label"] == 1 else "neg"
    
    if cls in ("DIRECT_COPY", "SSO_COPYING", "OBFUSCATED_CLONE"):
        strict_pos_by_label[label] += 1
    elif cls.startswith("SUSPICIOUS_"):
        suspicious_by_label[label] += 1

pos_total = sum(1 for e in data if e["label"] == 1)
neg_total = sum(1 for e in data if e["label"] == 0)

print("=== Classification Distribution ===")
for cls, count in sorted(classifications.items(), key=lambda x: -x[1]):
    print(f"  {cls:<25} {count:>5}")

print(f"\n=== Metrics ===")
print(f"Total: {len(data)} (pos={pos_total}, neg={neg_total})")
print(f"\nStrict positive detections: pos={strict_pos_by_label['pos']}, neg={strict_pos_by_label['neg']}")
print(f"SUSPICIOUS detections:     pos={suspicious_by_label['pos']}, neg={suspicious_by_label['neg']}")

strict_recall = strict_pos_by_label['pos'] / pos_total if pos_total else 0
inclusive_recall = (strict_pos_by_label['pos'] + suspicious_by_label['pos']) / pos_total if pos_total else 0

strict_precision = strict_pos_by_label['pos'] / (strict_pos_by_label['pos'] + strict_pos_by_label['neg']) if (strict_pos_by_label['pos'] + strict_pos_by_label['neg']) else 1.0

susp_total = suspicious_by_label['pos'] + suspicious_by_label['neg']
susp_precision = suspicious_by_label['pos'] / susp_total if susp_total else 1.0

print(f"\nPrecision_strict:  {strict_precision:.4f}")
print(f"Recall_strict:     {strict_recall:.4f}")
print(f"Recall_inclusive:   {inclusive_recall:.4f} (includes SUSPICIOUS)")
print(f"SUSPICIOUS precision: {susp_precision:.4f} ({suspicious_by_label['pos']}/{susp_total})")
print(f"Recall recovery: {inclusive_recall - strict_recall:+.4f}")
