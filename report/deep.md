# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **Profile** | `industrial` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (T)** | `0.10` |
| **Tokenizer** | `token` |
| **Grid Search** | `No` |

- **Dir A:** `example\aosp\left`
- **Dir B:** `example\aosp\right`
- **Comparison unit:** line
- **Comments:** excluded
- **Matched pairs:** 3
- **Unmatched:** 0 (A) / 0 (B)

## Summary

| # | File A | File B | Name Sim. | Match | +Added | −Deleted |
|---|--------|--------|:---------:|:-----:|:------:|:--------:|
| 1 | `Handler.java` | `Handler.java` | 100.0 | 88.6% | +144 | −76 |
| 2 | `Looper.java` | `Looper.java` | 100.0 | 90.0% | +82 | −5 |
| 3 | `Message.java` | `Message.java` | 100.0 | 96.3% | +42 | −6 |

## Deep Compare — N:M Cross-Match Results

| A File | B File(s) | Shared Hashes | Jaccard |
|--------|-----------|:-------------:|:-------:|
| `Looper.java` | `Looper.java` | 436 | 75.8% |
| `Message.java` | `Message.java` | 552 | 83.8% |