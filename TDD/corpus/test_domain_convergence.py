"""Stage 6: Domain convergence defense & AFC effect quantification.

Tests that boilerplate filtering, TF-IDF weighting, and the AFC pipeline
effectively prevent false positives on domain-convergent code pairs
(Apache/Guava vs JDK — same utility domain but independent implementations).

Key focus:
- Before/after filtration score comparison
- Optimal thresholds correctly classify all negatives
- AFC filtration_report captures meaningful filtering
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.parser import strip_comments
from diffinite.evidence import (
    afc_analysis,
    classify_similarity_pattern,
    identifier_cosine,
    identifier_cosine_tfidf,
    declaration_identifier_cosine,
)

SCORES_FILE = Path(__file__).parent / "scores_all.json"


# ── Data paths ───────────────────────────────────────────────────────────

APACHE_LANG = PROJECT_ROOT / "TDD" / "corpus" / "apache_commons_lang"
APACHE_COLL = PROJECT_ROOT / "TDD" / "corpus" / "apache_commons_collections"
GUAVA_DIR = PROJECT_ROOT / "TDD" / "corpus" / "guava"
JDK_DIR = PROJECT_ROOT / "example" / "Case-NegativeControl" / "OpenJDK"
OPENJDK_X = PROJECT_ROOT / "TDD" / "corpus" / "openjdk_extra"

# Domain-convergent pairs (all label=0, should NOT be classified as copying)
DOMAIN_PAIRS = [
    ("Apache:StringUtils", APACHE_LANG / "StringUtils.java", JDK_DIR / "String.java"),
    ("Apache:ArrayUtils", APACHE_LANG / "ArrayUtils.java", OPENJDK_X / "Arrays.java"),
    ("Apache:NumberUtils", APACHE_LANG / "NumberUtils.java", OPENJDK_X / "Math.java"),
    ("Apache:CollectionUtils", APACHE_COLL / "CollectionUtils.java", JDK_DIR / "Collections.java"),
    ("Apache:ListUtils", APACHE_COLL / "ListUtils.java", JDK_DIR / "ArrayList.java"),
    ("Guava:Strings", GUAVA_DIR / "Strings.java", APACHE_LANG / "StringUtils.java"),
    ("Guava:Lists", GUAVA_DIR / "Lists.java", APACHE_COLL / "ListUtils.java"),
    ("Guava:Maps", GUAVA_DIR / "Maps.java", APACHE_COLL / "CollectionUtils.java"),
]


def _read(path: Path) -> str | None:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def afc_results() -> list[dict]:
    """Run AFC analysis on all domain-convergent pairs."""
    results = []
    for name, path_a, path_b in DOMAIN_PAIRS:
        text_a = _read(path_a)
        text_b = _read(path_b)
        if not text_a or not text_b:
            continue

        cleaned_a = strip_comments(text_a, ".java")
        cleaned_b = strip_comments(text_b, ".java")

        afc = afc_analysis(cleaned_a, cleaned_b, ".java")
        results.append({
            "name": name,
            "raw_scores": afc["raw_scores"],
            "filtered_scores": afc["filtered_scores"],
            "filtration_report": afc["filtration_report"],
            "classification": afc["classification"],
        })

    return results


@pytest.fixture(scope="module")
def scores_data() -> list[dict]:
    """Load scores_all.json for cross-reference."""
    if not SCORES_FILE.exists():
        pytest.skip("scores_all.json not found")
    return json.loads(SCORES_FILE.read_text(encoding="utf-8"))


# ── Core domain convergence tests ────────────────────────────────────────

class TestDomainConvergenceClassification:
    """Verify domain-convergent pairs are not falsely classified as copying."""

    def test_no_domain_pair_classified_as_direct_copy(self, afc_results: list[dict]):
        """No domain-convergent pair should be DIRECT_COPY."""
        for r in afc_results:
            assert r["classification"] != "DIRECT_COPY", (
                f"{r['name']} falsely classified as DIRECT_COPY"
            )

    def test_no_domain_pair_classified_as_sso_copying(self, afc_results: list[dict]):
        """No domain-convergent pair should be SSO_COPYING.

        Previously xfail: AFC pipeline's import-filtering + boilerplate-filtering
        produced inflated scores causing Guava↔Apache SSO FP.  Fixed by
        introducing AFC-specific thresholds (_AFC_SSO_DECL_MIN=0.75,
        _AFC_SSO_GAP_MIN=0.35) in evidence.py.
        """
        for r in afc_results:
            assert r["classification"] != "SSO_COPYING", (
                f"{r['name']} falsely classified as SSO_COPYING"
            )

    def test_domain_pairs_are_inconclusive_or_convergence(self, afc_results: list[dict]):
        """All domain-convergent pairs should be INCONCLUSIVE or DOMAIN_CONVERGENCE.

        Previously xfail: same root cause as test_no_domain_pair_classified_as_sso_copying.
        Fixed by AFC-specific thresholds.
        """
        acceptable = {"INCONCLUSIVE", "DOMAIN_CONVERGENCE"}
        for r in afc_results:
            assert r["classification"] in acceptable, (
                f"{r['name']} classified as {r['classification']}, "
                f"expected {acceptable}"
            )


class TestAFCFiltrationEffect:
    """Verify that AFC filtration reduces false-positive-inducing scores."""

    def test_filtration_reduces_declaration_cosine(self, afc_results: list[dict]):
        """Filtered declaration_cosine should be ≤ raw for some pairs.

        Boilerplate filtering removes shared method names (toString, equals, etc.)
        that inflate similarity scores between independent implementations.
        Note: filtration can sometimes _increase_ similarity when shared
        boilerplate is removed (reducing denominator), so we only expect
        a subset of pairs to show reduction.
        """
        reduced_count = 0
        for r in afc_results:
            raw_decl = r["raw_scores"].get("declaration_cosine", 0.0)
            filt_decl = r["filtered_scores"].get("declaration_cosine", 0.0)
            if filt_decl <= raw_decl + 0.001:  # small epsilon for float
                reduced_count += 1

        assert reduced_count >= max(1, len(afc_results) * 0.25), (
            f"Only {reduced_count}/{len(afc_results)} pairs showed "
            f"declaration_cosine reduction after filtration"
        )

    def test_filtration_report_not_empty(self, afc_results: list[dict]):
        """At least half of pairs should have non-empty filtration reports."""
        has_report = sum(1 for r in afc_results if r["filtration_report"])
        assert has_report >= len(afc_results) * 0.5, (
            f"Only {has_report}/{len(afc_results)} pairs have filtration reports"
        )

    def test_filtration_mentions_boilerplate(self, afc_results: list[dict]):
        """At least one pair's filtration report should mention boilerplate."""
        any_boilerplate = any(
            any("boilerplate" in line.lower() for line in r["filtration_report"])
            for r in afc_results
        )
        assert any_boilerplate, (
            "No filtration report mentions boilerplate removal"
        )


