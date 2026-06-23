# Diffinite — Source Code Comparison

Forensic source-code comparison tool for **IP litigation and code audit**, available as a VS Code extension with zero-install embedded Python runtime.

Compare two directories of source code with [Winnowing fingerprints](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf) (Schleimer et al., 2003 — the algorithm behind [Stanford MOSS](https://theory.stanford.edu/~aiken/moss/)) and generate professional PDF/HTML/Markdown reports — all from within VS Code.

> **Design Principle**: Diffinite reports **how similar** and **where similar**. It does not classify the type of copying — that is the expert witness's job.

![sample report](https://raw.githubusercontent.com/nash-dir/diffinite/master/docs/report-sample.png)

![diff page](https://raw.githubusercontent.com/nash-dir/diffinite/master/docs/report-diff-sample.png)

---

## Features

### Core Analysis
- **1:1 File Matching** — Pairs files across two directories using fuzzy name matching, then computes line-by-line or word-by-word diffs with syntax highlighting.
- **N:M Cross-Matching (Deep Mode)** — Winnowing fingerprint-based Jaccard similarity across all file pairs. Detects code reuse even across renamed, split, or merged files.
- **Comment Stripping** — 6-state FSM parser supporting 45+ file extensions (`.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.go`, `.rs`, `.swift`, `.rb`, `.php`, `.sql`, `.html`, `.css`, and more).
- **Moved Block Detection** — Detects code blocks that were moved (not just added/deleted) and highlights them in purple (original position) and blue (moved destination).
- **SHA-256 Evidence Integrity** — Embeds cryptographic hashes for all analyzed files directly in the report for forensic chain-of-custody.

### VS Code Integration
- **Real-time Progress Bar** — Live percentage tracking during analysis, fed from Python backend stdout.
- **Pre-analysis Time Estimation** — Scans file sizes upfront and estimates Simple/Deep mode duration before committing to analysis.
- **Dynamic CPU Calibration** — Benchmarks Phase 1 performance to refine Phase 2 time predictions for the current machine.
- **OOM Defense** — Warns before analyzing file pairs exceeding 5MB, preventing silent crashes on large binary/generated files.
- **Interactive Tree Viewer** — Review matched pairs and selectively choose which files to include in the final report.
- **Multiple Report Formats** — Export to PDF, HTML, Markdown, or JSON.
- **Forensic Annotations** — Page numbers, file numbers, Bates stamps (with configurable prefix/suffix/start number), filenames on every page.
- **Bates Presets** — Save case-specific Bates configurations as reusable presets in VS Code settings.
- **GUI Options Panel** — Configure all analysis parameters visually without touching the CLI.
- **Embedded Python Runtime** — Windows builds ship with bundled Python 3.12; no separate Python installation required.

---

## Usage

1. Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Run **"Diffinite: Compare Directories"**
3. Select the original directory (A) and comparison directory (B)
4. Configure options in the GUI panel (mode, thresholds, comment stripping, etc.)
5. Review matched pairs in the interactive tree viewer
6. Export your report (PDF/HTML/Markdown) with one click

---

## How It Works

Diffinite runs a two-stage pipeline:

### Stage 1: 1:1 File Matching (`simple` mode)

1. **Fuzzy name matching** — Pairs files across directories using string similarity (configurable threshold).
2. **Comment stripping** — Optionally removes comments using a 6-state finite state machine parser.
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
| **Name Sim.** | Fuzzy filename similarity score (0–100) |
| **Line match (difflib)** | `SequenceMatcher.ratio()` — proportion of matching lines (`1.0` = identical) |
| **Added / Deleted** | Lines added to or deleted from File A to produce File B |

### Diff Pages

Side-by-side diff for each matched pair:
- 🟢 **Green** — Lines present only in File B (additions)
- 🔴 **Red** — Lines present only in File A (deletions)
- 🟡 **Yellow** — Lines changed between A and B (word-level diff in `--by-word` mode)
- 🟣 **Purple** — Lines moved from this position (with `--detect-moved`)
- 🔵 **Blue** — Lines moved to this position (with `--detect-moved`)
- No highlight — Identical lines (with configurable context folding)

### Deep Compare Section

N:M cross-matching table (deep mode):

| Column | Description |
|--------|-------------|
| **File A** | Source file from directory A |
| **Matched Files (B)** | All B-files sharing fingerprints above the Jaccard threshold |
| **Shared Hashes** | Count of Winnowing fingerprints the file pair has in common |
| **Jaccard** | `\|A∩B\| / \|A∪B\|` — fraction of shared Winnowing fingerprints |
| **Inconclusive** | Shown when Normalize is on and the smaller file is below 45 tokens — precision is unsalvageable at that size |

---

## Extension Settings

| Setting | Default | Description |
|---------|:-------:|-------------|
| `diffinite.pythonPath` | `python` | Path to Python interpreter (ignored when bundled runtime is available) |
| `diffinite.defaultMode` | `deep` | Default execution mode (`simple` or `deep`) |
| `diffinite.workers` | `4` | Number of CPU cores for parallel diff rendering |
| `diffinite.noMerge` | `false` | Save individual reports per file instead of one merged PDF |
| `diffinite.preserveTree` | `true` | Preserve directory tree structure in individual output |
| `diffinite.pdfLang` | `ko` | Language for CJK font resolution in PDF output (`ko`, `ja`, `zh-cn`, `en`). Auto-resolves the best OS-installed font. |
| `diffinite.pdfFont` | (empty) | Absolute path to a `.ttf`/`.otf` font to embed in the PDF. Overrides `pdfLang`. Leave empty to use built-in CJK fonts. |
| `diffinite.batesPresets` | `[]` | Saved Bates presets (prefix/suffix/start number per case) |

> **CJK / Unicode**: Korean, Japanese, and Chinese source code renders correctly in PDF and HTML reports. The `pdfLang` setting (default `ko`) picks an appropriate OS font for PDF output; HTML uses the browser's native font fallback.

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
| **Normalize** | off | Normalize identifiers → `ID`, literals → `LIT` before fingerprinting (Type-2 clone detection). When enabled, the deep threshold defaults to **93** (calibrated for FP ≤ 1%). Matches below a 45-token floor are marked *inconclusive*. |
| **Collapse Identical** | off | Fold unchanged blocks (3 context lines) |
| **Detect Moved Blocks** | off | Highlight moved code in purple/blue instead of plain delete/add |
| **No Autojunk** | off | Disable autojunk heuristic for more precise forensic analysis |
| **Hash (SHA-256)** | off | Embed evidence integrity hashes in the report |
| **Encoding** | `auto` | Force file encoding (`euc-kr`, `utf-8`, etc.) or auto-detect |
| **Uncompared Mode** | `inline` | How unmatched files appear: `inline`, `separate`, or `none` |
| **Threshold** | `60` | Fuzzy file-name matching threshold (0–100) |
| **K-gram** | `5` | Winnowing K-gram size (Schleimer 2003 §4.2) |
| **Window** | `4` | Winnowing window size. Detection guarantee: sequences ≥ K+W−1 tokens |
| **Threshold (Deep)** | `5` / `93` | Minimum Jaccard similarity (0–100) to include in results. Default is `5` (raw channel) or **`93`** when Normalize is enabled (calibrated operating point). |
| **Bates Preset** | — | Select a saved preset to auto-fill prefix/suffix/start |
| **Bates Prefix** | (empty) | Prefix for Bates numbering (e.g. `PLAINTIFF-`) |
| **Bates Suffix** | (empty) | Suffix for Bates numbering (e.g. `-CONFIDENTIAL`) |
| **Starting Number** | `1` | First Bates number (auto-continues across reports) |

---

## Requirements

This extension ships with an **embedded Python 3.12 runtime** on Windows — no separate installation required.

For Mac/Linux, Python ≥ 3.10 with diffinite is required:
```bash
pip install diffinite
```

---

## Comment Stripping Support

The **Strip Comments** option removes comments using a 6-state FSM parser covering 45+ file extensions:

| Extensions | Comment Styles |
|------------|---------------|
| `.py`, `.pyw` | `# line` (docstrings preserved) |
| `.js`, `.jsx`, `.mjs`, `.ts`, `.tsx` | `// line`, `/* block */`, template literals, regex literals |
| `.java`, `.kt`, `.kts`, `.scala`, `.c`, `.cc`, `.cpp`, `.h`, `.hpp`, `.cs`, `.go`, `.rs`, `.swift` | `// line`, `/* block */` |
| `.html`, `.htm`, `.xml`, `.svg` | `<!-- block -->` |
| `.css`, `.scss`, `.less` | `/* block */` |
| `.sql`, `.ddl`, `.dml`, `.pks`, `.pkb`, `.plsql`, `.tsql` | `-- line`, `/* block */` |
| `.php` | `// line`, `# line`, `/* block */` |
| `.rb` | `# line`, `=begin … =end` block |
| `.pl`, `.pm`, `.sh`, `.bash`, `.zsh`, `.r`, `.yaml`, `.yml`, `.toml` | `# line` |
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

[Apache License 2.0](https://github.com/nash-dir/diffinite/blob/master/LICENSE)

See [NOTICE](https://github.com/nash-dir/diffinite/blob/master/NOTICE) for attribution.
