# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (min Jaccard)** | `5.0%` |

- **Dir A:** `AOSP_Google`
- **Dir B:** `OpenJDK_Oracle`
- **Comparison unit:** line
- **Comments:** stripped
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
| `ArrayList.java` | `ArrayList.java` | 123 | 7.89% |
| `Collections.java` | `Collections.java` | 1113 | 23.14% |
| `List.java` | `List.java` | 17 | 11.64% |
| `Math.java` | `Math.java` | 42 | 6.30% |
| `String.java` | `String.java` | 269 | 6.83% |