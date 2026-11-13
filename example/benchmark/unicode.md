# Source Code Comparison Report

## Particulars

| Item | Value |
|---|---|
| Directory A | `left` |
| Directory B | `right` |
| Report generated | 2026-11-10 04:28 UTC |
| Tool | Diffinite 0.14.0 |
| Comparison unit | line |
| Comments | included |
| Matched pairs | 3 |
| Unmatched files | 0 in A; 0 in B |

## Analysis Configuration

| Setting | Value |
|---|---|
| Mode | deep |
| K-gram size (K) | 5 |
| Window size (W) | 4 |
| Jaccard threshold | 93% |
| Threshold source | Default for normalized comparison |
| Identifier normalization | on |
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
| Deep Compare pairs at or above the threshold | 0 (no file pair reached the Jaccard threshold) |
| Deep Compare index | Complete |

## Scope and Limitations

1. Similarity figures in this report measure textual and token overlap between the files compared. They do not establish copying, derivation or infringement.
2. Short files and small code fragments can show high similarity even when written independently, because language syntax and common idioms leave little room for variation.
3. Normalization replaces identifiers and literals before fingerprinting, which raises the similarity of independently written code in the same domain. The settings of this run differ from the measured profile ir-plag-file-pair-normalize-v1 (comment stripping). This is an unvalidated profile, and the measured false-positive rate does not apply.

## Summary

| # | File A | File B | Name similarity | Line match | Added | Deleted |
|--:|--------|--------|--:|--:|--:|--:|
| 1 | `mixed.py` | `mixed.py` | 100.0% | 0.0% | +5 | −5 |
| 2 | `日本語.java` | `日本語.java` | 100.0% | 37.5% | +6 | −4 |
| 3 | `계산기.py` | `계산기.py` | 100.0% | 43.5% | +8 | −5 |