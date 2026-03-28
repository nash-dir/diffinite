# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (T)** | `5.00` |

- **Dir A:** `Eclipse_Collections`
- **Dir B:** `OpenJDK`
- **Comparison unit:** line
- **Comments:** stripped
- **Matched pairs:** 2
- **Unmatched:** 3 (A) / 3 (B)

## Summary

| # | File A | File B | Name Sim. | Match | +Added | −Deleted |
|---|--------|--------|:---------:|:-----:|:------:|:--------:|
| 1 | `StringIterate.java` | `String.java` | 75.9 | 2.4% | +3045 | −1246 |
| 2 | `FastList.java` | `ArrayList.java` | 74.1 | 1.5% | +1159 | −1619 |

## Unmatched Files

### Only in A (`Eclipse_Collections`)

- `Iterate.java`
- `UnifiedMap.java`
- `UnifiedSet.java`

### Only in B (`OpenJDK`)

- `Collections.java`
- `HashMap.java`
- `HashSet.java`