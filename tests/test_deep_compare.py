"""Tests for the N:M deep cross-matching engine."""

import pytest

from diffinite.deep_compare import _jaccard, build_inverted_index


class TestJaccard:
    def test_identical(self):
        s = {1, 2, 3}
        assert _jaccard(s, s) == 1.0

    def test_disjoint(self):
        assert _jaccard({1, 2}, {3, 4}) == 0.0

    def test_partial(self):
        a = {1, 2, 3, 4}
        b = {3, 4, 5, 6}
        # Intersection = {3, 4} = 2,  Union = {1..6} = 6
        assert abs(_jaccard(a, b) - 2 / 6) < 1e-9

    def test_empty_both(self):
        assert _jaccard(set(), set()) == 0.0

    def test_one_empty(self):
        assert _jaccard({1, 2}, set()) == 0.0


class TestInvertedIndex:
    def test_basic(self):
        fp_map = {
            "fileA.py": {10, 20, 30},
            "fileB.py": {20, 30, 40},
            "fileC.py": {30, 50},
        }
        idx = build_inverted_index(fp_map)

        assert "fileA.py" in idx[10]
        assert "fileB.py" not in idx[10]

        # Hash 30 should map to all three files
        assert idx[30] == {"fileA.py", "fileB.py", "fileC.py"}

        # Hash 50 only in fileC
        assert idx[50] == {"fileC.py"}

    def test_empty(self):
        idx = build_inverted_index({})
        assert len(idx) == 0
