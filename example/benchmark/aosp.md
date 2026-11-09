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
| **Completeness detail** | Diff pairs: 3/3 processed; 0 worker failure(s) |
| **Completeness detail** | Deep files: 6/6 processed; 0 file/worker failure(s); 0 skipped as binary content |
| **Completeness detail** | Truncation: 0 inline diff payload(s); deep index complete |

> ℹ **Threshold disclosure:** Raw threshold 5 is the historical compatibility default and is not a calibrated safety threshold. Low-threshold results are similarity candidates for manual review, not legal copying determinations.

- **Dir A:** `left`
- **Dir B:** `right`
- **Comparison unit:** line
- **Comments:** stripped
- **Matched pairs:** 3
- **Unmatched:** 0 (A) / 0 (B)

## Summary

| # | File A | File B | Name Sim. | Line match (difflib) | +Added | −Deleted |
|---|--------|--------|:---------:|:--------------------:|:------:|:--------:|
| 1 | `Handler.java` | `Handler.java` | 100.0 | 88.6% | +144 | −76 |
| 2 | `Looper.java` | `Looper.java` | 100.0 | 90.0% | +82 | −5 |
| 3 | `Message.java` | `Message.java` | 100.0 | 96.3% | +42 | −6 |

## Deep Compare — N:M Cross-Match Results

| A File | B File(s) | Shared Hashes | Jaccard | A in B | B in A |
|--------|-----------|:-------------:|:-------:|:------:|:------:|
| `Handler.java` | `Handler.java` | 588 | 75.10% | 89.50% | 82.35% |
| `Looper.java` | `Looper.java` | 458 | 76.08% | 93.66% | 80.21% |
| `Message.java` | `Message.java` | 529 | 83.05% | 93.63% | 88.02% |

> **A in B** = shared ÷ unique fingerprints of the A file; **B in A** = shared ÷ unique fingerprints of the B file. Rows are selected by the Jaccard threshold only; the containment columns are descriptive and have no calibrated threshold.
