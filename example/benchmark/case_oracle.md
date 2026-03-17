# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (T)** | `0.05` |

- **Dir A:** `example/Case-Oracle/AOSP_Google`
- **Dir B:** `example/Case-Oracle/OpenJDK_Oracle`
- **Comparison unit:** line
- **Comments:** excluded
- **Matched pairs:** 5
- **Unmatched:** 0 (A) / 0 (B)

## Summary

| # | File A | File B | Name Sim. | Match | +Added | −Deleted |
|---|--------|--------|:---------:|:-----:|:------:|:--------:|
| 1 | `ArrayList.java` | `ArrayList.java` | 100.0 | 9.0% | +1097 | −582 |
| 2 | `Collections.java` | `Collections.java` | 100.0 | 4.5% | +3830 | −3474 |
| 3 | `List.java` | `List.java` | 100.0 | 6.3% | +570 | −323 |
| 4 | `Math.java` | `Math.java` | 100.0 | 5.2% | +1459 | −986 |
| 5 | `String.java` | `String.java` | 100.0 | 3.3% | +3009 | −2211 |

## Deep Compare — N:M Cross-Match Results

| A File | B File(s) | Shared Hashes | Jaccard |
|--------|-----------|:-------------:|:-------:|
| `ArrayList.java` | `ArrayList.java` | 116 | 7.3% |
| `String.java` | `String.java` | 287 | 7.3% |