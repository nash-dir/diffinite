# SQLite Example Analysis Report

> Generated: 2026-03-14 11:15
> Dataset: `example/sqlite/`

## Overview

Cross-version comparison of SQLite amalgamation source files.
Two versions of the SQLite C source are compared to measure
code evolution similarity using Diffinite's multi-channel algorithm.

## File Statistics

| File | Left (lines) | Right (lines) | Left (KB) | Right (KB) |
|------|-------------|--------------|-----------|-----------|
| `sqlite3.c` | 255,637 | 257,674 | 8,804 | 8,876 |
| `sqlite3.h` | 13,356 | 13,426 | 625 | 628 |
| `sqlite3ext.h` | 720 | 720 | 37 | 37 |
| `shell.c` | 29,637 | 31,096 | 889 | 935 |
| **Total** | **299,350** | **302,916** | | |

## Multi-Channel Similarity Scores (K=5, W=4)

| File | Raw Winnowing | Normalized | Identifier Cosine | Comment/String | **Composite** |
|------|:---:|:---:|:---:|:---:|:---:|
| `sqlite3.c` | 0.9547 | 0.9899 | 0.9998 | 0.9621 | **0.9812** |
| `sqlite3.h` | 0.9905 | 1.0000 | 1.0000 | 0.9890 | **0.9963** |
| `sqlite3ext.h` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **1.0000** |
| `shell.c` | 0.9472 | 0.9643 | 0.9992 | 0.9171 | **0.9621** |

## Key Findings

- **Average composite similarity**: 0.9849
- **Highest similarity**: `sqlite3ext.h` (1.0000)
- **Lowest similarity**: `shell.c` (0.9621)
- **Total codebase size**: 299,350 + 302,916 = 602,266 lines
- The SQLite amalgamation is a massive monolithic C file (~250K lines), ideal for stress-testing Diffinite's industrial-scale performance.