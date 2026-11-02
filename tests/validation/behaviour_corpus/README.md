# Behaviour corpus (hand-written, regression use only)

Small `left/` vs `right/` source pairs written to probe how Diffinite reacts to
specific, known transformations. Each category folder has a `CASES.md` stating
the transformation applied to each case and the outcome a fair tool should
report.

| Folder | What it probes |
|---|---|
| `exact-and-cosmetic/` | identical copies, whitespace / blank-line / comment / CRLF changes, unrelated negative controls |
| `renamed/` | identifier renaming, literal and type changes (Type-2) |
| `restructured/` | reordering, insertion/deletion, split / merged files, extracted helpers, loop rewrites, partial copies (Type-3) |
| `false-positive-traps/` | framework boilerplate, licence headers, generated code, independent implementations of the same algorithm, vendored libraries, tiny files |
| `cross-language-and-encoding/` | ports across languages, UTF-8 BOM / cp949 / EUC-KR / UTF-16, unusual extensions, a large generated file, empty and binary files |

**Limits — read before citing.** The cases were written by an AI agent during a
2026-11 review session, by the same process that reviewed the code, so they are
not independent ground truth. Use them as a regression and behaviour suite
("this transformation must keep scoring above / below that one"), never as an
accuracy or error-rate measurement. Measured error rates come only from the
external corpora in `tests/validation/error_rate.py` and `holdout.py`.

Files here are kept byte-exact (`.gitattributes`: `-text`) because several
cases depend on specific encodings and line endings.
