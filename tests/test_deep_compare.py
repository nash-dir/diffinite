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


class TestLangAwarePlumbing:
    """WS-C.2: --lang-aware must thread through run_deep_compare end to end and
    leave the default (language-agnostic) channel byte-identical."""

    def test_lang_aware_runs_and_matches_rust(self, tmp_path):
        from diffinite.deep_compare import run_deep_compare
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        rust = ("pub fn add(a: i32, b: i32) -> i32 {\n"
                "    let total = a + b;\n    total\n}\n") * 3
        (a / "lib.rs").write_text(rust, encoding="utf-8")
        (b / "lib.rs").write_text(rust, encoding="utf-8")

        res = run_deep_compare(str(a), str(b), ["lib.rs"], ["lib.rs"],
                               workers=1, normalize=True, lang_aware=True)
        assert res and res[0].matched_files_b
        # Identical inputs -> Jaccard 1.0 regardless of channel.
        assert res[0].matched_files_b[0][2] == 1.0

    def test_default_channel_unaffected(self, tmp_path):
        from diffinite.deep_compare import run_deep_compare
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        code = "def f(x):\n    return x + 1\n" * 5
        (a / "m.py").write_text(code, encoding="utf-8")
        (b / "m.py").write_text(code, encoding="utf-8")

        base = run_deep_compare(str(a), str(b), ["m.py"], ["m.py"],
                                workers=1, normalize=True)
        explicit = run_deep_compare(str(a), str(b), ["m.py"], ["m.py"],
                                    workers=1, normalize=True, lang_aware=False)
        assert base[0].matched_files_b == explicit[0].matched_files_b


class TestInconclusiveBand:
    """WS-B.enforce: under normalize, a pair whose smaller file is below the
    calibrated token floor is flagged inconclusive (4th tuple element)."""

    def _run(self, tmp_path, code, normalize, *, lang_aware=False, ext="py"):
        from diffinite.deep_compare import run_deep_compare
        a = tmp_path / "a"; a.mkdir(parents=True)
        b = tmp_path / "b"; b.mkdir(parents=True)
        (a / f"f.{ext}").write_text(code, encoding="utf-8")
        (b / f"f.{ext}").write_text(code, encoding="utf-8")
        return run_deep_compare(str(a), str(b), [f"f.{ext}"], [f"f.{ext}"],
                                workers=1, normalize=normalize, lang_aware=lang_aware)

    def test_small_normalized_pair_is_inconclusive(self, tmp_path):
        res = self._run(tmp_path, "def f(x):\n    return x + 1\n", True)
        assert res and res[0].matched_files_b[0][3] is True

    def test_large_normalized_pair_is_conclusive(self, tmp_path):
        res = self._run(tmp_path, "def f(x):\n    return x + 1\n" * 30, True)
        assert res and res[0].matched_files_b[0][3] is False

    def test_raw_mode_never_inconclusive(self, tmp_path):
        # The band is a normalize-precision mitigation; raw mode is unaffected
        # even for tiny files.
        res = self._run(tmp_path, "def f(x):\n    return x + 1\n", False)
        assert res and res[0].matched_files_b[0][3] is False

    def test_inconclusive_boundary_is_pinned_at_the_floor(self, tmp_path):
        # Pin the exact boundary: floor-1 tokens -> inconclusive, floor tokens ->
        # conclusive. (Prior tests used 10 vs 300, far from the floor, so a `<`/`<=`
        # flip or a floor change would have passed silently.)
        from diffinite.fingerprint import tokenize
        from diffinite.calibration import INCONCLUSIVE_TOKEN_FLOOR as F
        below = " ".join(f"v{i}" for i in range(F - 1))   # F-1 raw tokens
        at = " ".join(f"v{i}" for i in range(F))          # F raw tokens
        assert len(tokenize(below)) == F - 1 and len(tokenize(at)) == F
        rb = self._run(tmp_path / "b1", below, True)
        ra = self._run(tmp_path / "a1", at, True)
        assert rb[0].matched_files_b[0][3] is True    # F-1 < floor -> inconclusive
        assert ra[0].matched_files_b[0][3] is False   # F == floor -> conclusive

    def test_floor_decision_is_channel_independent(self, tmp_path):
        # The floor is a file-size gate in raw-token units, so --lang-aware (whose
        # Pygments tokenization yields a different count) must reach the SAME
        # inconclusive verdict as plain normalize for the same file.
        rust = "pub fn add(a: i32, b: i32) -> i32 { let t = a + b; t }\n"
        plain = self._run(tmp_path / "p", rust, True, ext="rs")
        la = self._run(tmp_path / "l", rust, True, lang_aware=True, ext="rs")
        assert plain[0].matched_files_b[0][3] == la[0].matched_files_b[0][3]


class TestSizeCap:
    """Audit B3: oversized files are skipped from deep compare (both channels),
    so an untrusted large/pathological file can't hang the run."""

    def test_oversized_file_skipped(self, tmp_path):
        from diffinite.deep_compare import run_deep_compare
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        big = "def f(x):\n    return x + 1\n" * 200  # ~5 KB
        (a / "f.py").write_text(big, encoding="utf-8")
        (b / "f.py").write_text(big, encoding="utf-8")
        # 1 KB cap -> both files exceed it -> skipped -> no fingerprints -> no match
        res = run_deep_compare(str(a), str(b), ["f.py"], ["f.py"],
                               workers=1, max_file_size_mb=0.001)
        assert res == []

    def test_under_cap_still_matches(self, tmp_path):
        from diffinite.deep_compare import run_deep_compare
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        code = "def f(x):\n    return x + 1\n" * 5
        (a / "f.py").write_text(code, encoding="utf-8")
        (b / "f.py").write_text(code, encoding="utf-8")
        res = run_deep_compare(str(a), str(b), ["f.py"], ["f.py"],
                               workers=1, max_file_size_mb=10.0)
        assert res and res[0].matched_files_b
