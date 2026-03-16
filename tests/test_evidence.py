"""Tests for the evidence module (jaccard + identifier cosine)."""

import pytest

from diffinite.evidence import (
    identifier_cosine,
    jaccard_similarity,
    compute_similarity,
)


class TestJaccardSimilarity:
    def test_identical(self):
        s = {1, 2, 3}
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint(self):
        assert jaccard_similarity({1, 2}, {3, 4}) == 0.0

    def test_partial(self):
        a = {1, 2, 3, 4}
        b = {3, 4, 5, 6}
        # Intersection = {3, 4} = 2,  Union = {1..6} = 6
        assert abs(jaccard_similarity(a, b) - 2 / 6) < 1e-9

    def test_empty_both(self):
        assert jaccard_similarity(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard_similarity({1, 2}, set()) == 0.0


class TestIdentifierCosine:
    def test_identical_sources(self):
        source = "def foo(x, y):\n    result = x + y\n    return result\n"
        score = identifier_cosine(source, source)
        assert abs(score - 1.0) < 1e-6

    def test_completely_different(self):
        source_a = "foo bar baz qux"
        source_b = "alice bob charlie dave"
        score = identifier_cosine(source_a, source_b)
        assert score == 0.0

    def test_partial_overlap(self):
        source_a = "def foo(x): return process(x)"
        source_b = "def foo(y): return handle(y)"
        score = identifier_cosine(source_a, source_b)
        assert 0.0 < score < 1.0

    def test_empty_source(self):
        score = identifier_cosine("", "def foo(): pass")
        assert score == 0.0

    def test_both_empty(self):
        score = identifier_cosine("", "")
        assert score == 0.0

    def test_keywords_excluded(self):
        """Keywords should not contribute to identifier similarity."""
        source_a = "if True: return foo"
        source_b = "if True: return bar"
        score = identifier_cosine(source_a, source_b)
        assert score < 1.0


class TestComputeSimilarity:
    def test_returns_both_metrics(self):
        result = compute_similarity(
            {1, 2, 3}, {2, 3, 4},
            "def foo(x): return x",
            "def foo(x): return x",
        )
        assert "jaccard" in result
        assert "identifier_cosine" in result

    def test_identical_inputs(self):
        s = {1, 2, 3}
        source = "def foo(x): return process(x)"
        result = compute_similarity(s, s, source, source)
        assert abs(result["jaccard"] - 1.0) < 1e-6
        assert abs(result["identifier_cosine"] - 1.0) < 1e-6

    def test_empty_fingerprints(self):
        result = compute_similarity(set(), set(), "", "")
        assert result["jaccard"] == 0.0
        assert result["identifier_cosine"] == 0.0
