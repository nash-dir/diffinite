# Source Code Comparison Report

## Particulars

| Item | Value |
|---|---|
| Directory A | `AOSP_Google` |
| Directory B | `OpenJDK_Oracle` |
| Report generated | 2026-11-10 04:28 UTC |
| Tool | Diffinite 0.14.0 |
| Comparison unit | line |
| Comments | stripped |
| Matched pairs | 5 |
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
| File pairs compared | 5 of 5 |
| File pairs failed | 0 |
| Inline diffs truncated | 0 |
| Deep Compare files processed | 10 of 10 |
| Deep Compare files failed | 0 |
| Deep Compare files skipped (binary or not decodable as text) | 0 |
| Deep Compare files with fewer tokens than the k-gram size | 0 |
| Deep Compare pairs at or above the threshold | 5 |
| Deep Compare index | Complete |

## Scope and Limitations

1. Similarity figures in this report measure textual and token overlap between the files compared. They do not establish copying, derivation or infringement.
2. Short files and small code fragments can show high similarity even when written independently, because language syntax and common idioms leave little room for variation.
3. Deep Compare lists file pairs whose Jaccard similarity is at least 5%, the default threshold. No false-positive rate has been measured for this threshold.

## Summary

| # | File A | File B | Name similarity | Line match | Added | Deleted |
|--:|--------|--------|--:|--:|--:|--:|
| 1 | `ArrayList.java` | `ArrayList.java` | 100.0% | 7.0% | +1,069 | −601 |
| 2 | `Collections.java` | `Collections.java` | 100.0% | 2.4% | +3,878 | −3,362 |
| 3 | `List.java` | `List.java` | 100.0% | 6.3% | +570 | −323 |
| 4 | `Math.java` | `Math.java` | 100.0% | 7.4% | +1,421 | −1,197 |
| 5 | `String.java` | `String.java` | 100.0% | 3.4% | +2,989 | −1,958 |

## Deep Compare: Cross-Match Results

| File A | File B | Shared hashes | Jaccard | A in B | B in A |
|--------|--------|--:|--:|--:|--:|
| `ArrayList.java` | `ArrayList.java` | 122 | 7.96% | 16.46% | 13.36% |
| `Collections.java` | `Collections.java` | 1,096 | 22.00% | 37.83% | 34.47% |
| `List.java` | `List.java` | 17 | 11.64% | 20.48% | 21.25% |
| `Math.java` | `Math.java` | 78 | 7.19% | 9.87% | 20.91% |
| `String.java` | `String.java` | 304 | 8.78% | 16.34% | 15.94% |

A in B is the number of shared hashes divided by the number of unique hashes of the A file; B in A is the same ratio for the B file. Rows are selected by the Jaccard threshold only.
