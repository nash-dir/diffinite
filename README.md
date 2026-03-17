# Diffinite

**Forensic source-code comparison tool for IP litigation and code audit.**

Diffinite compares two directories of source code and produces professional PDF/HTML reports with syntax-highlighted side-by-side diffs. It uses [Winnowing fingerprints](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf) (Schleimer et al., 2003 — the algorithm behind Stanford MOSS) for N:M cross-matching to detect code reuse even across renamed, split, or merged files.

> **Design Principle**: Diffinite reports **how similar** and **where similar**. It does not classify the type of copying — that is the expert witness's job.

---

## Installation

```bash
pip install diffinite
```

Or from source:

```bash
git clone https://github.com/nash-dir/diffinite.git
cd diffinite
pip install -e ".[dev]"
```

**Requirements**: Python ≥ 3.10

**Dependencies**: [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz), [Pygments](https://pygments.org/), [xhtml2pdf](https://github.com/xhtml2pdf/xhtml2pdf), [pypdf](https://github.com/py-pdf/pypdf), [reportlab](https://docs.reportlab.com/), [charset-normalizer](https://github.com/Ousret/charset_normalizer)

---

## Quick Start

```bash
# Compare two directories → PDF report
diffinite original/ suspect/ -o report.pdf

# With comment stripping and Bates numbering (forensic use)
diffinite original/ suspect/ -o report.pdf \
    --no-comments --bates-number --page-number --show-filename

# HTML report (single self-contained file, opens in browser)
diffinite original/ suspect/ --report-html report.html
```

---

## How It Works

Diffinite runs a two-stage pipeline:

### Stage 1: 1:1 File Matching (`simple` mode)

1. **Fuzzy name matching** — Pairs files across `dir_a` and `dir_b` using [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) string similarity (configurable threshold).
2. **Comment stripping** — Optionally removes comments using a 5-state finite state machine parser supporting 30+ file extensions.
3. **Side-by-side diff** — Computes line-by-line (or word-by-word) diffs using Python's `difflib.SequenceMatcher`.
4. **Report generation** — Renders syntax-highlighted HTML diffs via Pygments, then converts to PDF with xhtml2pdf.

### Stage 2: N:M Cross-Matching (`deep` mode, default)

5. **Winnowing fingerprint extraction** — Extracts position-independent code fingerprints using the Winnowing algorithm (K-gram → rolling hash → window selection).
6. **Inverted index construction** — Builds a hash-to-file mapping for all B-directory fingerprints.
7. **Jaccard similarity computation** — For each A-file, queries the index to find all B-files sharing fingerprints, then computes Jaccard similarity `|A∩B| / |A∪B|`.
8. **Cross-match reporting** — Appends an N:M similarity matrix to the report, showing which files from A are similar to which files in B.

---

## Output Report

### Cover Page

The cover page contains a summary table for each matched file pair:

| Column | Description |
|--------|-------------|
| **File A / File B** | Matched file paths |
| **Match** | `difflib.SequenceMatcher.ratio()` — the proportion of matching characters between the two files. `1.0` = identical, `0.0` = completely different. |
| **Added / Deleted** | Number of lines added to or deleted from File A to produce File B. |

### Diff Pages

Each matched pair gets a side-by-side diff page with:

- **Green highlight** — Lines present only in File B (additions)
- **Red highlight** — Lines present only in File A (deletions)
- **No highlight** — Identical lines (with configurable context folding)

### Deep Compare Section

When running in `deep` mode (default), the report includes an N:M cross-matching table:

| Column | Description |
|--------|-------------|
| **File A** | Source file from directory A |
| **Matched Files (B)** | All files from directory B that share fingerprints above the Jaccard threshold |
| **Jaccard** | `|A∩B| / |A∪B|` — the fraction of shared Winnowing fingerprints. A Jaccard of `0.73` means 73% of the code fingerprints are shared between the two files. |

### Understanding Jaccard Similarity

| Jaccard | Interpretation |
|:-------:|----------------|
| **0.80 – 1.00** | Very high overlap. Near-identical code or copy with minor edits. |
| **0.50 – 0.79** | Substantial overlap. Significant shared code structure. |
| **0.20 – 0.49** | Moderate overlap. Some shared patterns — could be common idioms or partial reuse. |
| **0.05 – 0.19** | Low overlap. Likely coincidental similarity or shared libraries. |
| **< 0.05** | Noise. Not reported (below default `--threshold-deep`). |

> **Note**: These ranges are descriptive guidelines, not classifications. Diffinite does not make legal judgments about the nature of any similarity.

### Page Annotations

| Option | Annotation | Position |
|--------|-----------|----------|
| `--page-number` | `Page 3 / 47` | Bottom-right |
| `--file-number` | `File 2 / 12` | Bottom-left |
| `--bates-number` | `DIFF-000003` | Bottom-center |
| `--show-filename` | `com/example/Foo.java` | Top-right |

---

## CLI Reference

### Positional Arguments

```
dir_a    Path to the original source directory (A)
dir_b    Path to the comparison source directory (B)
```

### Execution Mode

| Option | Default | Description |
|--------|:-------:|-------------|
| `--mode {simple,deep}` | `deep` | `simple` = 1:1 file matching only. `deep` = 1:1 + N:M Winnowing cross-matching. |

### Output Options

| Option | Description |
|--------|-------------|
| `-o`, `--output-pdf PATH` | Output PDF path (default: `report.pdf`). Ignored when `--report-*` is specified. |
| `--report-pdf PATH` | Generate merged PDF report |
| `--report-html PATH` | Generate standalone HTML report (single file, no external deps) |
| `--report-md PATH` | Generate Markdown summary report |
| `--no-merge` | Generate individual PDFs per file instead of one merged PDF |

### Diff Options

| Option | Default | Description |
|--------|:-------:|-------------|
| `--no-comments` | off | Strip comments before comparison (5-state FSM parser, 30+ extensions) |
| `--by-word` | off | Compare by word instead of by line |
| `--squash-blanks` | off | Collapse runs of 3+ blank lines. ⚠️ Changes line numbers — not recommended for forensic line-tracing. |
| `--threshold N` | `60` | Fuzzy file-name matching threshold (0–100). Lower = more aggressive matching. |
| `--collapse-identical` | off | Fold unchanged code blocks (3 context lines around each change) |

### Deep Compare Options

| Option | Default | Description |
|--------|:-------:|-------------|
| `--k-gram N` | `5` | K-gram size for Winnowing. Larger K = fewer but more specific fingerprints. (Schleimer 2003, §4.2) |
| `--window N` | `4` | Winnowing window size. Guarantees detection of any shared sequence ≥ `K+W−1` = 8 tokens. |
| `--threshold-deep F` | `0.05` | Minimum Jaccard similarity to include in results. Below 5% is considered noise. |
| `--normalize` | off | Normalize identifiers → `ID`, literals → `LIT` before fingerprinting. Improves Type-2 clone detection (renamed variables). |
| `--workers N` | `4` | Number of parallel worker processes for fingerprint extraction. |

### Forensic Options

| Option | Default | Description |
|--------|:-------:|-------------|
| `--no-autojunk` | off | Disable `SequenceMatcher`'s autojunk heuristic. Treats all tokens equally — slower but more precise for forensic analysis. |
| `--max-index-entries N` | `10,000,000` | Memory cap for inverted index. Prevents OOM on large corpora. ~800MB at 10M entries. |

### Page Annotation Options

| Option | Description |
|--------|-------------|
| `--page-number` | Show `Page n / N` at the bottom-right |
| `--file-number` | Show `File n / N` at the bottom-left |
| `--bates-number` | Stamp sequential Bates numbers at the bottom-center |
| `--show-filename` | Show filename at the top-right |

---

## Usage Examples

### Basic IP Litigation Report

```bash
# Full forensic report with all annotations
diffinite plaintiff_code/ defendant_code/ -o exhibit_A.pdf \
    --no-comments \
    --bates-number --page-number --file-number --show-filename \
    --collapse-identical
```

### Code Audit (Quick HTML)

```bash
# HTML report for browser viewing (no PDF dependency issues)
diffinite vendor_v1/ vendor_v2/ --report-html audit.html --no-comments
```

### Maximum Sensitivity (Type-2 Clones)

```bash
# Detect renamed-variable copies
diffinite original/ suspect/ -o report.pdf \
    --normalize --no-autojunk --no-comments
```

### Simple Mode (Fast, No Cross-Matching)

```bash
# 1:1 matching only — faster for quick comparisons
diffinite dir_a/ dir_b/ --mode simple -o quick_report.pdf
```

### Multiple Output Formats

```bash
# Generate all three formats at once
diffinite dir_a/ dir_b/ \
    --report-pdf report.pdf \
    --report-html report.html \
    --report-md report.md
```

### Tuning Sensitivity

```bash
# Larger K-gram = fewer false positives, may miss short matches
diffinite dir_a/ dir_b/ --k-gram 7 --window 5

# Lower Jaccard threshold = show weaker matches
diffinite dir_a/ dir_b/ --threshold-deep 0.02

# Stricter file name matching
diffinite dir_a/ dir_b/ --threshold 80
```

---

## Comment Stripping Support

The `--no-comments` flag removes comments using a 5-state finite state machine parser:

| Extensions | Comment Styles |
|------------|---------------|
| `.py` | `# line comments`, `"""docstrings"""` |
| `.js`, `.ts`, `.jsx`, `.tsx` | `// line`, `/* block */`, `` `template literals` `` |
| `.java`, `.c`, `.cpp`, `.h`, `.cs`, `.go`, `.rs`, `.kt`, `.scala` | `// line`, `/* block */` |
| `.html`, `.xml`, `.svg`, `.htm` | `<!-- block -->` |
| `.css`, `.scss`, `.less` | `/* block */` |
| `.sql` | `-- line`, `/* block */` |
| `.rb` | `# line` |
| `.sh`, `.bash`, `.zsh` | `# line` |
| `.lua` | `-- line`, `--[[ block ]]` |
| `.r` | `# line` |

---

## Project Structure

```
diffinite/
├── src/diffinite/
│   ├── cli.py              # CLI entry point & argument parsing
│   ├── pipeline.py         # Orchestration (simple/deep modes)
│   ├── collector.py        # File collection & fuzzy name matching
│   ├── parser.py           # 5-state comment stripping FSM
│   ├── differ.py           # Diff computation & HTML rendering
│   ├── fingerprint.py      # Winnowing fingerprint extraction
│   ├── deep_compare.py     # N:M cross-matching (inverted index)
│   ├── evidence.py         # Jaccard similarity metric
│   ├── models.py           # Data classes
│   ├── pdf_gen.py          # PDF/HTML report generation
│   └── languages/          # Per-language specs (30+ extensions)
├── tests/                  # 216 tests
├── example/                # Example source code for testing
├── AGENTS.md               # AI agent development guidelines
├── pyproject.toml
├── LICENSE                 # Apache 2.0
└── NOTICE
```

---

## Winnowing Algorithm

Diffinite uses the **Winnowing** algorithm (Schleimer, Wilkerson, Aiken. *"Winnowing: Local Algorithms for Document Fingerprinting."* SIGMOD 2003) — the same algorithm that powers [Stanford MOSS](https://theory.stanford.edu/~aiken/moss/).

**Pipeline**: `source → tokenize → K-gram → rolling hash → winnow → fingerprint set`

The algorithm provides a **density guarantee**: any shared token sequence of length ≥ `K + W − 1` (default: 8) will always be detected, regardless of its position in the file.

**Parameters**:

| Parameter | Default | Rationale |
|-----------|:-------:|-----------|
| `K` (k-gram) | `5` | Schleimer 2003 §4.2 recommended range. 5 consecutive tokens per fingerprint unit. |
| `W` (window) | `4` | Window of 4 fingerprints → minimum detectable sequence = 8 tokens. |
| `HASH_BASE` | `257` | Standard Rabin hash base (prime). |
| `HASH_MOD` | `2⁶¹ − 1` | Mersenne prime — efficient modular arithmetic, minimal collision probability. |

---

## License

[Apache License 2.0](LICENSE)

See [NOTICE](NOTICE) for attribution.
