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
| **Analysis status** | `incomplete` |
| **Completeness detail** | Collection: 0 file/directory failure(s) |
| **Completeness detail** | Diff pairs: 5/5 processed; 0 worker failure(s) |
| **Completeness detail** | Deep files: 10/10 processed; 0 file/worker failure(s); 0 skipped as binary content |
| **Completeness detail** | Truncation: 1 inline diff payload(s); deep index complete |

> ℹ **Threshold disclosure:** Raw threshold 5 is the historical compatibility default and is not a calibrated safety threshold. Low-threshold results are similarity candidates for manual review, not legal copying determinations.

> ⚠ **Incomplete analysis / 불완전 결과:** diff-payload-truncated. This report must not be read as a complete analysis.

- **Dir A:** `AOSP_Google`
- **Dir B:** `OpenJDK_Oracle`
- **Comparison unit:** line
- **Comments:** stripped
- **Matched pairs:** 5
- **Unmatched:** 0 (A) / 0 (B)

## Summary

| # | File A | File B | Name Sim. | Line match (difflib) | +Added | −Deleted |
|---|--------|--------|:---------:|:--------------------:|:------:|:--------:|
| 1 | `ArrayList.java` | `ArrayList.java` | 100.0 | 7.0% | +1069 | −601 |
| 2 | `Collections.java` | `Collections.java` | 100.0 | 2.4% | +3878 | −3362 |
| 3 | `List.java` | `List.java` | 100.0 | 6.3% | +570 | −323 |
| 4 | `Math.java` | `Math.java` | 100.0 | 7.4% | +1421 | −1197 |
| 5 | `String.java` | `String.java` | 100.0 | 3.4% | +2989 | −1958 |

## Deep Compare — N:M Cross-Match Results

| A File | B File(s) | Shared Hashes | Jaccard | A in B | B in A |
|--------|-----------|:-------------:|:-------:|:------:|:------:|
| `ArrayList.java` | `ArrayList.java` | 122 | 7.96% | 16.46% | 13.36% |
| `Collections.java` | `Collections.java` | 1096 | 22.00% | 37.83% | 34.47% |
| `List.java` | `List.java` | 17 | 11.64% | 20.48% | 21.25% |
| `Math.java` | `Math.java` | 78 | 7.19% | 9.87% | 20.91% |
| `String.java` | `String.java` | 304 | 8.78% | 16.34% | 15.94% |

> **A in B** = shared ÷ unique fingerprints of the A file; **B in A** = shared ÷ unique fingerprints of the B file. Rows are selected by the Jaccard threshold only; the containment columns are descriptive and have no calibrated threshold.
