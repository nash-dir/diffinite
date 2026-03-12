# Diffinite

**Source code directory diff → PDF report with Bates numbering**

Diffinite compares source code files across two directories using fuzzy file-name matching, produces quantitative analysis (match ratio, additions, deletions), and generates a styled PDF report with side-by-side visual diffs.

Built for **code audits, IP litigation, forensic analysis**, and any scenario where you need a professional, paginated diff report with legal-grade page identification.

## Features

- **Fuzzy file matching** — Automatically pairs files across directories even if names differ slightly (powered by [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz))
- **Side-by-side diff** — Line-by-line visual comparison with color-coded additions/deletions
- **PDF report** — Professional A4 landscape PDF with cover page and per-file diffs
- **Bates numbering** — Sequential page stamps for legal/forensic use
- **Page annotations** — File sequence, page numbers, and filename on every page
- **Merge or split** — Single merged PDF or individual per-file PDFs
- **Comment stripping** — Optionally ignore comments before comparison
- **Word or line mode** — Compare by line (default) or by whitespace-split tokens
- **Encoding auto-detection** — Handles mixed encodings via [charset-normalizer](https://github.com/Ousret/charset_normalizer)

## Installation

```bash
pip install diffinite
```

Or install from source:

```bash
git clone https://github.com/nash-dir/diffinite.git
cd diffinite
pip install .
```

## Quick Start

```bash
# Basic comparison
diffinite dir_a dir_b -o report.pdf

# Full annotations: page numbers, file sequence, Bates numbers, filenames
diffinite dir_a dir_b -o report.pdf \
    --page-number --file-number --bates-number --show-filename

# Individual PDFs per file (no merge)
diffinite dir_a dir_b -o report.pdf --no-merge \
    --page-number --file-number --bates-number --show-filename

# Strip comments before comparison
diffinite dir_a dir_b -o report.pdf --no-comments
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
| `--page-number` | Show `Page n / N` at the bottom-right of each page |
| `--file-number` | Show `File n / N` at the bottom-left of each page |
| `--bates-number` | Stamp Bates numbers at the bottom-center of each page |
| `--show-filename` | Show the filename at the top-right of each page |

## PDF Output

### Merged mode (default)

Generates a single PDF with:
1. **Cover page** — Summary table with match ratios, additions/deletions per file pair
2. **Diff pages** — Side-by-side visual diff for each matched file pair

### Split mode (`--no-merge`)

Generates individual PDFs in a `{output_stem}_files/` directory:
- `000_cover.pdf` — Cover page
- `001_{filename}.pdf` — Per-file diff pages

Bates numbers are continuous across all files in both modes.

## Example

An example dataset (AOSP Android 9 vs 11 Core OS) is included. To download the source files and run:

```bash
cd example
example_download.bat       # Downloads Handler.java, Looper.java, Message.java
cd ..
diffinite example/left example/right -o example_report.pdf \
    --page-number --file-number --bates-number --show-filename
```

## Supported Languages (Comment Stripping)

When using `--no-comments`, the following file types are supported:

| Extensions | Comment styles |
|------------|---------------|
| `.py` | `# ...` |
| `.js` `.ts` `.c` `.cpp` `.h` `.hpp` `.java` `.cs` `.go` `.rs` | `// ...` and `/* ... */` |
| `.html` `.xml` `.htm` `.svg` | `<!-- ... -->` |

## License

[Apache License 2.0](LICENSE)

See [NOTICE](NOTICE) for additional attribution information.
