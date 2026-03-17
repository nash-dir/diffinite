# Diffinite — Source Code Diff Report

## Analysis Configuration

| Parameter | Value |
|-----------|-------|
| **Execution Mode** | `deep` |
| **K-gram (K)** | `5` |
| **Window (W)** | `4` |
| **Threshold (T)** | `0.05` |

- **Dir A:** `example/plagiarism/case-01/original`
- **Dir B:** `example/plagiarism/case-01/plagiarized`
- **Comparison unit:** line
- **Comments:** excluded
- **Matched pairs:** 1
- **Unmatched:** 0 (A) / 39 (B)

## Summary

| # | File A | File B | Name Sim. | Match | +Added | −Deleted |
|---|--------|--------|:---------:|:-----:|:------:|:--------:|
| 1 | `T1.java` | `L1/04/T1.java` | 70.0 | 100.0% | +0 | −0 |

## Unmatched Files


### Only in B (`example/plagiarism/case-01/plagiarized`)

- `L1/01/L1.java`
- `L1/02/Main.java`
- `L1/03/Main.java`
- `L1/05/HelloWorld.java`
- `L1/06/HelloWorld.java`
- `L1/07/Main.java`
- `L1/08/Kasus1L1.java`
- `L1/09/Level1.java`
- `L2/01/L2.java`
- `L2/02/Main.java`
- `L2/03/WelcomeToJava.java`
- `L2/04/hellow.java`
- `L2/05/PrintJava.java`
- `L3/01/L3.java`
- `L3/02/Main.java`
- `L3/03/HelloWorld.java`
- `L3/04/hellow.java`
- `L3/05/Kasus1L3.java`
- `L3/06/Level3.java`
- `L4/01/L4.java`
- `L4/02/Main.java`
- `L4/03/Main.java`
- `L4/04/HelloWorld.java`
- `L4/05/hellow.java`
- `L4/06/Level4.java`
- `L5/01/L5.java`
- `L5/02/Main.java`
- `L5/03/WelcomeToJava.java`
- `L5/04/hellow.java`
- `L5/05/PrintJava.java`
- `L6/01/L6.java`
- `L6/02/Main.java`
- `L6/03/Main.java`
- `L6/04/WelcomeToJava.java`
- `L6/05/HelloWorld.java`
- `L6/06/hellow.java`
- `L6/07/PrintJava.java`
- `L6/08/Kasus1L6.java`
- `L6/09/Level6.java`

## Deep Compare — N:M Cross-Match Results

| A File | B File(s) | Shared Hashes | Jaccard |
|--------|-----------|:-------------:|:-------:|
| `T1.java` | `L1/04/T1.java` | 13 | 100.0% |
| `T1.java` | `L2/01/L2.java` | 13 | 100.0% |
| `T1.java` | `L2/04/hellow.java` | 13 | 100.0% |
| `T1.java` | `L1/06/HelloWorld.java` | 13 | 100.0% |
| `T1.java` | `L1/08/Kasus1L1.java` | 13 | 100.0% |
| `T1.java` | `L3/02/Main.java` | 13 | 100.0% |
| `T1.java` | `L1/05/HelloWorld.java` | 12 | 92.3% |
| `T1.java` | `L4/05/hellow.java` | 13 | 72.2% |
| `T1.java` | `L4/01/L4.java` | 11 | 57.9% |
| `T1.java` | `L6/06/hellow.java` | 11 | 57.9% |
| `T1.java` | `L5/03/WelcomeToJava.java` | 9 | 39.1% |
| `T1.java` | `L6/02/Main.java` | 9 | 31.0% |