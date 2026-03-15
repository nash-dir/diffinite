"""Simulate adding norm/raw ratio condition to SSO rule — measure FP/FN impact."""
import json, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SCORES_FILE = Path(__file__).parent / "scores_all.json"
data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))

from diffinite.evidence import (
    _SSO_RAW_MAX, _SSO_DECL_MIN, _SSO_GAP_MIN, _SSO_AST_MIN,
    _DC_RAW_MIN, _DC_IDENT_MIN,
    _OBC_RAW_MAX, _OBC_IDENT_MAX, _OBC_AST_MIN,
    _CONV_IDENT_MIN, _CONV_DECL_MAX, _CONV_RAW_MAX,
)

def classify_with_norm_ratio(scores, ratio_min=1.2):
    """Classify with additional norm/raw ratio condition on SSO rule."""
    raw = scores.get("raw_winnowing", 0.0)
    norm = scores.get("normalized_winnowing", 0.0)
    ident = scores.get("identifier_cosine", 0.0)
    decl = scores.get("declaration_cosine", 0.0)
    ast = scores.get("ast_winnowing", 0.0)

    if raw > _DC_RAW_MIN and ident > _DC_IDENT_MIN:
        return "DIRECT_COPY"

    # SSO with norm/raw ratio condition
    norm_raw_ok = (norm > raw * ratio_min) if raw > 0.01 else (norm > 0.05)
    if (raw < _SSO_RAW_MAX and decl >= _SSO_DECL_MIN
            and (ident - raw) >= _SSO_GAP_MIN and ast > _SSO_AST_MIN
            and norm_raw_ok):  # ← NEW condition
        return "SSO_COPYING"

    if raw < _OBC_RAW_MAX and ident < _OBC_IDENT_MAX and ast > _OBC_AST_MIN:
        return "OBFUSCATED_CLONE"
    if ident > _CONV_IDENT_MIN and decl < _CONV_DECL_MAX and raw < _CONV_RAW_MAX:
        return "DOMAIN_CONVERGENCE"
    return "INCONCLUSIVE"

from diffinite.evidence import classify_similarity_pattern

# Compare current vs proposed classification
changes = {"new_fp": [], "new_fn": [], "fixed_fp": [], "fixed_fn": []}
current_sso = 0
proposed_sso = 0

for e in data:
    scores = e["scores"]
    label = e["label"]
    current = classify_similarity_pattern(scores)
    proposed = classify_with_norm_ratio(scores)

    current_pos = current in ("DIRECT_COPY", "SSO_COPYING", "OBFUSCATED_CLONE")
    proposed_pos = proposed in ("DIRECT_COPY", "SSO_COPYING", "OBFUSCATED_CLONE")

    if current == "SSO_COPYING": current_sso += 1
    if proposed == "SSO_COPYING": proposed_sso += 1

    if current != proposed:
        if not current_pos and proposed_pos and label == 0:
            changes["new_fp"].append((e["pair"], current, proposed))
        elif current_pos and not proposed_pos and label == 1:
            changes["new_fn"].append((e["pair"], current, proposed))
        elif current_pos and not proposed_pos and label == 0:
            changes["fixed_fp"].append((e["pair"], current, proposed))
        elif not current_pos and proposed_pos and label == 1:
            changes["fixed_fn"].append((e["pair"], current, proposed))

print(f"Current SSO_COPYING: {current_sso}")
print(f"Proposed SSO_COPYING: {proposed_sso}")
print(f"\nNew FP (bad):  {len(changes['new_fp'])}")
print(f"New FN (bad):  {len(changes['new_fn'])}")
print(f"Fixed FP (good): {len(changes['fixed_fp'])}")
print(f"Fixed FN (good): {len(changes['fixed_fn'])}")

for k, v in changes.items():
    if v:
        print(f"\n--- {k} ---")
        for pair, cur, prop in v[:5]:
            print(f"  {pair}: {cur} → {prop}")
