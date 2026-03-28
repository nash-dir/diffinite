"""Tests for the evidence module (Jaccard similarity)."""

import pytest

from diffinite.evidence import jaccard_similarity


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
