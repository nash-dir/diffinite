# Changelog

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
