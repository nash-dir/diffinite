# Changelog

All notable changes to Diffinite will be documented in this file.

## [Unreleased] — 2026-03-13

### Performance
- **Parser 4.4× speedup** — Replaced `_strip_slow()` with line-based `_strip_2pass()`. Lines without comment markers bypass the character-level state machine entirely.
- **Diff 1,824× speedup** — Switched `difflib.SequenceMatcher` to `autojunk=True`. On 12K-line files, diff completes in 0.01s (was 21s).
- **Diff 255K-line support** — sqlite3.c (255,636 lines) now diffs in ~10s (previously timed out).
- **HTML output 99% reduction** — Context-fold equal-line runs via `context_lines` parameter. sqlite3.h HTML: 10MB → 112KB.
- **Collector O(N) optimization** — Exact-match-first 2-phase strategy. Identical filenames skip O(N²) fuzzy matching.

### Accuracy
- **K-gram tuning** — `DEFAULT_K` changed from 50 → 5, `DEFAULT_W` from 40 → 4. Grid search across SQLite 250K-line and AOSP Java corpora. Jaccard gap reduced from >50pp to <14pp.
- **`#if 0` block removal** — New `_strip_ifdef_zero()` pre-pass for C-family files. Removes dead code blocks while preserving line numbers.
- **Triple-quote bug fix** — `_has_any_marker()` now detects string delimiters (`"`, `'`, `` ` ``), preventing false comment stripping inside Python `"""` strings.

### Features
- **`--squash-blanks` CLI flag** — Collapses 3+ consecutive blank lines after comment stripping. Opt-in only; default behavior preserves original line numbers for forensic traceability.
- **`context_lines` parameter** — `generate_html_diff()` now accepts `context_lines` (default 3) to fold equal-line runs. Set to -1 to disable.

### Internal
- Synchronized `TDD/logic/` with `src/diffinite/` (6 modules).
- Added integration cross-check test (`TDD/test_integration_crosscheck.py`) covering AOSP and SQLite datasets.