class TestScoresAllConsistency:
    """Cross-check domain pairs in scores_all.json with optimal thresholds."""

    def test_utility_domain_all_negative(self, scores_data: list[dict]):
        """All utility-domain pairs should be label=0."""
        utility = [e for e in scores_data if e["domain"] == "utility"]
        for e in utility:
            assert e["label"] == 0, (
                f"Utility pair {e['pair']} has label={e['label']}"
            )

    def test_collections_domain_all_negative(self, scores_data: list[dict]):
        """All collections-domain pairs should be label=0."""
        collections = [
            e for e in scores_data
            if e["domain"] == "collections"
        ]
        for e in collections:
            assert e["label"] == 0, (
                f"Collections pair {e['pair']} has label={e['label']}"
            )

    def test_no_utility_classified_as_copying(self, scores_data: list[dict]):
        """No utility-domain pair should be classified as copying
        (DIRECT_COPY or SSO_COPYING) in scores_all.json."""
        utility = [e for e in scores_data if e["domain"] == "utility"]
        copying = [
            e for e in utility
            if e["classification"] in ("DIRECT_COPY", "SSO_COPYING")
        ]
        assert len(copying) == 0, (
            f"{len(copying)} utility pairs classified as copying: "
            f"{[e['pair'] for e in copying[:3]]}"
        )


class TestAFCQuantification:
    """Quantify the before/after effect of AFC analysis."""

    def test_summary_table(self, afc_results: list[dict]):
        """Verify we can produce a summary of before/after scores."""
        # This test just validates the data structure for the summary
        for r in afc_results:
            assert "raw_scores" in r
            assert "filtered_scores" in r
            raw_decl = r["raw_scores"].get("declaration_cosine", -1)
            filt_decl = r["filtered_scores"].get("declaration_cosine", -1)
            assert 0.0 <= raw_decl <= 1.0
            assert 0.0 <= filt_decl <= 1.0

    def test_print_before_after_table(self, afc_results: list[dict], capsys):
        """Print a before/after comparison table (diagnostic, always passes)."""
        print("\n" + "=" * 90)
        print("  AFC Before/After Comparison (Domain-Convergent Pairs)")
        print("=" * 90)
        print(f"  {'Pair':<30} {'Raw Decl':>9} {'Filt Decl':>10} "
              f"{'Δ Decl':>7} {'Raw ID':>7} {'Classification':<20}")
        print("-" * 90)

        for r in afc_results:
            raw_decl = r["raw_scores"].get("declaration_cosine", 0)
            filt_decl = r["filtered_scores"].get("declaration_cosine", 0)
            delta = filt_decl - raw_decl
            raw_id = r["raw_scores"].get("identifier_cosine", 0)
            cls = r["classification"]
            print(f"  {r['name']:<30} {raw_decl:>9.4f} {filt_decl:>10.4f} "
                  f"{delta:>+7.4f} {raw_id:>7.4f} {cls:<20}")

        print("=" * 90)
