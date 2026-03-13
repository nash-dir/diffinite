"""Integration tests using real SQLite amalgamation data.

Ported from TDD/test_logic.py — comprehensive tests covering:
    A = Collector Accuracy,  P = Parser,  D = Diff,  F = Fingerprint,
    E = Edge/Stability,  B = Autojunk,  C = Context-fold

Uses real SQLite amalgamation data from ``example/sqlite/`` as test fixtures.
Tests are skipped automatically when example data is not present.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from diffinite.collector import collect_files, match_files
from diffinite.deep_compare import _jaccard, run_deep_compare
from diffinite.differ import compute_diff, generate_html_diff, read_file
from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments

# ---------------------------------------------------------------------------
# Fixtures — support both example/sqlite/ and TDD/ data locations
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CANDIDATES = [
    _PROJECT_ROOT / "example" / "sqlite",
    _PROJECT_ROOT / "TDD",
    _PROJECT_ROOT / "legacy" / "TDD",
]

EXAMPLE_DIR = next(
    (d for d in _CANDIDATES if (d / "left" / "sqlite3.c").is_file()), None
)
LEFT = str(EXAMPLE_DIR / "left") if EXAMPLE_DIR else ""
RIGHT = str(EXAMPLE_DIR / "right") if EXAMPLE_DIR else ""
DATA_EXISTS = EXAMPLE_DIR is not None

pytestmark = pytest.mark.skipif(
    not DATA_EXISTS,
    reason="SQLite example data not found — run setup_example_sqlite.py first",
)


@pytest.fixture(scope="module")
def matched_pairs():
    """Collect and match files once for the whole module."""
    fa = collect_files(LEFT)
    fb = collect_files(RIGHT)
    matches, ua, ub = match_files(fa, fb)
    return fa, fb, matches, ua, ub


@pytest.fixture(scope="module")
def file_texts():
    """Read all file pairs once."""
    texts = {}
    root_a, root_b = Path(LEFT).resolve(), Path(RIGHT).resolve()
    for name in ["sqlite3.c", "sqlite3.h", "sqlite3ext.h", "shell.c"]:
        texts[f"left/{name}"] = read_file(str(root_a / name))
        texts[f"right/{name}"] = read_file(str(root_b / name))
    return texts


# ===================================================================
# A: Collector & Matching Accuracy
# ===================================================================
class TestCollectorAccuracy:
    """[A1, A2] File collection and fuzzy matching."""

    def test_a1_file_count(self, matched_pairs):
        fa, fb, matches, ua, ub = matched_pairs
        assert len(fa) == 4, f"Expected 4 left files, got {len(fa)}"
        assert len(fb) == 4, f"Expected 4 right files, got {len(fb)}"

    def test_a1_no_unmatched(self, matched_pairs):
        _, _, _, ua, ub = matched_pairs
        assert ua == [], f"Unexpected unmatched A: {ua}"
        assert ub == [], f"Unexpected unmatched B: {ub}"

    def test_a2_all_pairs_matched(self, matched_pairs):
        _, _, matches, _, _ = matched_pairs
        assert len(matches) == 4

    def test_a2_similarity_100(self, matched_pairs):
        _, _, matches, _, _ = matched_pairs
        for m in matches:
            assert m.similarity == 100.0, (
                f"{m.rel_path_a}: expected 100.0, got {m.similarity}"
            )
            assert m.rel_path_a == m.rel_path_b

    def test_a2_sorted_posix_paths(self, matched_pairs):
        fa, _, _, _, _ = matched_pairs
        assert fa == sorted(fa), "File list should be sorted"
        assert all("/" in f or "." in f for f in fa)


# ===================================================================
# P: Comment Parser
# ===================================================================
class TestCommentParser:
    """[P1, P2, P3] Comment stripping accuracy and performance."""

    def test_p1_line_preservation_sqlite3_h(self, file_texts):
        text = file_texts["left/sqlite3.h"]
        stripped = strip_comments(text, ".h")
        orig_lines = text.count("\n")
        stripped_lines = stripped.count("\n")
        assert orig_lines == stripped_lines, (
            f"Line count changed: {orig_lines} → {stripped_lines}"
        )

    def test_p1_line_preservation_shell_c(self, file_texts):
        text = file_texts["left/shell.c"]
        stripped = strip_comments(text, ".c")
        assert text.count("\n") == stripped.count("\n")

    def test_p2_url_in_code_preserved(self, file_texts):
        text = file_texts["left/sqlite3.h"]
        stripped = strip_comments(text, ".h")
        assert '"3.45.0"' in stripped or '"3.' in stripped, (
            "Version string literal was incorrectly stripped"
        )

    def test_p2_string_slashes_preserved(self, file_texts):
        test_code = 'char *url = "http://sqlite.org/path";\n'
        stripped = strip_comments(test_code, ".c")
        assert '"http://sqlite.org/path"' in stripped, (
            f"URL in string literal was stripped: {stripped!r}"
        )
        test_code2 = 'printf("see https://www.sqlite.org/doc");  // comment\n'
        stripped2 = strip_comments(test_code2, ".c")
        assert '"see https://www.sqlite.org/doc"' in stripped2
        assert '// comment' not in stripped2

    def test_p3_performance_sqlite3_c(self, file_texts):
        text = file_texts["left/sqlite3.c"]
        strip_comments(text[:1000], ".c")
        start = time.perf_counter()
        strip_comments(text, ".c")
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s (limit: 2.0s)"

    def test_p3_performance_shell_c(self, file_texts):
        text = file_texts["left/shell.c"]
        start = time.perf_counter()
        strip_comments(text, ".c")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Too slow: {elapsed:.2f}s (limit: 0.5s)"


# ===================================================================
# D: Diff Engine
# ===================================================================
class TestDiffEngine:
    """[D1, D2, D3] Diff computation accuracy and performance."""

    def test_d1_ratio_range(self, file_texts):
        for name in ["sqlite3.h", "sqlite3ext.h", "shell.c"]:
            ta = file_texts[f"left/{name}"]
            tb = file_texts[f"right/{name}"]
            ratio, adds, dels = compute_diff(ta, tb)
            assert 0.0 <= ratio <= 1.0, f"{name}: ratio={ratio}"
            assert adds >= 0 and dels >= 0

    def test_d1_adjacent_versions_high_similarity(self, file_texts):
        ta = file_texts["left/sqlite3.h"]
        tb = file_texts["right/sqlite3.h"]
        ratio, _, _ = compute_diff(ta, tb)
        assert ratio > 0.5, f"sqlite3.h ratio too low: {ratio:.4f}"

    def test_d2_identical_input(self, file_texts):
        text = file_texts["left/sqlite3.h"]
        ratio, adds, dels = compute_diff(text, text)
        assert ratio == 1.0
        assert adds == 0 and dels == 0

    def test_d2_empty_inputs(self):
        ratio, adds, dels = compute_diff("", "")
        assert ratio == 1.0
        assert adds == 0 and dels == 0

    def test_d3_performance_sqlite3_c(self, file_texts):
        ta = strip_comments(file_texts["left/sqlite3.c"], ".c")
        tb = strip_comments(file_texts["right/sqlite3.c"], ".c")
        start = time.perf_counter()
        ratio, adds, dels = compute_diff(ta, tb)
        elapsed = time.perf_counter() - start
        assert elapsed < 30.0, f"Too slow: {elapsed:.2f}s"
        assert ratio > 0.95 and adds > 0 and dels > 0

    def test_d3_folded_html_much_smaller(self, file_texts):
        ta = file_texts["left/sqlite3.h"]
        tb = file_texts["right/sqlite3.h"]
        folded = generate_html_diff(
            ta, tb, filename_a="sqlite3.h", filename_b="sqlite3.h",
            context_lines=3,
        )
        full = generate_html_diff(
            ta, tb, filename_a="sqlite3.h", filename_b="sqlite3.h",
            context_lines=-1,
        )
        ratio = len(folded) / len(full)
        assert ratio < 0.5, f"Fold ratio {ratio:.2f} — expected < 0.50"

    def test_d3_html_well_formed(self, file_texts):
        ta = file_texts["left/sqlite3ext.h"]
        tb = file_texts["right/sqlite3ext.h"]
        html = generate_html_diff(
            ta, tb,
            label_a="left", label_b="right",
            filename_a="sqlite3ext.h", filename_b="sqlite3ext.h",
        )
        assert html.startswith('<table class="difftbl">')
        assert html.endswith("</table>")
        assert "<thead>" in html
        assert "<tbody>" in html

    def test_d3_html_has_diff_markers(self, file_texts):
        ta = file_texts["left/sqlite3.h"]
        tb = file_texts["right/sqlite3.h"]
        html = generate_html_diff(
            ta, tb, filename_a="sqlite3.h", filename_b="sqlite3.h",
        )
        has_markers = 'class="code add"' in html or 'class="code del"' in html
        assert has_markers, "HTML diff missing add/del markers"

    def test_d3_html_has_pygments_styles(self, file_texts):
        ta = file_texts["left/sqlite3ext.h"]
        tb = file_texts["right/sqlite3ext.h"]
        html = generate_html_diff(
            ta, tb, filename_a="sqlite3ext.h", filename_b="sqlite3ext.h",
        )
        assert 'style="' in html, "Missing Pygments inline styles"


# ===================================================================
# F: Fingerprint & Deep Compare
# ===================================================================
class TestFingerprint:
    """[F1, F2, F3, F4] Winnowing fingerprint & deep compare."""

    def test_f1_extraction_nonzero(self, file_texts):
        for name in ["sqlite3.h", "sqlite3ext.h", "shell.c"]:
            text = file_texts[f"left/{name}"]
            stripped = strip_comments(text, ".c")
            fps = extract_fingerprints(stripped, k=10, w=8)
            assert len(fps) > 0, f"{name}: zero fingerprints"

    def test_f2_self_jaccard_high(self, file_texts):
        for name in ["sqlite3.h", "sqlite3ext.h", "shell.c"]:
            ta = strip_comments(file_texts[f"left/{name}"], ".c")
            tb = strip_comments(file_texts[f"right/{name}"], ".c")
            fa = {fp.hash_value for fp in extract_fingerprints(ta, k=10, w=8)}
            fb = {fp.hash_value for fp in extract_fingerprints(tb, k=10, w=8)}
            j = _jaccard(fa, fb)
            assert j >= 0.70, f"{name}: Jaccard={j:.4f} (min 0.70)"

    def test_f3_top1_self_match(self):
        fa = collect_files(LEFT)
        fb = collect_files(RIGHT)
        results = run_deep_compare(
            LEFT, RIGHT, fa, fb,
            k=10, w=8, workers=1, min_jaccard=0.01,
        )
        for r in results:
            assert r.matched_files_b, f"{r.file_a}: no matches"
            top_file = r.matched_files_b[0][0]
            assert top_file == r.file_a, (
                f"{r.file_a}: top match is {top_file}, expected self"
            )

    def test_f4_fingerprint_performance_sqlite3_c(self, file_texts):
        text = file_texts["left/sqlite3.c"]
        stripped = strip_comments(text, ".c")
        start = time.perf_counter()
        fps = extract_fingerprints(stripped, k=10, w=8)
        elapsed = time.perf_counter() - start
        assert elapsed < 30.0, f"Too slow: {elapsed:.2f}s"
        assert len(fps) > 0


# ===================================================================
# E: Edge Cases & Stability
# ===================================================================
class TestEdgeCases:
    """[E1, E2] Determinism and edge-case handling."""

    def test_e1_deterministic(self, file_texts):
        ta = file_texts["left/sqlite3.h"]
        tb = file_texts["right/sqlite3.h"]
        results = []
        for _ in range(3):
            r, a, d = compute_diff(ta, tb)
            results.append((round(r, 10), a, d))
        assert results[0] == results[1] == results[2]

    def test_e1_fingerprint_deterministic(self, file_texts):
        text = strip_comments(file_texts["left/sqlite3.h"], ".h")
        fp_sets = []
        for _ in range(3):
            fps = extract_fingerprints(text, k=10, w=8)
            fp_sets.append({fp.hash_value for fp in fps})
        assert fp_sets[0] == fp_sets[1] == fp_sets[2]

    def test_e2_empty_file_no_crash(self):
        assert strip_comments("", ".c") == ""
        r, a, d = compute_diff("", "")
        assert r == 1.0
        fps = extract_fingerprints("", k=10, w=8)
        assert fps == []

    def test_e2_one_side_empty(self):
        r, a, d = compute_diff("int main() {}", "")
        assert 0.0 <= r <= 1.0
        assert a == 0 and d >= 1

    def test_e2_encoding_detection(self, file_texts):
        for key, text in file_texts.items():
            assert text is not None, f"Failed to read {key}"
            assert len(text) > 0, f"Empty text for {key}"

    def test_e2_all_exact_matched(self, matched_pairs):
        _, _, matches, _, _ = matched_pairs
        for m in matches:
            assert m.similarity == 100.0

    def test_e2_mixed_exact_and_fuzzy(self):
        fa = ["common.c", "renamed_old.c", "unique_a.c"]
        fb = ["common.c", "renamed_new.c", "unique_b.c"]
        matches, ua, ub = match_files(fa, fb, threshold=50)
        exact = [m for m in matches if m.similarity == 100.0]
        fuzzy = [m for m in matches if m.similarity < 100.0]
        assert len(exact) == 1, f"Expected 1 exact match: {exact}"
        assert exact[0].rel_path_a == "common.c"
        assert len(fuzzy) >= 1, "Expected fuzzy matches for renamed files"


# ===================================================================
# B: Differ autojunk optimization
# ===================================================================
class TestDifferAutojunk:
    """Verify autojunk=True gives massive speedup."""

    def test_b_diff_perf_under_half_second(self, file_texts):
        ta = file_texts["left/sqlite3.h"]
        tb = file_texts["right/sqlite3.h"]
        start = time.perf_counter()
        ratio, adds, dels = compute_diff(ta, tb)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Too slow: {elapsed:.2f}s (limit: 0.5s)"
        assert ratio > 0.95, f"Ratio too low: {ratio:.4f}"

    def test_b_shell_diff_fast(self, file_texts):
        ta = file_texts["left/shell.c"]
        tb = file_texts["right/shell.c"]
        start = time.perf_counter()
        compute_diff(ta, tb)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s"


# ===================================================================
# C: Context-fold HTML
# ===================================================================
class TestContextFoldHTML:
    """Verify HTML context folding reduces output size."""

    def test_c_fold_has_separator(self, file_texts):
        ta = file_texts["left/sqlite3.h"]
        tb = file_texts["right/sqlite3.h"]
        html = generate_html_diff(
            ta, tb, filename_a="sqlite3.h", filename_b="sqlite3.h",
            context_lines=3,
        )
        assert 'class="fold"' in html, "Missing fold separator row"
        assert "identical lines" in html

    def test_c_fold_much_smaller_than_full(self, file_texts):
        ta = file_texts["left/sqlite3ext.h"]
        tb = file_texts["right/sqlite3ext.h"]
        full = generate_html_diff(
            ta, tb, filename_a="sqlite3ext.h", filename_b="sqlite3ext.h",
            context_lines=-1,
        )
        folded = generate_html_diff(
            ta, tb, filename_a="sqlite3ext.h", filename_b="sqlite3ext.h",
            context_lines=3,
        )
        ratio = len(folded) / len(full)
        assert ratio < 0.5, f"Fold ratio {ratio:.2f} — expected < 0.50"

    def test_c_fold_still_well_formed(self, file_texts):
        ta = file_texts["left/sqlite3ext.h"]
        tb = file_texts["right/sqlite3ext.h"]
        html = generate_html_diff(
            ta, tb, filename_a="sqlite3ext.h", filename_b="sqlite3ext.h",
        )
        assert html.startswith('<table class="difftbl">')
        assert html.endswith("</table>")


# ===================================================================
# D2: Fingerprint with tuned defaults (k=5, w=4)
# ===================================================================
class TestFingerprintNewDefaults:
    """Verify fingerprint with tuned k=5, w=4 defaults."""

    def test_d2_default_jaccard_high(self, file_texts):
        ta = strip_comments(file_texts["left/sqlite3.h"], ".c")
        tb = strip_comments(file_texts["right/sqlite3.h"], ".c")
        fa = {fp.hash_value for fp in extract_fingerprints(ta)}
        fb = {fp.hash_value for fp in extract_fingerprints(tb)}
        j = _jaccard(fa, fb)
        assert j >= 0.98, f"Jaccard with defaults: {j:.4f} (expected ≥ 0.98)"

    def test_d2_more_fingerprints_than_old_defaults(self, file_texts):
        text = strip_comments(file_texts["left/sqlite3.h"], ".c")
        fps_new = extract_fingerprints(text)         # k=5, w=4
        fps_old = extract_fingerprints(text, k=50, w=40)
        assert len(fps_new) > len(fps_old), (
            f"New: {len(fps_new)} vs Old: {len(fps_old)}"
        )


# ===================================================================
# F2: Parser #if 0 handling
# ===================================================================
class TestIfZeroStripping:
    """Verify #if 0 ... #endif block stripping."""

    def test_f2_basic_if0(self):
        code = (
            "int a = 1;\n"
            "#if 0\n"
            "int b = 2;\n"
            "int c = 3;\n"
            "#endif\n"
            "int d = 4;\n"
        )
        stripped = strip_comments(code, ".c")
        assert "int a = 1;" in stripped
        assert "int d = 4;" in stripped
        assert "int b = 2;" not in stripped
        assert "int c = 3;" not in stripped

    def test_f2_line_count_preserved(self):
        code = "a\n#if 0\nb\nc\n#endif\nd\n"
        stripped = strip_comments(code, ".c")
        assert code.count("\n") == stripped.count("\n")

    def test_f2_nested_if(self):
        code = (
            "int a;\n"
            "#if 0\n"
            "#if 1\n"
            "int dead;\n"
            "#endif\n"
            "#endif\n"
            "int alive;\n"
        )
        stripped = strip_comments(code, ".c")
        assert "int a;" in stripped
        assert "int alive;" in stripped
        assert "int dead;" not in stripped

    def test_f2_sqlite_if0_count(self, file_texts):
        import re
        text = file_texts["left/sqlite3.c"]
        if0_count = len(re.findall(r"^\s*#\s*if\s+0\s*$", text, re.MULTILINE))
        stripped = strip_comments(text, ".c")
        assert text.count("\n") == stripped.count("\n")
        if if0_count > 0:
            assert len(stripped) < len(text), (
                f"Found {if0_count} #if 0 blocks but stripped is not smaller"
            )
