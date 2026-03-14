# Plagiarism Dataset Analysis Report

> Generated: 2026-03-14 11:15
> Dataset: `example/plagiarism/` (IR-Plag-Dataset)

## Overview

Cross-validation of Diffinite against the IR-Plag-Dataset — 7 introductory
Java programming tasks with Faidhi-Robinson L1–L6 plagiarism levels and
independent (non-plagiarized) submissions.

| Level | Plagiarism Technique |
|-------|---------------------|
| L1 | Comment/formatting changes |
| L2 | Identifier renaming |
| L3 | Statement reordering |
| L4 | Function extraction/refactoring |
| L5 | Loop/control-flow transformation |
| L6 | Complete logic restructuring |

## Case Summary

| Case | Original File | Lines | Plagiarized | Non-Plagiarized |
|------|--------------|:---:|:---:|:---:|
| `case-01` | `T1.java` | 12 | 40 | 15 |
| `case-02` | `T2.java` | 20 | 54 | 15 |
| `case-03` | `T3.java` | 35 | 52 | 15 |
| `case-04` | `T4.java` | 16 | 54 | 15 |
| `case-05` | `T5.java` | 21 | 53 | 15 |
| `case-06` | `T6.java` | 21 | 51 | 15 |
| `case-07` | `T7.java` | 27 | 51 | 15 |

## Industrial Profile (K=5, W=4, T=0.10)

### Per-Level Average Composite Score

| Case | L1 | L2 | L3 | L4 | L5 | L6 | Neg Avg |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `case-01` | 0.827 | 0.750 | 0.753 | 0.501 | 0.340 | 0.285 | 0.373 |
| `case-02` | 0.868 | 0.687 | 0.630 | 0.471 | 0.476 | 0.460 | 0.533 |
| `case-03` | 0.833 | 0.733 | 0.668 | 0.557 | 0.541 | 0.481 | 0.650 |
| `case-04` | 0.875 | 0.678 | 0.603 | 0.520 | 0.454 | 0.448 | 0.240 |
| `case-05` | 0.835 | 0.608 | 0.579 | 0.492 | 0.430 | 0.398 | 0.378 |
| `case-06` | 0.826 | 0.671 | 0.579 | 0.490 | 0.410 | 0.380 | 0.552 |
| `case-07` | 0.773 | 0.671 | 0.610 | 0.537 | 0.501 | 0.462 | 0.502 |

## Academic Profile (K=2, W=3, T=0.40)

### Per-Level Average Composite Score

| Case | L1 | L2 | L3 | L4 | L5 | L6 | Neg Avg |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `case-01` | 0.900 | 0.861 | 0.833 | 0.659 | 0.533 | 0.491 | 0.520 |
| `case-02` | 0.944 | 0.716 | 0.714 | 0.615 | 0.616 | 0.597 | 0.654 |
| `case-03` | 0.922 | 0.718 | 0.698 | 0.620 | 0.613 | 0.554 | 0.691 |
| `case-04` | 0.924 | 0.736 | 0.694 | 0.651 | 0.568 | 0.548 | 0.430 |
| `case-05` | 0.936 | 0.659 | 0.683 | 0.626 | 0.549 | 0.519 | 0.456 |
| `case-06` | 0.939 | 0.767 | 0.734 | 0.673 | 0.602 | 0.564 | 0.672 |
| `case-07` | 0.926 | 0.788 | 0.768 | 0.726 | 0.684 | 0.626 | 0.666 |

## Profile Comparison

| Metric | Industrial (K=5,W=4,T=0.10) | Academic (K=2,W=3,T=0.40) | Δ |
|--------|:---:|:---:|:---:|
| F1 | 0.8712 | 0.8736 | +0.0024 |
| PRECISION | 0.7717 | 0.7860 | +0.0143 |
| RECALL | 1.0000 | 0.9831 | -0.0169 |
| FPR | 1.0000 | 0.9048 | -0.0952 |
| TP | 355 | 349 | -6 |
| FP | 105 | 95 | -10 |

## Key Findings

- **Industrial profile**: F1=0.8712 — optimized for large codebases, threshold too low for short academic code
- **Academic profile**: F1=0.8736 — tuned for 10–30 line submissions, disables noisy identifier/comment channels
- **L1–L4 detection** remains robust across both profiles (surface-level plagiarism)
- **L5–L6** (control-flow/logic restructuring) are inherently harder; academic profile achieves better precision at minimal TPR cost
- **FPR reduction**: 1.00 → 0.90 (9.5pp improvement)