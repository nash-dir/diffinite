# Diffinite

**Source-code comparison tool for code audit and similarity analysis.**

Diffinite compares two directories of source code and produces professional PDF/HTML reports with syntax-highlighted side-by-side diffs. It uses [Winnowing fingerprints](https://theory.stanford.edu/~aiken/publications/papers/sigmod03.pdf) (Schleimer et al., 2003 — the algorithm that also forms the basis of [Stanford MOSS](https://theory.stanford.edu/~aiken/moss/)) for N:M cross-matching to detect code reuse even across renamed, split, or merged files.

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
- **Purple highlight** — Lines moved from this position (`--detect-moved`)
- **Blue highlight** — Lines moved to this position (`--detect-moved`)
- **No highlight** — Identical lines (with configurable context folding)

### Deep Compare Section

When running in `deep` mode (default), the report includes an N:M cross-matching table:

| Column | Description |
|--------|-------------|
| **File A** | Source file from directory A |
| **Matched Files (B)** | All files from directory B that share fingerprints above the Jaccard threshold |
| **Jaccard** | `|A∩B| / |A∪B|` — the fraction of shared Winnowing fingerprints. A Jaccard of `0.73` means 73% of the code fingerprints are shared between the two files. |

Jaccard similarity is a well-defined set metric: `|A∩B| / |A∪B|`. Its interpretation depends on the domain, code size, and language. Diffinite reports the raw value without attaching qualitative labels.

### Page Annotations

| Option | Annotation | Position |
|--------|-----------|----------|
| `--page-number` | `Page 3 / 47` | Bottom-right |
| `--file-number` | `File 2 / 12` | Bottom-left |
| `--bates-number` | `TEST-000003-CONF` | Bottom-center |
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
| `--detect-moved` | off | Detect moved code blocks and highlight with distinct colors (purple=original, blue=destination) |

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
| `--bates-prefix TEXT` | Bates number prefix (e.g. `PLAINTIFF-`). Combined as: `{prefix}{number}{suffix}` |
| `--bates-suffix TEXT` | Bates number suffix (e.g. `-CONFIDENTIAL`) |
| `--bates-start N` | Starting Bates number (default: `1`). Useful for continuing numbering across reports. |
| `--show-filename` | Show filename at the top-right |

---

## Usage Examples

### Basic IP Litigation Report

```bash
# Full forensic report with all annotations
diffinite plaintiff_code/ defendant_code/ -o exhibit_A.pdf \
    --no-comments \
    --bates-number --bates-prefix "CASE2026-" --bates-suffix "-CONFIDENTIAL" \
    --bates-start 1 --page-number --file-number --show-filename \
    --collapse-identical --detect-moved
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
├── tests/
├── example/                # Benchmark datasets (see below)
├── AGENTS.md               # AI agent development guidelines
├── pyproject.toml
├── LICENSE                 # Apache 2.0
└── NOTICE
```

---

## Benchmarks

Download the example datasets first, then run the benchmarks yourself:

```bash
python example/download_examples.py          # download all datasets
python example/download_examples.py --dataset aosp  # or download one
```

Pre-generated benchmark reports (Markdown) are in `example/benchmark/`.

### 1. Google v. Oracle — API Header Similarity

**Why this dataset**: The [Oracle v. Google](https://en.wikipedia.org/wiki/Google_LLC_v._Oracle_America,_Inc.) case is the landmark SSO (Structure, Sequence, Organization) copyright dispute. Google's Android reimplemented Java API declarations. The code *bodies* are independently written, but the API *signatures* are necessarily similar.

```bash
diffinite example/Case-Oracle/AOSP_Google example/Case-Oracle/OpenJDK_Oracle \
    --no-comments --report-md example/benchmark/case_oracle.md
```

| File | Match (difflib) | Jaccard (Winnowing) |
|------|:-:|:-:|
| `ArrayList.java` | 9.0% | 7.3% |
| `Collections.java` | 4.5% | — |
| `String.java` | 3.3% | 7.3% |

**Observation**: Low Match and Jaccard scores confirm these are **independent implementations** of the same API specification. The shared fingerprints come from identical method signatures, not copied logic.

### 2. Eclipse Collections v. OpenJDK — Negative Control

**Why this dataset**: Eclipse Collections and OpenJDK solve similar problems (collection frameworks) but are developed by different teams with no code sharing. This is the **expected baseline for independent work** in the same domain.

```bash
diffinite example/Case-NegativeControl/Eclipse_Collections example/Case-NegativeControl/OpenJDK \
    --no-comments --report-md example/benchmark/case_negative.md
```

| File A | File B | Match | Jaccard |
|--------|--------|:-:|:-:|
| `StringIterate.java` | `String.java` | 2.4% | — |
| `FastList.java` | `ArrayList.java` | 1.5% | — |

**Observation**: No cross-matches above the 5% Jaccard threshold. This is the correct result — independent projects should show near-zero similarity.

### 3. IR-Plag Case 01 — Known Plagiarism

**Why this dataset**: [IR-Plag](https://github.com/oscarkarnalim/sourcecodeplagiarismdataset) is a publicly available plagiarism corpus with labeled modification levels (L1=verbatim copy through L6=heavy restructuring).

```bash
diffinite example/plagiarism/case-01/original example/plagiarism/case-01/plagiarized \
    --normalize --no-comments --report-md example/benchmark/plagiarism_case01.md
```

| Original | Plagiarized | Jaccard |
|----------|-------------|:-:|
| `T1.java` | `L1/04/T1.java` | 100.0% |
| `T1.java` | `L1/06/HelloWorld.java` | 100.0% |
| `T1.java` | `L1/05/HelloWorld.java` | 92.3% |
| `T1.java` | `L4/01/L4.java` | 57.9% |
| `T1.java` | `L5/03/WelcomeToJava.java` | 39.1% |
| `T1.java` | `L6/02/Main.java` | 31.0% |

**Observation**: Jaccard decreases monotonically as the plagiarism level increases (L1→L6). Verbatim copies score 100%. Heavily restructured copies (L5, L6) still show 30–40% shared fingerprints.

### 4. AOSP Framework — Same Codebase, Minor Edits

**Why this dataset**: Two versions of Android's `Handler`/`Looper`/`Message` framework. Small evolutionary changes between versions.

```bash
diffinite example/aosp/left example/aosp/right \
    --no-comments --report-md example/benchmark/aosp.md
```

| File | Match (difflib) | Jaccard |
|------|:-:|:-:|
| `Handler.java` | 88.6% | — |
| `Looper.java` | 90.0% | 77.1% |
| `Message.java` | 96.3% | — |

**Observation**: High Match and Jaccard scores correctly reflect that these are minor revisions of the same codebase.

---

## Winnowing Algorithm

Diffinite uses the **Winnowing** algorithm (Schleimer, Wilkerson, Aiken. *"Winnowing: Local Algorithms for Document Fingerprinting."* SIGMOD 2003), which also forms the basis of [Stanford MOSS](https://theory.stanford.edu/~aiken/moss/).

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

## Limitations

- **General-purpose tokenizer**: Uses a single regex tokenizer for all languages, not language-specific parsers. Accuracy may vary across languages.
- **Position-independent**: Winnowing fingerprints are order-independent within a window. Code with reordered functions may produce higher similarity than expected.
- **No corpus-based analysis**: Each comparison is pairwise. There is no built-in corpus-wide frequency weighting (e.g., TF-IDF) to down-weight common idioms.
- **Binary and obfuscated code**: Not supported. Diffinite operates on source code text only.
- **Not a legal opinion**: Similarity scores are mathematical measurements, not legal conclusions. Professional review is required before use in any legal proceeding.

---

## License

[Apache License 2.0](LICENSE)

See [NOTICE](NOTICE) for attribution.
