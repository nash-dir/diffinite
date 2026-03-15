"""Analyze AFC raw vs filtered scores for domain-convergent pairs."""
import sys, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.parser import strip_comments
from diffinite.evidence import afc_analysis, classify_similarity_pattern

APACHE_LANG = PROJECT_ROOT / "TDD" / "corpus" / "apache_commons_lang"
APACHE_COLL = PROJECT_ROOT / "TDD" / "corpus" / "apache_commons_collections"
GUAVA_DIR = PROJECT_ROOT / "TDD" / "corpus" / "guava"
JDK_DIR = PROJECT_ROOT / "example" / "Case-NegativeControl" / "OpenJDK"
OPENJDK_X = PROJECT_ROOT / "TDD" / "corpus" / "openjdk_extra"

PAIRS = [
    ("Apache:StringUtils", APACHE_LANG / "StringUtils.java", JDK_DIR / "String.java"),
    ("Apache:ArrayUtils", APACHE_LANG / "ArrayUtils.java", OPENJDK_X / "Arrays.java"),
    ("Apache:NumberUtils", APACHE_LANG / "NumberUtils.java", OPENJDK_X / "Math.java"),
    ("Apache:CollectionUtils", APACHE_COLL / "CollectionUtils.java", JDK_DIR / "Collections.java"),
    ("Apache:ListUtils", APACHE_COLL / "ListUtils.java", JDK_DIR / "ArrayList.java"),
    ("Guava:Strings", GUAVA_DIR / "Strings.java", APACHE_LANG / "StringUtils.java"),
    ("Guava:Lists", GUAVA_DIR / "Lists.java", APACHE_COLL / "ListUtils.java"),
    ("Guava:Maps", GUAVA_DIR / "Maps.java", APACHE_COLL / "CollectionUtils.java"),
]

def read(p):
    for enc in ("utf-8", "latin-1"):
        try: return p.read_text(encoding=enc)
        except: continue
    return None

print(f"{'Pair':<28} {'raw_decl':>9} {'filt_decl':>10} {'ratio':>7} {'raw_raw':>9} {'filt_raw':>9} {'classification':<20}")
print("-" * 100)

sso_pairs = []
for name, pa, pb in PAIRS:
    ta, tb = read(pa), read(pb)
    if not ta or not tb: continue
    ca, cb = strip_comments(ta, ".java"), strip_comments(tb, ".java")
    afc = afc_analysis(ca, cb, ".java")
    rs, fs = afc["raw_scores"], afc["filtered_scores"]
    rd = rs.get("declaration_cosine", 0)
    fd = fs.get("declaration_cosine", 0)
    ratio = fd / rd if rd > 0.01 else float('inf')
    rr = rs.get("raw_winnowing", 0)
    fr = fs.get("raw_winnowing", 0)
    cls = afc["classification"]
    print(f"{name:<28} {rd:>9.4f} {fd:>10.4f} {ratio:>7.2f} {rr:>9.4f} {fr:>9.4f} {cls:<20}")
    if cls == "SSO_COPYING":
        sso_pairs.append((name, rs, fs))

    # Also test with afc_filtered=True once we know the function signature
    # For now, collect what threshold would fix each SSO pair
    if cls == "SSO_COPYING":
        print(f"  → FP! filtered_decl={fd:.4f}, needs _AFC_SSO_DECL_MIN > {fd:.2f}")
        ident = fs.get("identifier_cosine", 0)
        raw = fs.get("raw_winnowing", 0)
        gap = ident - raw
        print(f"    ident={ident:.4f}, raw={raw:.4f}, gap={gap:.4f}")

print("\n--- Summary ---")
print(f"Total pairs: {len(PAIRS)}")
print(f"SSO_COPYING FP: {len(sso_pairs)}")
for name, rs, fs in sso_pairs:
    print(f"  {name}: filt_decl={fs['declaration_cosine']:.4f}")
