# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (T)** | `0.05` |

- **Dir A:** `example/Case-NegativeControl/Eclipse_Collections`
- **Dir B:** `example/Case-NegativeControl/OpenJDK`
- **Comparison unit:** line
- **Comments:** excluded
- **Matched pairs:** 2
- **Unmatched:** 3 (A) / 3 (B)

## Summary

| # | File A | File B | Name Sim. | Match | +Added | −Deleted |
|---|--------|--------|:---------:|:-----:|:------:|:--------:|
| 1 | `StringIterate.java` | `String.java` | 75.9 | 2.4% | +3045 | −1246 |
| 2 | `FastList.java` | `ArrayList.java` | 74.1 | 1.5% | +1159 | −1619 |

## Unmatched Files

### Only in A (`example/Case-NegativeControl/Eclipse_Collections`)

- `Iterate.java`
- `UnifiedMap.java`
- `UnifiedSet.java`

### Only in B (`example/Case-NegativeControl/OpenJDK`)

- `Collections.java`
- `HashMap.java`
- `HashSet.java`