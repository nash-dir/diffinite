"""Tests for the evidence module (Jaccard similarity)."""

import typing

import pytest

from diffinite.evidence import jaccard_similarity, write_manifest


class TestTypeHints:
    def test_write_manifest_type_hints_resolve(self):
        """Optional must be importable so get_type_hints() does not raise.

        write_manifest annotates root_label_a/b with Optional[str]; under
        ``from __future__ import annotations`` the NameError stays dormant until
        something resolves the hints. This locks in the import fix.
        """
        hints = typing.get_type_hints(write_manifest)
        assert hints["root_label_a"] == typing.Optional[str]


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
