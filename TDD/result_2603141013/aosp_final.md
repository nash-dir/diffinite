# Diffinite — Source Code Diff Report

- **Dir A:** `example/aosp/left`
- **Dir B:** `example/aosp/right`
- **Comparison unit:** line
- **Comments:** included
- **Matched pairs:** 3
- **Unmatched:** 0 (A) / 0 (B)

## Summary

| # | File A | File B | Name Sim. | Match | +Added | −Deleted |
|---|--------|--------|:---------:|:-----:|:------:|:--------:|
| 1 | `Handler.java` | `Handler.java` | 100.0 | 90.6% | +125 | −57 |
| 2 | `Looper.java` | `Looper.java` | 100.0 | 89.1% | +86 | −9 |
| 3 | `Message.java` | `Message.java` | 100.0 | 96.0% | +44 | −8 |

## Deep Compare — Multi-Evidence Channel Matrix

| A File | B File | Raw | Normalized | AST | Identifier | Comment/Str | Composite |
|--------|--------|:---:|:----------:|:---:|:----------:|:-----------:|:---------:|
| `Looper.java` | `Looper.java` | 75.5% | 82.3% | — | 94.8% | 80.0% | 84.0% |
| `Message.java` | `Message.java` | 84.9% | 87.8% | — | 98.8% | 92.9% | 91.2% |