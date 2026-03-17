# Diffinite — Source Code Comparison

Forensic source-code comparison tool for **IP litigation and code audit**, now available as a VSCode extension.

Compare two directories of source code with [Winnowing fingerprints](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf) and generate professional PDF/HTML/Markdown reports — all from within VSCode.

> **Design Principle**: Diffinite reports **how similar** and **where similar**. It does not classify the type of copying — that is the expert witness's job.

## Features

- **1:1 File Matching** — Fuzzy name matching + line-by-line / word-by-word diffs
- **N:M Cross-Matching** — Winnowing fingerprint-based Jaccard similarity across all file pairs
- **Comment Stripping** — 5-state FSM parser supporting 30+ file extensions
- **Multiple Report Formats** — PDF, HTML, Markdown
- **Forensic Annotations** — Page numbers, file numbers, Bates stamps, filenames
- **GUI Options Panel** — Configure all analysis parameters without touching the CLI

## Usage

1. Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Run **"Diffinite: Compare Directories"**
3. Select the two directories to compare
4. Configure options in the GUI panel
5. View results in the built-in diff viewer or export a report

## Requirements

This extension requires either:

- **Bundled binary** (included for Windows/Linux/macOS when available), or
- **Python ≥ 3.10** with `diffinite` installed (`pip install diffinite`)

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `diffinite.pythonPath` | `python` | Path to Python interpreter with diffinite installed |
| `diffinite.defaultMode` | `deep` | Default execution mode (`simple` or `deep`) |

## How It Works

### Simple Mode (1:1)
Files are paired by name similarity, then compared line-by-line using `difflib.SequenceMatcher`.

### Deep Mode (N:M)
Every file in directory A is fingerprinted using the Winnowing algorithm, then cross-matched against all files in directory B via an inverted index. Jaccard similarity `|A∩B| / |A∪B|` quantifies shared code.

## License

[Apache License 2.0](https://github.com/nash-dir/diffinite/blob/main/LICENSE)
