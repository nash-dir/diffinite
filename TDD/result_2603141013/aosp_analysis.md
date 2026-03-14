# AOSP Example Analysis Report

> Generated: 2026-03-14 11:15
> Dataset: `example/aosp/`

## Overview

Cross-version comparison of AOSP (Android Open Source Project)
core OS Java files: Android 9 (Pie) vs Android 11.
Targets `android.os.Handler`, `Looper`, and `Message` — the core
message-passing framework of Android's main thread architecture.

## File Statistics

| File | Android 9 (lines) | Android 11 (lines) | A9 (KB) | A11 (KB) |
|------|:---:|:---:|:---:|:---:|
| `Handler.java` | 933 | 1,001 | 35 | 39 |
| `Looper.java` | 399 | 476 | 14 | 16 |
| `Message.java` | 630 | 666 | 19 | 20 |
| **Total** | **1,962** | **2,143** | | |

## Multi-Channel Similarity Scores (K=5, W=4)

| File | Raw Winnowing | Normalized | Identifier Cosine | Comment/String | **Composite** |
|------|:---:|:---:|:---:|:---:|:---:|
| `Handler.java` | 0.7513 | 0.8489 | 0.9205 | 0.9080 | **0.8614** |
| `Looper.java` | 0.7714 | 0.8080 | 0.9485 | 0.8000 | **0.8382** |
| `Message.java` | 0.8328 | 0.8602 | 0.9876 | 0.9293 | **0.9025** |

## Key Findings

- **Average composite similarity**: 0.8674
- **Highest similarity**: `Message.java` (0.9025) — least changed between versions
- **Lowest similarity**: `Looper.java` (0.8382) — most evolution
- These files represent Android's core threading infrastructure with moderate-size Java classes (300–900 lines), testing Diffinite's industrial profile on real-world version evolution.