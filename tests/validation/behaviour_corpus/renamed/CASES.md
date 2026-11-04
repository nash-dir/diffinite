# Corpus: renamed (Type-2 clones)

Each case is `<case>/left` (original, "A") vs `<case>/right` (derived, "B").
Left files are hand-written; most right files were derived with
`scratchpad/tools/rename.py` (whole-word identifier mapping, mapping JSONs
`scratchpad/tools/m0N.json`) plus sed literal edits, so the transformation is
exactly reproducible. Reports are in `<case>/out/<mode>.json` (+ `.log`).

Modes run: `simple` (--mode simple), `deep` (default), `deep_strip`
(--strip-comments), `norm` (--normalize), `norm_strip` (--strip-comments
--normalize; the calibrated profile), `norm_lang` (+ --lang-aware),
`norm_strip_t0` (calibrated profile with --threshold-deep 0, to see the raw
score that the 93 threshold hides).

| Case | Files | Transformation | Expected from a fair tool |
|---|---|---|---|
| c01_py_rename | inventory.py (115 lines) -> stock_ledger.py | Every class/function/variable/attribute renamed (~45 identifiers); file renamed; a few string words also changed by the renamer. Control flow, structure, literals otherwise identical. | Raw line/token similarity low (most lines touched). Normalized deep should be ~100% (pure renaming). Since names differ, 1:1 pairing will not happen; deep N:M must find it. |
| c02_java_types | AccountService.java (138) -> WalletManager.java | Identifier renaming + type change double/int -> long everywhere, package renamed. | Same as c01: raw low, normalized ~100% (types are identifiers to a non-lang-aware normalizer; lang-aware should still be very high). |
| c03_js_literals | rateLimiter.js (99) -> rateLimiter.js | Literal-only: 14 lines with changed numbers/strings/status codes; all identifiers identical. | Line ratio ~85%; raw deep high but < 100; normalized deep ~100%. |
| c04_c_rename_reformat | ringbuf.c (126) -> circular.c | Identifier renaming + reformat: K&R -> Allman braces, 4-space -> tab, operator spacing removed, single-return blocks collapsed to one line. | Line diff very low; token-based normalized deep should still be ~100% (whitespace/brace placement is token-neutral except collapsed blocks keep same tokens). |
| c05_go_full_type2 | lexer.go (130) -> scanner.go | Full Type-2: identifier renaming + float64 -> float32 + ParseFloat bitsize literal 64 -> 32 + error message strings changed. | Raw low-moderate; normalized ~100% (ignoring literal values). |
| c06_trap_independent | scheduler.py (82) vs task_queue.py (78) | NEGATIVE CONTROL: two independently written priority job queues for the same spec (heap vs bisect, slots class vs dataclass, different retry logic). | Low score in every mode; normalized must stay well below 93 and must not be presented as copying. |
| c08_java_rename_only | AccountService.java -> WalletManager.java | Control for c02: same renaming, NO type change (double/int kept). Added after c02 scored 0.70. | Normalized ~100%. Isolates the effect of the type change in c02. |
| c07_py_partial | textutils.py (78) vs strings_helper.py (79) | PARTIAL COPY: 2 of 7 functions (levenshtein, wrap_paragraph) copied with renaming; other 5 functions on each side unrelated. | Normalized deep moderate (roughly 25-40% Jaccard) and must not reach the 93 "flag" level; a fair tool should still let a reader see that two functions match. Raw low. |
