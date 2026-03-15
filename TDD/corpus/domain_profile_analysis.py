"""Analyze score distributions per domain to determine academic profile thresholds."""
import json, sys, statistics
from pathlib import Path
from collections import defaultdict

SCORES_FILE = Path(__file__).parent / "scores_all.json"
data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))

# Group by domain
by_domain = defaultdict(list)
for e in data:
    by_domain[e["domain"]].append(e)

channels = ["raw_winnowing", "normalized_winnowing", "ast_winnowing",
            "identifier_cosine", "declaration_cosine", "comment_string_overlap"]

print("=" * 100)
print("  Domain-wise Score Distribution (median [min–max])")
print("=" * 100)
print(f"  {'Domain':<18} {'Label':<6} {'N':>3} ", end="")
for ch in channels:
    short = ch.replace("_winnowing", "_w").replace("_cosine", "_cos").replace("_overlap", "_ovl").replace("comment_string", "comment")
    print(f"  {short:>12}", end="")
print()
print("-" * 100)

for domain in sorted(by_domain.keys()):
    entries = by_domain[domain]
    for label in [0, 1]:
        subset = [e for e in entries if e["label"] == label]
        if not subset:
            continue
        label_str = "pos" if label == 1 else "neg"
        row = f"  {domain:<18} {label_str:<6} {len(subset):>3} "
        for ch in channels:
            vals = [e["scores"].get(ch, 0.0) for e in subset]
            med = statistics.median(vals)
            row += f"  {med:>12.4f}"
        print(row)

print("=" * 100)

# Separate academic vs industrial domains
academic_domains = {"irplag", "soco"}
industrial_domains = {"sso", "clones"}
negative_domains = {"utility", "collections"}

print("\n=== Academic vs Industrial threshold analysis ===\n")

academic_pos = [e for e in data if e["domain"] in academic_domains and e["label"] == 1]
academic_neg = [e for e in data if e["domain"] in academic_domains and e["label"] == 0]
industrial_pos = [e for e in data if e["domain"] in industrial_domains and e["label"] == 1]

print(f"Academic positive: {len(academic_pos)}")
print(f"Academic negative: {len(academic_neg)}")
print(f"Industrial positive: {len(industrial_pos)}")

# For academic pairs, find optimal thresholds
# Key challenge: academic code is short, so base raw_winnowing is often > 0.50
# We need higher DC_RAW_MIN to avoid FP
if academic_pos:
    for ch in channels:
        pos_vals = sorted([e["scores"].get(ch, 0.0) for e in academic_pos])
        neg_vals = sorted([e["scores"].get(ch, 0.0) for e in academic_neg]) if academic_neg else [0.0]
        p10 = pos_vals[int(len(pos_vals) * 0.10)] if len(pos_vals) > 10 else pos_vals[0]
        p25 = pos_vals[int(len(pos_vals) * 0.25)]
        p50 = pos_vals[int(len(pos_vals) * 0.50)]
        n_max = max(neg_vals) if neg_vals else 0.0
        n_p90 = neg_vals[int(len(neg_vals) * 0.90)] if len(neg_vals) > 10 else n_max
        print(f"  {ch:<25} pos: p10={p10:.4f} p25={p25:.4f} p50={p50:.4f}  neg: p90={n_p90:.4f} max={n_max:.4f}")

# Determine academic thresholds
print("\n=== Proposed Academic Thresholds ===")
print("Goal: higher bar for DIRECT_COPY and SSO_COPYING to suppress FP on short code")

# For academic, raw_winnowing tends to be higher even for negative pairs
# because short codes share more common constructs
if academic_neg:
    neg_raw = [e["scores"].get("raw_winnowing", 0.0) for e in academic_neg]
    neg_raw_max = max(neg_raw)
    neg_raw_p90 = sorted(neg_raw)[int(len(neg_raw) * 0.90)] if len(neg_raw) > 10 else neg_raw_max
    print(f"  neg raw_winnowing: max={neg_raw_max:.4f}, p90={neg_raw_p90:.4f}")
    print(f"  → _DC_RAW_MIN should be > {neg_raw_max:.2f} (academic)")

    neg_decl = [e["scores"].get("declaration_cosine", 0.0) for e in academic_neg]
    neg_decl_max = max(neg_decl)
    print(f"  neg declaration_cosine: max={neg_decl_max:.4f}")
    print(f"  → _SSO_DECL_MIN should be > {neg_decl_max:.2f} (academic)")

    neg_ident = [e["scores"].get("identifier_cosine", 0.0) for e in academic_neg]
    neg_ident_max = max(neg_ident)
    print(f"  neg identifier_cosine: max={neg_ident_max:.4f}")
