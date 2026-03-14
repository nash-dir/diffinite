# Plagiarism Detection Targets & Results

## Dataset: IR-Plag-Dataset

7 introductory Java programming tasks, Faidhi-Robinson plagiarism levels L1–L6.

| Level | Technique | Files/Case |
|-------|-----------|-----------|
| L1 | Comment/formatting changes only | ~9 |
| L2 | Identifier renaming | ~8 |
| L3 | Statement reordering | ~8 |
| L4 | Function extraction/refactoring | ~9 |
| L5 | Loop/control-flow transformation | ~8 |
| L6 | Complete logic restructuring | ~9 |

Non-plagiarized: 9–15 independent submissions per case (105 total).

---

## Baseline (Industrial Profile — K=5, W=4, threshold=0.10)

Default weights: `raw=1.0, norm=2.0, ast=2.0, id_cos=1.5, cs_ovl=1.0`

| Level | TPR | Avg Composite |
|-------|-----|---------------|
| L1 | 1.0000 (60/60) | 0.8389 |
| L2 | 1.0000 (56/56) | 0.6868 |
| L3 | 1.0000 (57/57) | 0.6389 |
| L4 | 1.0000 (60/60) | 0.5223 |
| L5 | 1.0000 (59/59) | 0.4691 |
| L6 | 1.0000 (63/63) | 0.4300 |

| Metric | Value |
|--------|-------|
| Precision | 0.7717 |
| Recall | 1.0000 |
| F1-Score | 0.8712 |
| FPR | 1.0000 |
| TP=355 FN=0 | FP=105 TN=0 |

### Diagnosis
Threshold too low for short academic code — all non-plagiarized submissions scored above 0.10, causing 100% FPR.

---

## Tuned (Academic Profile — K=2, W=3, threshold=0.40)

Weights: `raw=3.0, norm=1.0, ast=1.0, id_cos=0.0, cs_ovl=0.0`

| Level | TPR | Avg Composite |
|-------|-----|---------------|
| L1 | 1.0000 (60/60) | 0.9354 |
| L2 | 1.0000 (56/56) | 0.7361 |
| L3 | 1.0000 (57/57) | 0.7279 |
| L4 | 1.0000 (60/60) | 0.6244 |
| L5 | 1.0000 (59/59) | 0.5814 |
| L6 | 0.9683 (61/63) | 0.5367 |

| Metric | Value |
|--------|-------|
| Precision | 0.7915 |
| Recall | 0.9944 |
| F1-Score | **0.8814** |
| FPR | 0.8857 |
| TP=353 FN=2 | FP=93 TN=12 |

---

## Improvement Summary

| Metric | Baseline | Tuned | Delta |
|--------|----------|-------|-------|
| **F1-Score** | 0.8712 | **0.8814** | **+0.0102** |
| Precision | 0.7717 | 0.7915 | +0.0198 |
| Recall | 1.0000 | 0.9944 | −0.0056 |
| FPR | 1.0000 | 0.8857 | **−0.1143** |

### Per-Level TPR

| Level | Baseline | Tuned | Delta |
|-------|----------|-------|-------|
| L1 | 1.0000 | 1.0000 | — |
| L2 | 1.0000 | 1.0000 | — |
| L3 | 1.0000 | 1.0000 | — |
| L4 | 1.0000 | 1.0000 | — |
| L5 | 1.0000 | 1.0000 | — |
| L6 | 1.0000 | 0.9683 | −0.0317 |

### Key Findings

1. **F1 improved** from 0.8712 to 0.8814 (+1.0pp) — driven by precision gain.
2. **Precision improved** from 0.7717 to 0.7915 (+2.0pp) — fewer false positives.
3. **FPR reduced** by 11.4pp (1.00 → 0.89) — 12 true negatives vs 0 at baseline.
4. **L1–L5 maintain 100% TPR** — only L6 (logic restructuring) drops to 96.8%.
5. **Identifier/comment channels disabled** for academic profile — these channels add noise for short programs that inevitably share common Java keywords and boilerplate strings.
6. **Smaller K-grams** (K=2 vs K=5) better capture the short code fragments in 10–30 line academic submissions.

### Remaining Challenge

Short academic programs inherently share significant structural patterns (loops, if-statements, print calls). FPR remains high (0.89) because independent solutions to the same task produce similar Winnowing fingerprints. This is a fundamental limitation of fingerprint-based detection for ultra-short code — full semantic analysis (deep learning, PDG normalization) would be needed for further FPR reduction.
