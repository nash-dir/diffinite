# Diffinite

**Forensic source-code comparison → PDF report with multi-evidence analysis**

Diffinite compares source code across two directories using fuzzy file-name matching, Winnowing fingerprint analysis, and optional AST-level structural comparison. It produces professional PDF reports with side-by-side visual diffs, N:M cross-matching, and multi-channel evidence scoring — designed for **IP litigation, code audit, and software plagiarism forensics**.

## Key Features

### Core Analysis
- **Fuzzy file matching** — Pairs files across directories even if names differ ([RapidFuzz](https://github.com/rapidfuzz/RapidFuzz))
- **Side-by-side diff** — Line-by-line visual comparison with syntax highlighting ([Pygments](https://pygments.org/))
- **Context folding** — Collapses unchanged regions to focus on changes
- **Comment stripping** — Optionally ignores comments before comparison
- **Encoding auto-detection** — Handles mixed encodings via [charset-normalizer](https://github.com/Ousret/charset_normalizer)

### Deep Compare (N:M Cross-Matching)
- **Winnowing fingerprints** — Detect code reuse even across split/merged files
- **Token normalization** — Catches Type-2 clones (renamed identifiers/literals)
- **AST linearization** — tree-sitter-based structural analysis resilient to variable renaming (Phase 2)
- **PDG normalization** — Use-def chain analysis, dead code filtering, dependency reordering (Phase 4)

### Multi-Evidence Channels (Phase 3)
- **Raw Winnowing** — Exact token sequence similarity
- **Normalized Winnowing** — Identifier/literal-normalized similarity
- **AST Winnowing** — Structural pattern similarity
- **Identifier Cosine** — Name-change disguise detection
- **Comment/String Overlap** — Author artefact preservation detection
- **Composite Score** — Weighted combination of all channels

### PDF Report
- **Cover page** — Summary table with match ratios, additions/deletions, and channel evidence matrix
- **Diff pages** — Side-by-side visual diff for each matched file pair
- **Bates numbering** — Sequential page stamps for legal/forensic use
- **Page annotations** — File sequence, page numbers, and filename on every page
- **Merge or split** — Single merged PDF or individual per-file PDFs

## Installation

```bash
pip install diffinite
```

From source (with AST analysis support):

```bash
git clone https://github.com/nash-dir/diffinite.git
cd diffinite
pip install -e ".[ast]"
```

## Quick Start

```bash
# Basic comparison
diffinite dir_a dir_b -o report.pdf

# With comment stripping and annotations
diffinite dir_a dir_b -o report.pdf --no-comments \
    --page-number --file-number --bates-number --show-filename

# Deep compare with Winnowing fingerprints
diffinite dir_a dir_b -o report.pdf --deep --normalize

# AST-based structural analysis + multi-channel evidence
diffinite dir_a dir_b -o report.pdf --deep --mode ast --multi-channel

# Maximum forensic analysis (AST + all channels + normalization)
diffinite dir_a dir_b -o report.pdf --deep --mode ast --multi-channel --normalize --no-comments
```

## CLI Options

| Option | Description |
|--------|-------------|
| `dir_a` | Path to the original source directory |
| `dir_b` | Path to the comparison source directory |
| `-o`, `--output-pdf` | Output PDF file path (default: `report.pdf`) |
| `--by-word` | Compare by word instead of by line |
| `--no-comments` | Strip comments before comparison |
| `--threshold` | Fuzzy matching threshold, 0–100 (default: 60) |
| `--no-merge` | Generate individual PDFs per file |
| `--page-number` | Show `Page n / N` at the bottom-right |
| `--file-number` | Show `File n / N` at the bottom-left |
| `--bates-number` | Stamp Bates numbers at the bottom-center |
| `--show-filename` | Show filename at the top-right |

### Deep Compare Options

| Option | Description |
|--------|-------------|
| `--deep` | Enable N:M deep cross-matching |
| `--normalize` | Normalize identifiers → `ID`, literals → `LIT` |
| `--mode` | Fingerprint strategy: `token` (default), `ast`, `pdg` |
| `--multi-channel` | Enable 5-channel multi-evidence scoring |
| `--kgram-size` | K-gram size for Winnowing (default: 5) |
| `--window-size` | Winnowing window size (default: 4) |
| `--min-jaccard` | Minimum Jaccard threshold for matches (default: 0.05) |

## Architecture

```
src/diffinite/
├── cli.py              # CLI entry point
├── pipeline.py         # Orchestration pipeline
├── collector.py        # File collection & fuzzy matching
├── parser.py           # Comment stripping (Python/C/Java/JS/Go/Rust/HTML/SQL)
├── differ.py           # Diff computation & HTML generation
├── fingerprint.py      # Winnowing fingerprint extraction
├── deep_compare.py     # N:M cross-matching engine
├── ast_normalizer.py   # tree-sitter AST linearization & PDG normalization
├── evidence.py         # Multi-evidence channel scoring
├── models.py           # Data classes
└── pdf_gen.py          # PDF report generation
```

## Supported Languages

### Comment Stripping (`--no-comments`)

| Extensions | Comment styles |
|------------|---------------|
| `.py` | `# ...` |
| `.js` `.ts` `.c` `.cpp` `.h` `.hpp` `.java` `.cs` `.go` `.rs` | `// ...` and `/* ... */` |
| `.html` `.xml` `.htm` `.svg` | `<!-- ... -->` |
| `.sql` | `-- ...` and `/* ... */` |

### AST Analysis (`--mode ast`)

| Extensions | Language |
|------------|---------|
| `.py` | Python |
| `.java` | Java |
| `.js` | JavaScript |
| `.ts` | TypeScript |
| `.c` `.h` | C |
| `.cpp` `.hpp` `.cc` | C++ |
| `.cs` | C# |
| `.go` | Go |
| `.rs` | Rust |

## License

[Apache License 2.0](LICENSE)

See [NOTICE](NOTICE) for additional attribution information.
