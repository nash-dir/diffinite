# Changelog

## [0.13.1] — 2026-06-23

### Docs

- Extension README: updated Normalize option description to document the calibrated threshold (93) and 45-token inconclusive band; corrected "Content Match" → "Line match (difflib)" in the Cover Page table; added Inconclusive column to the Deep Compare table; corrected Threshold (Deep) default to reflect channel-dependent behaviour.

## [0.13.0] — 2026-06-23

### Added

- **Measured normalize false-positive rate.** `--normalize` (identifier flattening) collapses small, standard code onto identical fingerprints, so independent work and renamed copies can score the same. A validation harness (`tests/validation/error_rate.py`, run via `python -m tests.validation.error_rate`) now measures precision/recall per file pair on the Karnalim IR-Plag corpus and commits the evidence under `example/validation/`. Every `--normalize` report discloses its measured false-positive rate — with the Wilson confidence interval, the per-level recall (near-verbatim only), and the small-file scope — so a flagged match is not read as a known copy verdict.
- **Calibrated normalize operating point.** Under `--normalize`, `--threshold-deep` now defaults to **93** (calibrated for false-positive ≤ 1%) instead of 5, and matches whose smaller file is below a 45-token floor are reported as **inconclusive** rather than confident findings. The raw (non-normalize) default stays 5.
- **`--lang-aware`** (opt-in): language-aware normalization via Pygments lexers (falling back to per-language keyword sets) so keywords like Rust `fn`/`pub` or Go `func` are preserved instead of flattened to `ID`, reducing false positives on non-JVM/Python/JS languages.
- **Unicode/i18n example** (`example/unicode`) and end-to-end coverage for non-ASCII filenames, CJK/Cyrillic/Arabic content, and emoji.

### Changed

- The "Content Match" headline is relabelled **"Line match (difflib)"** across all report formats, and the difflib `autojunk` state is now shown in every Analysis Configuration banner — the figure is a line-level difflib ratio, not semantic similarity.
- A deep-compare file-size cap (`--max-file-size`) now also bounds fingerprint extraction, so an untrusted large/pathological file cannot hang a run.

### Fixed

- Resolved dormant type-hint/import issues, an `AnalysisMetadata` field-order hazard, and a library entry point that omitted the normalize disclosure.

## [0.12.2] — 2026-06-22

### Fixed

- **Report labels — filename vs. content similarity**: every report format now shows filename similarity and content match as two clearly-labelled, distinct figures, so a 100% filename match is no longer mistaken for identical file content. The CSV exhibit index gains a `Content Match (%)` column alongside `Name Sim. (%)`; the Markdown summary, HTML evidence index, and per-file diff pages are relabelled consistently; binary pairs report their SHA-256 match status. (The PDF cover and JSON report already separated the two values.)

### Docs

- Corrected and expanded both READMEs: comment-stripping coverage (45+ extensions, derived from the language registry), previously-undocumented CLI flags, a PDF Font / CJK rendering section, and the `diffinite.pdfLang` / `diffinite.pdfFont` settings. Fixed the extension README's FSM state count, broken `master` license links, and the default deep-threshold value.

### Chore

- `.gitignore` now ignores generated CLI report outputs left in the `example/` root.

## [0.12.1] — 2026-06-17

### Security

- **Webview hardening**: every webview (options panel, result viewer, tree viewer) now sets a strict Content-Security-Policy with a per-render nonce, closing the script-injection surface. Rendered `html_diff` is backend-escaped and CSP-protected.

### Fixed

- **Cancellation, temp files, argument passing**: in-flight analysis/export processes are reliably terminated on cancel and temporary working files are cleaned up; hardened how analysis options and temp paths are forwarded to the bundled Python backend.

### Changed

- **Supply-chain hardened bundle build**: `build_bundle.ps1` now installs the embedded-Python dependencies from a pinned, hash-verified `requirements-bundle.lock` via `pip install --require-hashes`, with SHA-256 verification of the Python embeddable zip and `get-pip.py`.
- **Smaller VSIX**: the bundle prune step is fixed (it previously pruned nothing) and now runs last; `pip-licenses` is built in a throwaway directory instead of shipping into the runtime, dropping ~12 MB of `__pycache__`/`.pyc` and build-only packages.

### Docs

