# Source Code Comparison Report

## Particulars

| Item | Value |
|---|---|
| Directory A | `Eclipse_Collections` |
| Directory B | `OpenJDK` |
| Report generated | 2026-11-10 04:28 UTC |
| Tool | Diffinite 0.14.0 |
| Comparison unit | line |
| Comments | stripped |
| Matched pairs | 2 |
| Unmatched files | 3 in A; 3 in B |

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
| File pairs compared | 2 of 2 |
| File pairs failed | 0 |
| Inline diffs truncated | 0 |
| Deep Compare files processed | 10 of 10 |
| Deep Compare files failed | 0 |
| Deep Compare files skipped (binary or not decodable as text) | 0 |
| Deep Compare files with fewer tokens than the k-gram size | 0 |
| Deep Compare pairs at or above the threshold | 0 (no file pair reached the Jaccard threshold) |
| Deep Compare index | Complete |

## Scope and Limitations

1. Similarity figures in this report measure textual and token overlap between the files compared. They do not establish copying, derivation or infringement.
2. Short files and small code fragments can show high similarity even when written independently, because language syntax and common idioms leave little room for variation.
3. Deep Compare lists file pairs whose Jaccard similarity is at least 5%, the default threshold. No false-positive rate has been measured for this threshold.

## Summary

| # | File A | File B | Name similarity | Line match | Added | Deleted |
|--:|--------|--------|--:|--:|--:|--:|
| 1 | `StringIterate.java` | `String.java` | 75.9% | 1.1% | +3,054 | −1,276 |
| 2 | `FastList.java` | `ArrayList.java` | 74.1% | 1.5% | +1,111 | −1,619 |

## Unmatched Files

### Only in A (`Eclipse_Collections`)

- `Iterate.java`
- `UnifiedMap.java`
- `UnifiedSet.java`

### Only in B (`OpenJDK`)

- `Collections.java`
- `HashMap.java`
- `HashSet.java`