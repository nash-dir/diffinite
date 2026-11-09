# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (min Jaccard)** | `5.0%` |
| **Threshold provenance** | `legacy-uncalibrated` |
| **Normalize fingerprints** | `off` |
| **Line diff autojunk** | `on` |
| **Ignore policy** | `0 rule(s); SHA-256=none` |
| **Selection filter** | `none; 0 path(s); SHA-256=none` |
| **Analysis status** | `complete` |
| **Completeness detail** | Collection: 0 file/directory failure(s) |
| **Completeness detail** | Diff pairs: 2/2 processed; 0 worker failure(s) |
| **Completeness detail** | Deep files: 10/10 processed; 0 file/worker failure(s); 0 skipped as binary content |
| **Completeness detail** | Truncation: 0 inline diff payload(s); deep index complete |

> ℹ **Threshold disclosure:** Raw threshold 5 is the historical compatibility default and is not a calibrated safety threshold. Low-threshold results are similarity candidates for manual review, not legal copying determinations.

- **Dir A:** `Eclipse_Collections`
- **Dir B:** `OpenJDK`
- **Comparison unit:** line
- **Comments:** stripped
- **Matched pairs:** 2
- **Unmatched:** 3 (A) / 3 (B)

## Summary

| # | File A | File B | Name Sim. | Line match (difflib) | +Added | −Deleted |
|---|--------|--------|:---------:|:--------------------:|:------:|:--------:|
| 1 | `StringIterate.java` | `String.java` | 75.9 | 1.1% | +3054 | −1276 |
| 2 | `FastList.java` | `ArrayList.java` | 74.1 | 1.5% | +1111 | −1619 |

## Unmatched Files

### Only in A (`Eclipse_Collections`)

- `Iterate.java`
- `UnifiedMap.java`
- `UnifiedSet.java`

### Only in B (`OpenJDK`)

- `Collections.java`
- `HashMap.java`
- `HashSet.java`