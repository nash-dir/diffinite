# Corpus: cross-language-and-encoding

All files hand-written (c1, c2, c4, c7) or generated (c3, c5, c6). The generator
scripts and the per-mode reports of the original review session were not committed;
the generated inputs are committed as-is.
Each case has `left/` (A, "original") and `right/` (B, "accused").
Current measured results for c1, c2 and c7 are produced by
`python example/benchmark/run_benchmarks.py` into `example/benchmark/RESULTS.md`.

Modes run per case: `default` (deep, raw, threshold 5, +HTML), `simple`, `raw_t1`
(`--threshold-deep 1`), `strip` (`--strip-comments`), `norm` (`--normalize`, default
threshold 93), `norm_strip` (`--normalize --strip-comments` = the only calibrated profile),
`norm_la` (`--normalize --lang-aware`), `norm_t1`, `norm_la_t1` (same with
`--threshold-deep 1` so the underlying Jaccard is visible).

## c1_py_to_js — same algorithm ported Python -> JavaScript
- `route_planner.py` (Dijkstra + delivery window, 117 lines) -> `route_planner.js` (163 lines):
  faithful port, snake_case -> camelCase, `heapq` -> hand-written MinHeap, dict -> Map.
- `csv_ledger.py` (80 lines) -> `csvLedger.mjs` (90 lines): line-by-line port of a CSV
  splitter / amount parser / reconciler; filename changed to camelCase + `.mjs`.
- Expected: line diff low (syntax differs on almost every line). This is a translation;
  a token tool can't be expected to prove it, but it should not crash and should not
  claim near-identity. Normalized mode may surface csv_ledger (statement structure is
  nearly 1:1). Ideal: some non-zero signal for the port, honestly labelled.

## c2_java_to_kotlin_csharp — Java -> C# and Java -> Kotlin
- `InventoryLedger.java` (111 lines) vs `InventoryLedger.cs` (124 lines; near-mechanical
  port: PascalCase methods, Dictionary, ArgumentException) and `InventoryLedger.kt`
  (78 lines; idiomatic Kotlin: `require`, string templates, collection pipeline).
- Expected: only one of .cs/.kt can be 1:1 paired (same stem); the other must go to
  N:M deep compare or be listed as unmatched. Java<->C# normalized similarity should be
  high (structure nearly identical); Java<->Kotlin low/moderate.

## c3_encodings — identical content, different byte encodings
- left: all UTF-8 (no BOM, LF). right: same text as
  `payroll_bom.py` UTF-8 with BOM; `payroll_cp949.py` cp949 (note: file still declares
  `# -*- coding: utf-8 -*-`, a realistic mismatch); `payroll_utf16.py` UTF-16 with BOM;
  `payroll_utf16le_nobom.py` UTF-16-LE without BOM; `Attendance_euckr.java` EUC-KR;
  `Attendance_crlf.java` UTF-8 with CRLF line endings. All Korean comments/strings.
- Expected: every pair is textually identical after decoding -> 100% line ratio and
  ~100% deep Jaccard; SHA-256 differs (bytes differ) and the report should make clear
  that byte-identity != text-identity; no mojibake in the HTML.

## c4_unusual_extensions — same code under unusual/missing extensions
- `geometry.c` -> `geometry.inc` (code identical, 5 comment lines reworded)
- `sync_backup.sh` -> `sync-backup` (no extension, byte-identical)
- `config_loader.py` -> `config_loader.py.orig` (byte-identical)
- `Makefile` -> `GNUmakefile` (byte-identical)
- Expected: byte-identical pairs = 100% regardless of name; geometry ~95% line ratio
  and 100% after comment stripping. Risk: comment stripping / lang-aware chosen by
  extension, so `.inc` / no-extension files may be processed asymmetrically.

## c5_large_file — ~5k-line generated module vs lightly modified copy
- `rule_handlers.py`: 5,290 lines (left) vs 5,271 lines (right). Right = left with
  5 functions renamed (`_v2`), 30 float constants bumped, a 60-line block deleted at
  line 2400, a 39-line new function inserted at line 4000.
- Expected: ~97-99% line similarity, deep Jaccard high (>90%); reasonable runtime.

## c6_empty_and_binary — empty files and binaries mixed with code
- `pkg/rate_limiter.py` identical (control).
- `pkg/__init__.py` empty on both sides (empty vs empty).
- `pkg/limits_config.py` empty on left, 46-line real config on right (empty vs non-empty).
- `logo.png` identical valid PNG (binary identical); `libfast.so` different random ELF-ish blobs.
- `pkg/rate_limiter.cpython-312.pyc` identical "pyc" (header + mostly ASCII + NULs).
- `pkg/helpers.py` real text on left, random binary garbage on right (same name).
- `pkg/py.typed` empty, right only.
- Expected: no crash; binaries reported by hash (identical vs different), not by a
  fake text ratio; empty-vs-empty must not be presented as "100% similar code" without
  qualification; empty-vs-content must be 0%; text-vs-binary should be flagged, not scored.

## c7_trap_unrelated_cross_lang — false-positive control
- `Validator.java` (sign-up field validation) vs `Validator.cs` (sensor ring buffer):
  same class name, same C-family boilerplate, unrelated logic.
- `scheduler.py` (cron parser) vs `scheduler.js` (meeting-room allocator): same
  filename stem, unrelated logic.
- Expected: low scores in every mode; normalized mode must not cross 93 here.
