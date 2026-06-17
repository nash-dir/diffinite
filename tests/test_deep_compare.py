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
        idx, truncated = build_inverted_index(fp_map)
        assert truncated is False

        assert "fileA.py" in idx[10]
        assert "fileB.py" not in idx[10]

        # Hash 30 should map to all three files
        assert idx[30] == {"fileA.py", "fileB.py", "fileC.py"}

        # Hash 50 only in fileC
        assert idx[50] == {"fileC.py"}

    def test_empty(self):
        idx, truncated = build_inverted_index({})
        assert len(idx) == 0
        assert truncated is False

    def test_truncation_is_reported(self):
        fp_map = {f"f{i}.py": {i, i + 1000, i + 2000} for i in range(50)}
        idx, truncated = build_inverted_index(fp_map, max_entries=5)
        assert truncated is True


class TestDeterministicOrdering:
    """Equal-Jaccard matches must order deterministically (no hash-seed dependence)."""

    def test_run_deep_compare_tie_break_is_stable(self, tmp_path):
        from diffinite.deep_compare import run_deep_compare

        # Two B files identical to A → identical Jaccard (1.0). The tie-break
        # (shared count desc, then file id asc) must put them in a fixed order.
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        code = "def f(x):\n    return x + 1\n" * 5
        (a / "orig.py").write_text(code, encoding="utf-8")
        (b / "z_copy.py").write_text(code, encoding="utf-8")
        (b / "a_copy.py").write_text(code, encoding="utf-8")

        results = run_deep_compare(str(a), str(b), ["orig.py"],
                                   ["z_copy.py", "a_copy.py"], workers=1)
        assert results
        matched = results[0].matched_files_b
        assert [m[0] for m in matched] == sorted(m[0] for m in matched)