- Added a Platform Support matrix to the README; the embedded-Python runtime is scoped to Windows (macOS/Linux use system Python via the CLI).

## [0.12.0] — 2026-03-31

### Added

- **Parallel execution**: multi-process Phase-2 rendering for faster reports on large selections.
- **Persistent Options Panel**: the options panel remembers the last run's settings and directories.

### Fixed

- **CJK font rendering** in PDF output.

## [0.11.1] — 2026-03-28

### Fixed

- **CI/CD Pipeline**: Restore pytest across Python 3.10–3.13, add `libcairo2-dev` for Ubuntu runner, fix `vsce --dry-run` removal (unsupported in v3.x), unify release.yml to `pwsh`.
- **Tests**: Update `TestBreakPath` assertions to match CSS-based word wrapping (no more `<wbr>` tags).
- **Tests restored to repo**: 18 test files re-added with `skipif` guards for external-data tests.

### Changed

- **VSCE README**: Document progress bar, OOM defense, time estimation, SHA-256, encoding, uncompared modes, embedded Python runtime.
- **PyPI metadata**: Expand keywords for better discoverability (side-by-side, similarity, jaccard, copyright, litigation, vscode).
- **CI dependency chain**: VSCode Bundle job now requires all pytest jobs to pass first (`needs: test`).

## [0.11.0] — 2026-03-28

### Added

- **Real-time Progress Bar**: Python backend stdout (`[Worker-N] X/Y`) is parsed and fed into VS Code's native progress API for live percentage tracking.
- **Pre-analysis Time Estimation**: `dirScanner.ts` scans file sizes upfront and estimates Simple/Deep mode duration before analysis begins.
- **Dynamic CPU Calibration**: Phase 1 execution time is benchmarked to calibrate Phase 2 rendering time predictions (clamped 0.2x–5.0x).
- **OOM Defense**: Warns users when file pairs exceed 5MB, preventing silent crashes on large binary/generated files.
- **Uncompared File Modes**: `--uncompared-mode {inline,separate,none}` controls how unmatched files appear in reports.
- **Evidence Integrity Hashes**: `--hash` flag embeds SHA-256 hashes for all analyzed files directly in the report.
- **JSON Report Output**: `--report-json` for machine-readable output consumed by the VS Code extension tree viewer.
- **Default Export Filename**: Save dialog now defaults to `{dirA}_{dirB}_{timestamp}` pattern.

### Fixed

- **PDF Table Layout**: Removed `xhtml2pdf` shrink mode that minified fonts; applied `table-layout: fixed` with explicit column width weights.
- **PDF Word Wrap**: Replaced broken `<wbr>` hack with `pdf-word-wrap: CJK` for reliable long-path wrapping across all tables, lists, and body text.
- **Column Width Distribution**: Summary (4%/#, 34%/FileA, 34%/FileB, 8%/NameSim, 10%/Match, 5%/Added, 5%/Deleted), Deep Compare (40%/40%/10%/10%), Hash Evidence (5%/60%/20%/15%).

## [0.9.3] — 2026-03-18

### Added

- **Moved Block Detection**: `--detect-moved` flag detects code blocks that were moved (not just added/deleted) and highlights them in purple (original position) and blue (destination).
- **Bates Prefix / Suffix / Starting Number**: `--bates-prefix`, `--bates-suffix`, `--bates-start` CLI flags for customizable Bates labels (e.g. `PLAINTIFF-0001-CONFIDENTIAL`). Font auto-shrinks when label exceeds 30 characters.
- **Bates Presets (VSCode)**: Save case-specific Bates configurations in `settings.json` as `diffinite.batesPresets`. Select a preset in the GUI to auto-fill prefix/suffix/start fields.
- **Options Panel**: New fields for Detect Moved, Bates Prefix, Suffix, Starting Number, and Preset dropdown.

### Fixed

- Extension now correctly passes `--encoding`, `--sort-by`, `--sort-order`, and `--detect-moved` to CLI.
- Dark-mode CSS for moved-block highlighting in diff viewer.

## [0.6.0] — 2026-03-18

### Added

- Initial Marketplace release (version synced with PyPI)
- **Compare Directories** command with GUI options panel
- Scrollable block-by-block diff viewer
- Report export (PDF / HTML / Markdown)
- Configurable analysis options: mode, comment stripping, normalization, thresholds
- Bundled binary resolution with Python fallback
