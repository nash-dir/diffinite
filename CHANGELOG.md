# Changelog

All notable changes to Diffinite will be documented in this file.

## [0.3.0] — 2026-03-16

### Deep Compare & Evidence Analysis (Phase 2)
- **6-channel evidence scoring** — raw/normalized/AST Winnowing, identifier cosine, declaration cosine, comment/string overlap. Composite weighted by ROC AUC.
- **2-stage classification** — Strict (zero-FP) + Relaxed (recall補完) → 7-class pattern output (`DIRECT_COPY`, `SSO_COPYING`, `OBFUSCATED_CLONE`, `DOMAIN_CONVERGENCE`, `SUSPICIOUS_COPY`, `SUSPICIOUS_SSO`, `INCONCLUSIVE`).
- **AFC pipeline** — Altai (1992) Abstraction-Filtration-Comparison. Boilerplate/import filtering with inflation-corrected thresholds.
- **IDEX analysis** — Dual-profile Idea-Expression Dichotomy → 5 legal defense patterns.
- **N:M deep cross-matching** — Inverted-index based O(Σ|fp_a|) with parallel fingerprint extraction.
- **AST/PDG normalizer** — tree-sitter based structural tokenization with boilerplate filtering.
- **Language registry** — `languages/` package (13 modules, 30+ extensions). `LangSpec` dataclass + central registry.
- **TF-IDF channels** — Corpus-weighted identifier/declaration/comment cosine scoring.

### TDD Corpus Pipeline (Phase 3)
- **8-stage validation** — IR-Plag L1-L6, 646-pair corpus, domain convergence (Guava↔JDK), negative control (FP −78%), 84K grid search (Precision 95.5%).

### Quality Enhancements (Phase 4)
- **`TOKEN_RE` unification** — Consolidated duplicate tokenizer regex from `fingerprint.py` and `evidence.py`.
- **`ClassificationThresholds` dataclass** — 18-field frozen dataclass replacing `_CLASSIFICATION_PROFILES` dict. Type-safe, IDE-friendly.
- **`IDEXThresholds` dataclass** — 8-field frozen dataclass for legal defense pattern thresholds.
- **`--no-autojunk` CLI** — Disable `SequenceMatcher` junk heuristic for forensic precision.
- **`--max-index-entries` CLI** — Memory cap for inverted index (default 10M, graceful truncation with warning).
- **JS template literal parser** — 5-state machine (`IN_TEMPLATE_LITERAL`) with `template_depth` counter for `${}` nesting.
- **Test count**: 253 passed, 4 skipped.

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

