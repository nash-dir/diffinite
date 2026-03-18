# Changelog

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
