# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (min Jaccard)** | `93.0%` |
| **Threshold provenance** | `normalize-default` |
| **Normalize fingerprints** | `on` |
| **Line diff autojunk** | `on` |
| **Ignore policy** | `0 rule(s); SHA-256=none` |
| **Selection filter** | `none; 0 path(s); SHA-256=none` |
| **Analysis status** | `complete` |
| **Completeness detail** | Collection: 0 file/directory failure(s) |
| **Completeness detail** | Diff pairs: 3/3 processed; 0 worker failure(s) |
| **Completeness detail** | Deep files: 6/6 processed; 0 file/worker failure(s); 0 skipped as binary content |
| **Completeness detail** | Truncation: 0 inline diff payload(s); deep index complete |

> ℹ **Threshold disclosure:** Normalize (identifier-flattening) inflates false positives on independent same-domain code. The active fingerprint settings are an unvalidated profile for ir-plag-file-pair-normalize-v1 (mismatch: strip_comments); the published false-positive-rate and confidence-interval estimate does not apply. Threshold 93 and the 45-token inconclusive guard remain conservative compatibility behavior, not a calibrated safety claim for this profile.

- **Dir A:** `left`
- **Dir B:** `right`
- **Comparison unit:** line
- **Comments:** included
- **Matched pairs:** 3
- **Unmatched:** 0 (A) / 0 (B)

## Summary

| # | File A | File B | Name Sim. | Line match (difflib) | +Added | −Deleted |
|---|--------|--------|:---------:|:--------------------:|:------:|:--------:|
| 1 | `mixed.py` | `mixed.py` | 100.0 | 0.0% | +5 | −5 |
| 2 | `日本語.java` | `日本語.java` | 100.0 | 37.5% | +6 | −4 |
| 3 | `계산기.py` | `계산기.py` | 100.0 | 43.5% | +8 | −5 |