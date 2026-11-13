# Source Code Comparison Report

## Particulars

| Item | Value |
|---|---|
| Directory A | `left` |
| Directory B | `right` |
| Report generated | 2026-11-10 04:28 UTC |
| Tool | Diffinite 0.14.0 |
| Comparison unit | line |
| Comments | stripped |
| Matched pairs | 3 |
| Unmatched files | 0 in A; 0 in B |

## Analysis Configuration

| Setting | Value |
|---|---|
| Mode | deep |
| K-gram size (K) | 5 |
| Window size (W) | 4 |
| Jaccard threshold | 5% |
| Threshold source | Default (5%) |
| Identifier normalization | off |
| Line diff autojunk | on |
| Ignore policy | 0 rules; SHA-256 none |
| Selection filter | none; 0 paths; SHA-256 none |

## Analysis Status

| Item | Value |
|---|---|
| State | Complete |
| Inputs not read | 0 |
| File pairs compared | 3 of 3 |
| File pairs failed | 0 |
| Inline diffs truncated | 0 |
| Deep Compare files processed | 6 of 6 |
| Deep Compare files failed | 0 |
| Deep Compare files skipped (binary or not decodable as text) | 0 |
| Deep Compare files with fewer tokens than the k-gram size | 0 |
| Deep Compare pairs at or above the threshold | 3 |
| Deep Compare index | Complete |

## Scope and Limitations

1. Similarity figures in this report measure textual and token overlap between the files compared. They do not establish copying, derivation or infringement.
2. Short files and small code fragments can show high similarity even when written independently, because language syntax and common idioms leave little room for variation.
3. Deep Compare lists file pairs whose Jaccard similarity is at least 5%, the default threshold. No false-positive rate has been measured for this threshold.

## Summary

| # | File A | File B | Name similarity | Line match | Added | Deleted |
|--:|--------|--------|--:|--:|--:|--:|
| 1 | `Handler.java` | `Handler.java` | 100.0% | 88.6% | +144 | −76 |
| 2 | `Looper.java` | `Looper.java` | 100.0% | 90.0% | +82 | −5 |
| 3 | `Message.java` | `Message.java` | 100.0% | 96.3% | +42 | −6 |

## Deep Compare: Cross-Match Results

| File A | File B | Shared hashes | Jaccard | A in B | B in A |
|--------|--------|--:|--:|--:|--:|
| `Handler.java` | `Handler.java` | 588 | 75.10% | 89.50% | 82.35% |
| `Looper.java` | `Looper.java` | 458 | 76.08% | 93.66% | 80.21% |
| `Message.java` | `Message.java` | 529 | 83.05% | 93.63% | 88.02% |

A in B is the number of shared hashes divided by the number of unique hashes of the A file; B in A is the same ratio for the B file. Rows are selected by the Jaccard threshold only.
