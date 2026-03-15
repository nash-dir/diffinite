"""Legal Defense Pattern Tests — Idea-Expression Dichotomy TDD Suite.

Tests the dual-profile analysis that classifies code similarity
into legal defense categories:
  - CLEAN_ROOM_PROBABLE: same algorithm, different expression
  - MERGER_FILTERED: similarity due to constrained expression
  - LITERAL_COPYING: expression-level copying
  - INDEPENDENT_CREATION: independently written code
"""
import sys
from pathlib import Path

import pytest

# Allow importing from src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.evidence import analyze_legal_defense_pattern

LEGAL_DIR = Path(__file__).parent


def _read_pair(base_a: str, base_b: str) -> tuple[str, str]:
    """Read a Java file pair from the legal_defense directory."""
    a = (LEGAL_DIR / base_a).read_text(encoding="utf-8")
    b = (LEGAL_DIR / base_b).read_text(encoding="utf-8")
    return a, b


class TestCleanRoomDefense:
    """Tests for clean room design defense pattern.

    Clean room: same algorithm (idea), completely different expression.
    Expected: low industrial raw, high academic AST, large positive delta.
    """

    def test_clean_room_mergesort_industrial_raw_low(self):
        """MergeSort A vs B: industrial raw_winnowing should be low."""
        a, b = _read_pair("CleanRoom_MergeSort_A.java",
                          "CleanRoom_MergeSort_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        assert result["industrial_scores"]["raw_winnowing"] < 0.30

    def test_clean_room_mergesort_academic_ast_high(self):
        """MergeSort A vs B: academic AST should show structural similarity."""
        a, b = _read_pair("CleanRoom_MergeSort_A.java",
                          "CleanRoom_MergeSort_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        assert result["academic_scores"]["ast_winnowing"] > 0.40

    def test_clean_room_mergesort_delta_positive(self):
        """MergeSort A vs B: academic composite > industrial composite."""
        a, b = _read_pair("CleanRoom_MergeSort_A.java",
                          "CleanRoom_MergeSort_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        assert result["delta"] > 0.0, (
            f"Expected positive delta, got {result['delta']:.4f}"
        )

    def test_clean_room_has_disclaimer(self):
        """Explanation must contain legal disclaimer."""
        a, b = _read_pair("CleanRoom_MergeSort_A.java",
                          "CleanRoom_MergeSort_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        assert "면책조항" in result["explanation"]

    def test_result_has_required_keys(self):
        """Result dict must have all required keys."""
        a, b = _read_pair("CleanRoom_MergeSort_A.java",
                          "CleanRoom_MergeSort_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        required = {"industrial_scores", "academic_scores", "delta",
                    "legal_pattern", "explanation"}
        assert required.issubset(result.keys())


class TestMergerDoctrine:
    """Tests for merger doctrine / scènes à faire patterns.

    When there is only one way to express an idea (e.g., design patterns),
    the expression merges with the idea and is not copyrightable.
    """

    def test_singleton_high_structural_similarity(self):
        """Singleton A vs B: high structural similarity."""
        a, b = _read_pair("Singleton_A.java", "Singleton_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        # Design pattern code should show moderate-to-high similarity
        acad_c = result["academic_scores"].get("composite", 0.0)
        assert acad_c > 0.20, f"Expected academic composite > 0.20, got {acad_c}"

    def test_factory_high_structural_similarity(self):
        """Factory A vs B: high structural similarity."""
        a, b = _read_pair("Factory_A.java", "Factory_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        acad_c = result["academic_scores"].get("composite", 0.0)
        assert acad_c > 0.20, f"Expected academic composite > 0.20, got {acad_c}"

    def test_singleton_not_literal_copying(self):
        """Singleton should NOT be classified as LITERAL_COPYING."""
        a, b = _read_pair("Singleton_A.java", "Singleton_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        assert result["legal_pattern"] != "LITERAL_COPYING"

    def test_factory_not_literal_copying(self):
        """Factory should NOT be classified as LITERAL_COPYING."""
        a, b = _read_pair("Factory_A.java", "Factory_B.java")
        result = analyze_legal_defense_pattern(a, b, ".java")
        assert result["legal_pattern"] != "LITERAL_COPYING"
