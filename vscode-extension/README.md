# Diffinite — Source Code Comparison

Forensic source-code comparison tool for **IP litigation and code audit**, now available as a VSCode extension.

Compare two directories of source code with [Winnowing fingerprints](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf) (Schleimer et al., 2003 — the algorithm behind [Stanford MOSS](https://theory.stanford.edu/~aiken/moss/)) and generate professional PDF/HTML/Markdown reports — all from within VSCode.

> **Design Principle**: Diffinite reports **how similar** and **where similar**. It does not classify the type of copying — that is the expert witness's job.

---

## Features

- **1:1 File Matching** — Pairs files across two directories using fuzzy name matching, then computes line-by-line or word-by-word diffs with syntax highlighting.
- **N:M Cross-Matching (Deep Mode)** — Winnowing fingerprint-based Jaccard similarity across all file pairs. Detects code reuse even across renamed, split, or merged files.
- **Comment Stripping** — 5-state FSM parser supporting 30+ file extensions (`.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.go`, `.rs`, `.rb`, `.sql`, `.html`, `.css`, and more).
- **Moved Block Detection** — Detects code blocks that were moved (not just added/deleted) and highlights them in purple (original position) and blue (moved destination).
- **Multiple Report Formats** — Export to PDF, HTML, or Markdown.
- **Forensic Annotations** — Page numbers, file numbers, Bates stamps (with configurable prefix/suffix/start number), filenames on every page.
- **Bates Presets** — Save case-specific Bates configurations (prefix, suffix, starting number) as reusable presets in VSCode settings.
- **GUI Options Panel** — Configure all analysis parameters visually without touching the CLI.
- **Bundled Binary Support** — Ships with standalone binaries when available; falls back to Python if needed.

---

## Usage

1. Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Run **"Diffinite: Compare Directories"**
3. Select the original directory (A) and comparison directory (B)
4. Configure options in the GUI panel (mode, thresholds, comment stripping, etc.)
5. View results in the built-in diff viewer or export a report

---

## How It Works

Diffinite runs a two-stage pipeline:

### Stage 1: 1:1 File Matching (`simple` mode)

1. **Fuzzy name matching** — Pairs files across directories using string similarity (configurable threshold).
2. **Comment stripping** — Optionally removes comments using a 5-state finite state machine parser.
3. **Side-by-side diff** — Computes line-by-line (or word-by-word) diffs using `difflib.SequenceMatcher`.
4. **Report generation** — Renders syntax-highlighted HTML diffs via Pygments, converts to PDF with xhtml2pdf.

### Stage 2: N:M Cross-Matching (`deep` mode, default)

5. **Winnowing fingerprint extraction** — Extracts position-independent code fingerprints (K-gram → rolling hash → window selection).
6. **Inverted index construction** — Builds a hash-to-file mapping for all B-directory fingerprints.
7. **Jaccard similarity computation** — For each A-file, computes `|A∩B| / |A∪B|` against all B-files sharing fingerprints.
8. **Cross-match reporting** — Appends an N:M similarity matrix showing which files from A are similar to which files in B.

---

## Output Report

### Cover Page

Summary table for each matched file pair:

| Column | Description |
|--------|-------------|
| **File A / File B** | Matched file paths |
| **Match** | `SequenceMatcher.ratio()` — proportion of matching characters (`1.0` = identical) |
| **Added / Deleted** | Lines added to or deleted from File A to produce File B |

### Diff Pages

Side-by-side diff for each matched pair:
- 🟢 **Green** — Lines present only in File B (additions)
- 🔴 **Red** — Lines present only in File A (deletions)
- 🟣 **Purple** — Lines moved from this position (with `--detect-moved`)
- 🔵 **Blue** — Lines moved to this position (with `--detect-moved`)
- No highlight — Identical lines (with configurable context folding)

### Deep Compare Section

N:M cross-matching table (deep mode):

| Column | Description |
|--------|-------------|
| **File A** | Source file from directory A |
| **Matched Files (B)** | All B-files sharing fingerprints above the Jaccard threshold |
| **Jaccard** | `|A∩B| / |A∪B|` — fraction of shared Winnowing fingerprints |

---

## Extension Settings

| Setting | Default | Description |
|---------|:-------:|-------------|
| `diffinite.pythonPath` | `python` | Path to Python interpreter with diffinite installed |
| `diffinite.defaultMode` | `deep` | Default execution mode (`simple` or `deep`) |
| `diffinite.batesPresets` | `[]` | Saved Bates presets (prefix/suffix/start number per case). Example in `settings.json`: |

```json
{
  "diffinite.batesPresets": [
    { "name": "Oracle v. Google", "prefix": "GOOG-", "suffix": "-HIGHLY_CONF", "nextBatesNumber": 1 },
    { "name": "Internal Audit Q1", "prefix": "AUDIT-", "suffix": "" }
  ]
}
```

### GUI Options Panel

All options are configurable through the built-in GUI panel:

| Option | Default | Description |
|--------|:-------:|-------------|
| **Mode** | `deep` | `simple` = 1:1 only. `deep` = 1:1 + N:M cross-matching |
| **Strip Comments** | off | Remove comments before comparison |
| **By Word** | off | Compare by word instead of by line |
| **Normalize** | off | Normalize identifiers/literals for Type-2 clone detection |
| **Collapse Identical** | off | Fold unchanged blocks (3 context lines) |
| **Detect Moved Blocks** | off | Highlight moved code in purple/blue instead of plain delete/add |
| **No Autojunk** | off | Disable autojunk heuristic for more precise forensic analysis |
| **Threshold** | `60` | Fuzzy file-name matching threshold (0–100) |
| **K-gram** | `5` | Winnowing K-gram size (Schleimer 2003 §4.2) |
| **Window** | `4` | Winnowing window size. Detection guarantee: sequences ≥ K+W−1 tokens |
| **Threshold (Deep)** | `0.05` | Minimum Jaccard similarity to include in results |
| **Bates Preset** | — | Select a saved preset to auto-fill prefix/suffix/start |
| **Bates Prefix** | (empty) | Prefix for Bates numbering (e.g. `PLAINTIFF-`) |
| **Bates Suffix** | (empty) | Suffix for Bates numbering (e.g. `-CONFIDENTIAL`) |
| **Starting Number** | `1` | First Bates number (auto-continues across reports) |

---

## Requirements

This extension requires either:

- **Bundled binary** (included for Windows / Linux / macOS when available), or
- **Python ≥ 3.10** with diffinite installed:
  ```bash
  pip install diffinite
  ```

---

## Comment Stripping Support

The **Strip Comments** option removes comments using a 5-state FSM parser:

| Extensions | Comment Styles |
|------------|---------------|
| `.py` | `# line`, `"""docstrings"""` |
| `.js`, `.ts`, `.jsx`, `.tsx` | `// line`, `/* block */`, `` `template literals` `` |
| `.java`, `.c`, `.cpp`, `.h`, `.cs`, `.go`, `.rs`, `.kt`, `.scala` | `// line`, `/* block */` |
| `.html`, `.xml`, `.svg` | `<!-- block -->` |
| `.css`, `.scss`, `.less` | `/* block */` |
| `.sql` | `-- line`, `/* block */` |
| `.rb`, `.sh`, `.bash`, `.r` | `# line` |
| `.lua` | `-- line`, `--[[ block ]]` |

---

> 📊 Benchmark results and dataset rationale → [see GitHub README](https://github.com/nash-dir/diffinite#benchmarks)

---

## Limitations

- **General-purpose tokenizer** — Uses a single regex tokenizer, not language-specific parsers.
- **Position-independent** — Reordered functions may produce higher similarity than expected.
- **No corpus-wide weighting** — Pairwise comparison only; no TF-IDF to down-weight common idioms.
- **Not a legal opinion** — Similarity scores are mathematical measurements, not legal conclusions.

---

## License

[Apache License 2.0](https://github.com/nash-dir/diffinite/blob/main/LICENSE)

See [NOTICE](https://github.com/nash-dir/diffinite/blob/main/NOTICE) for attribution.
