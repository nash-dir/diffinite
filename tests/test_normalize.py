"""Tests for Token-Type Normalization (Phase 1).

Validates that the ``normalize=True`` mode in tokenize / extract_fingerprints
correctly normalises identifiers → ID, literals → LIT, string delimiters → STR,
while preserving keywords and operators.  This enables robust Type-2 clone
detection even when variable/function names have been systematically renamed.
"""

import pytest

from diffinite.fingerprint import (
    _COMMON_KEYWORDS,
    extract_fingerprints,
    tokenize,
)


# ---------------------------------------------------------------------------
# Helper: Jaccard similarity on fingerprint sets
# ---------------------------------------------------------------------------
def _jaccard_from_source(
    src_a: str,
    src_b: str,
    *,
    normalize: bool = False,
    k: int = 5,
    w: int = 4,
) -> float:
    """Compute Jaccard similarity between two source strings."""
    fps_a = {fp.hash_value for fp in extract_fingerprints(src_a, k=k, w=w, normalize=normalize)}
    fps_b = {fp.hash_value for fp in extract_fingerprints(src_b, k=k, w=w, normalize=normalize)}
    if not fps_a and not fps_b:
        return 0.0
    intersection = len(fps_a & fps_b)
    union = len(fps_a | fps_b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Test code samples (Type-2 clone pair: identical structure, renamed symbols)
# ---------------------------------------------------------------------------
ORIGINAL_JAVA = """\
public void handleMessage(Message msg) {
    if (msg.what == MSG_INIT) {
        mHandler.post(mCallback);
    }
    for (int i = 0; i < count; i++) {
        process(items[i]);
    }
    return result;
}
"""

RENAMED_JAVA = """\
public void processData(Packet pkt) {
    if (pkt.what == PKT_START) {
        mProcessor.post(mAction);
    }
    for (int j = 0; j < total; j++) {
        execute(entries[j]);
    }
    return output;
}
"""

ORIGINAL_PYTHON = """\
def calculate_total(items, tax_rate):
    subtotal = sum(item.price for item in items)
    tax = subtotal * tax_rate
    if tax > 100:
        tax = 100
    return subtotal + tax
"""

RENAMED_PYTHON = """\
def compute_sum(products, vat_percent):
    base = sum(product.cost for product in products)
    levy = base * vat_percent
    if levy > 100:
        levy = 100
    return base + levy
"""


# ===================================================================
# Tests
# ===================================================================
class TestTokenNormalization:
    """Basic token normalisation correctness."""

    def test_keyword_preservation(self):
        """Keywords must NOT be normalised to ID."""
        tokens = tokenize("if else return for while class void int", normalize=True)
        for kw in ["if", "else", "return", "for", "while", "class", "void", "int"]:
            assert kw in tokens, f"Keyword '{kw}' should be preserved, got {tokens}"
        # No keyword should become "ID"
        assert tokens.count("ID") == 0

    def test_identifier_normalization(self):
        """User-defined identifiers become ID."""
        tokens = tokenize("myVar + anotherVar", normalize=True)
        assert tokens == ["ID", "+", "ID"]

    def test_literal_normalization(self):
        """Numeric literals become LIT, string delimiters become STR."""
        tokens = tokenize('x = 42 + 3.14', normalize=True)
        assert "LIT" in tokens
        # 42 and 3.14 should both become LIT
        assert tokens.count("LIT") == 2

        tokens_str = tokenize('"hello"', normalize=True)
        assert tokens_str.count("STR") == 2  # opening and closing "

    def test_operator_preservation(self):
        """Operators and punctuation are preserved."""
        tokens = tokenize("a + b * (c - d)", normalize=True)
        assert "+" in tokens
        assert "*" in tokens
        assert "(" in tokens
        assert ")" in tokens
        assert "-" in tokens

    def test_normalize_false_is_raw(self):
        """normalize=False returns raw tokens (backward compat)."""
        raw = tokenize("def foo(x): return x + 1")
        normalized_off = tokenize("def foo(x): return x + 1", normalize=False)
        assert raw == normalized_off

    def test_underscore_identifiers(self):
        """Identifiers starting with _ are normalised."""
        tokens = tokenize("_private = __dunder__", normalize=True)
        assert tokens == ["ID", "=", "ID"]


class TestType2CloneDetection:
    """Type-2 clone detection via normalized fingerprints."""

    def test_type2_identical_structure_java(self):
        """Renamed Java code should have normalized Jaccard >= 0.90."""
        jaccard = _jaccard_from_source(ORIGINAL_JAVA, RENAMED_JAVA, normalize=True)
        assert jaccard >= 0.90, (
            f"Normalized Jaccard for Java Type-2 clone = {jaccard:.4f}, expected >= 0.90"
        )

    def test_type2_identical_structure_python(self):
        """Renamed Python code should have normalized Jaccard >= 0.90."""
        jaccard = _jaccard_from_source(ORIGINAL_PYTHON, RENAMED_PYTHON, normalize=True)
        assert jaccard >= 0.90, (
            f"Normalized Jaccard for Python Type-2 clone = {jaccard:.4f}, expected >= 0.90"
        )

    def test_type2_vs_raw_java(self):
        """Normalized Jaccard should be significantly higher than raw for renamed code."""
        raw_jaccard = _jaccard_from_source(ORIGINAL_JAVA, RENAMED_JAVA, normalize=False)
        norm_jaccard = _jaccard_from_source(ORIGINAL_JAVA, RENAMED_JAVA, normalize=True)
        assert norm_jaccard > raw_jaccard, (
            f"Normalized ({norm_jaccard:.4f}) should exceed raw ({raw_jaccard:.4f})"
        )

    def test_type2_vs_raw_python(self):
        """Normalized Jaccard should be significantly higher than raw for renamed code."""
        raw_jaccard = _jaccard_from_source(ORIGINAL_PYTHON, RENAMED_PYTHON, normalize=False)
        norm_jaccard = _jaccard_from_source(ORIGINAL_PYTHON, RENAMED_PYTHON, normalize=True)
        assert norm_jaccard > raw_jaccard, (
            f"Normalized ({norm_jaccard:.4f}) should exceed raw ({raw_jaccard:.4f})"
        )


class TestType1Regression:
    """Ensure normalisation does not break identical-code detection."""

    def test_normalize_does_not_break_type1(self):
        """Identical source code must have Jaccard = 1.0 with normalize=True."""
        src = "def foo(x):\n    return x * 2 + bar(x - 1)\n" * 5
        jaccard = _jaccard_from_source(src, src, normalize=True)
        assert jaccard == 1.0, f"Type-1 Jaccard = {jaccard:.4f}, expected 1.0"

    def test_type1_raw_still_works(self):
        """Identical code with normalize=False still yields Jaccard = 1.0."""
        src = "public static void main(String[] args) { System.out.println(args); }\n" * 5
        jaccard = _jaccard_from_source(src, src, normalize=False)
        assert jaccard == 1.0


class TestKeywordDictionary:
    """Sanity checks for the keyword dictionary."""

    def test_keywords_are_frozenset(self):
        assert isinstance(_COMMON_KEYWORDS, frozenset)

    def test_common_keywords_present(self):
        """Essential keywords must be in the dictionary."""
        essentials = {"if", "else", "for", "while", "return", "class", "def",
                      "void", "int", "public", "private", "import"}
        assert essentials.issubset(_COMMON_KEYWORDS)

    def test_no_empty_strings(self):
        assert "" not in _COMMON_KEYWORDS
