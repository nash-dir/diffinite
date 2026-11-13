# Changelog

## [0.14.0] — unreleased

### Breaking

- **Sensitive files are excluded by default.** A tree containing `.env`, `id_rsa`, `*.pem` and similar files now yields a smaller evidence set than 0.13.x for the same command line. Each excluded file is disclosed in the reports. Pass `--sensitive-files include` for the previous behaviour.
- **Fail-closed by default.** Unreadable/undecodable source files, hashing or worker failures and a truncated Deep Compare index now abort the run instead of producing a silently partial report. Pass `--allow-partial` to get an explicitly marked incomplete report (the old behaviour, now disclosed).
- **Deep Compare no longer strips comments unless `--strip-comments` is given.** Jaccard values for the same command line differ from 0.13.x. The measured normalize false-positive figures apply only to `--normalize --strip-comments` with default K/W; other runs are labelled `unvalidated-profile`.
- **JSON report schema v2** (`schema_version: 2`). The default `threshold_provenance` value is now `legacy-uncalibrated` (was `default`). The extension requires a schema-v2 report, i.e. diffinite ≥ 0.14.0 when using a system Python.

### Added

- **Excluded inputs are listed.** Every file or directory left out by `--ignore-file`, `--include` or the sensitive-file preset is disclosed with the rule that removed it: the reports give the count (status row *Inputs excluded by policy*) and, unless `--uncompared-files none`, the list (section *Excluded Inputs*, or the `*_uncompared.txt` file with `separate`); the JSON report (`analysis_status.exclusion`) and the manifest always carry the full list. Before, only the rule count and the ignore file's SHA-256 were recorded.
- **`--sensitive-files {exclude,include,error}`**, default `exclude`: `.env` files, private keys and credential files (a fixed, versioned list matched by name, ignoring case) are no longer hashed, bundled or copied into reports. `include` restores the previous behaviour; `error` stops the run before anything is written. The extension has the same choice in the Options panel.
- **`--include PATTERN`** (repeatable): collect only matching files. Applied during collection, unlike `--filter-json`, so it also limits hashing, the manifest and the bundle.
- **`--bundle-sources {full,none}`**: `none` writes the `--bundle` ZIP without the source files; the manifest still lists their SHA-256 digests.

- **Directional containment** in every Deep Compare table and the JSON report: *A in B* = shared ÷ unique fingerprints of A, *B in A* = shared ÷ unique fingerprints of B (analogous to the 원본 기준 / 비교본 기준 ratios of Korean software appraisal and the per-direction similarity of JPlag/Dolos, but counted in unique fingerprints). For a pair that is listed, a file copied whole into a larger file now reads ~100% instead of a diluted Jaccard. Descriptive only — rows are still selected by the Jaccard threshold, so a small file inside a much larger one can remain unlisted. JSON adds `unique_hashes_a`, `unique_hashes_b`, `containment_a_in_b`, `containment_b_in_a`.
- **Out-of-sample validation** (`python -m tests.validation.holdout`): leave-one-assignment-out on IR-Plag and an independent check on the SOCO 2014 training set; results in `example/validation/holdout.md`. `example/download_examples.py --dataset soco14` fetches the SOCO training set pinned by SHA-256.
- Deep Compare now lists files it skipped as binary or not decodable as text, with the reason (`analysis_status.deep.skipped_binary_files`), instead of counting them as processed. Files read but shorter than one k-gram are listed as `unfingerprinted_files`, and `--lang-aware` lexer fallbacks as `lang_aware_fallback_files`.
- Reports and the manifest record the Python, Unicode data and Pygments versions and, with `--lang-aware`, the tiers used (fingerprints depend on them).
- Evidence hardening: a private source snapshot whose SHA-256 hashes are verified at creation, before analysis and before commit, transactional multi-format output with rollback, provenance of ignore/filter policies, CSV formula-injection escaping.

### Fixed

- `--strip-comments`: a C-style block comment between two identifier or number characters (e.g. `int/*a*/x`) is now replaced by one space, as a compiler treats it, instead of joining the tokens into a non-existent identifier (`intx`). Stripped text, line diffs and fingerprints can differ from 0.13.x for such code. Markup comments (`<!-- -->`) are unchanged. The IR-Plag calibration corpus contains no such pattern, so the calibration figures are unchanged.
- `#if 0 … #else … #endif`: the live `#else`/`#elif` branch was deleted as dead code, and a nested `#ifdef` inside `#if 0` ended the dead block early. `#if 0 // comment` is now recognised.
- The line channel stripped comments from **both** files with File A's language rules; each file now uses its own.
- A binary file saved under a source extension (e.g. a compiled blob named `.py`) no longer aborts the whole run; Deep Compare skips it and lists it in the report as skipped (binary or not decodable as text).
- Under `--allow-partial` with a truncated Deep Compare index, *Shared Hashes* undercounted while Jaccard did not; both (and containment) now use the same full fingerprint sets.
- An unterminated `#if 0` (e.g. inside a comment) no longer blanks the rest of a C file.
- When one file of a pair has an unregistered extension (`Foo.java` vs `Foo.java.orig`), `--strip-comments` now applies the registered partner's rules to both sides, in the line diff and in Deep Compare. Extensions whose comments were kept are named in the comment-mode labels and the JSON.
- `example/download_examples.py` could not fetch IR-Plag (upstream now ships a nested zip) and only targeted case-01. It now fetches all 7 cases from a pinned commit and verifies SHA-256, so the calibration corpus is reproducible.
- Tests importing `tomllib` no longer break collection on Python 3.10.
- Windows junctions are now detected on Python 3.10 and 3.11 too (the check relied on `Path.is_junction`, which only exists from 3.12), so an output path through a junction is refused on every supported version.
- A failure before report writing no longer leaves the plaintext source snapshot in the temp directory until garbage collection; it is removed immediately.
- Extension error messages keep the last 8 KB of stderr instead of only the last chunk, so a traceback is not cut mid-line.
- `calibration.json`: the `fp_le_5` point mixed two denominators; its count and confidence interval now use the same negatives as its rate. The shipped `fp_le_1` point is unchanged, and a new test ties the constants quoted in reports to this file.

#### Comparison and reports

- Reports no longer show a difflib percentage or +0/−0 for pairs compared only by SHA-256 (binary or undecodable, or over `--max-file-size`); they say "Not compared by difflib (…); SHA-256 identical/different". The PDF, exhibit CSV and index.html show `—` for their line counts. JSON keeps `ratio` and adds `comparison_method`, `hash_only_reason` and `comparison_note`. `--sort-by ratio` ranks only difflib pairs.
- Pairs that could not be compared (unreadable file, or a decode failure under `--binary-handling error`) count as failed, mark the run incomplete (`diff-pair-error`) and show "Not compared (…)" instead of 0.0%, in every format. With `--binary-handling error`, an unreadable file is labelled as a read error, not "Could not decode".
- `--binary-handling exclude` lists every matched pair it left out (JSON `excluded_pairs`, Markdown, HTML, PDF, status). Those pairs are no longer counted as successful. Unreadable files are never excluded.
- Jaccard and containment are stored exactly instead of rounded, and are shown as 100% only when exactly identical (a near-identical pair is no longer shown or stored as 1.0).
- Filtered (selected) runs state how many unmatched files they left out (`analysis_status.selection`) instead of reporting 0.
- `--by-word` rows show the source whitespace exactly and highlight whitespace-only differences; moved-block markers are kept with `--detect-moved`.
- Text such as `border: 1px solid #abc` in source code is no longer deleted from the displayed diff.
- A UTF-8 BOM is ignored on every decode path (a BOM file and its copy without one now score 100% with `--encoding utf-8` too), and at the start of the ignore file or filter JSON.
- File names in Markdown are shown literally, and control characters as visible symbols, so a name cannot create headings or rows.
- A drive or share root (e.g. `Z:\`) gets a non-empty directory label. The recorded deep threshold is exactly the value given (57, not 56.99999999999999).
- A file name containing a lone UTF-16 surrogate stops the run before analysis with a message naming the file, instead of crashing after it. If an unreadable-file log already exists, this run's entries go to the error log instead of being lost.

#### Deep Compare and `--lang-aware`

- A file with an unregistered extension that cannot be read now fails the run (use `--allow-partial` to continue); one that can be read but not decoded is listed as skipped. Neither is counted as processed.
- All modes: source is NFC-normalized and identifiers keep their combining marks (Devanagari, Thai, NFD accents), so NFC and NFD copies match. Fingerprints change only for such input.
- `--lang-aware`: R (`.r`) and Perl (`.pl`/`.pm`) are lexed as R and Perl, not REBOL, Prolog or Promela; their scores change.
- `--lang-aware`: a file its lexer cannot handle (e.g. Kotlin, C# or Ruby with Korean identifiers) uses the registry-keyword tier for the whole file, and is logged and listed. Renamed clones are no longer missed.
- `--lang-aware`: SQL, PHP, HTML and CSS-family keywords are compared regardless of case, and each string literal counts as one `STR` token, so escapes and string length no longer change fingerprints.
- `--workers` above 61 is rejected at startup on Windows instead of crashing; the pool is capped at 61 there. Pool workers exit when the analyzer process dies.

#### Comment stripping (`--strip-comments`; scores can change for these languages)

- Shell and Zsh keep code after a `#` inside a word (`$#`, `${#arr[@]}`, `x#y`); YAML keeps `#` with no space before it (`url#anchor`); Perl keeps `$#arr`; PHP 8 `#[Attribute]` lines are kept.
- `'''` and `"""` open a multi-line string only in Python, Java, Kotlin, Scala, Swift and C#; before, SQL `''''` or C `""""` could leave comments unstripped for the rest of the file.
- A backslash at the end of a line no longer escapes the first character of the next line, and a string ending in a backslash continues onto the next line (LF and CRLF files).
- `#if 0` blocks are removed only in C, C++ and C#, and a `#if 0` inside a comment or string no longer deletes the live code after it.
- Nested block comments in Rust, Swift, Kotlin and Scala are removed completely. Go raw strings ending in a backslash or containing `${`, and Rust lifetimes (`'a`), no longer stop comments from being stripped.

#### Collection and ignore rules

- Ignore patterns are matched case-sensitively on every OS (before, Windows ignored case and Linux/macOS did not).
- Ignore patterns follow gitignore rules: `dir/` matches directories at any depth, `**/x` also matches at the root, `*` no longer crosses `/` (`src/*.py` no longer excludes `src/a/b.py`), and a leading `/` anchors to the root. `!` negation and `\` escapes are not supported.
- A linked or junction directory excluded by the ignore policy is no longer reported as a collection failure.
- Files that are listed but cannot be collected are disclosed and make the run incomplete: stat failures, non-regular files, file reparse points and, on Windows, names ending in a dot or a space. Before, they were dropped silently.
- When several unmatched files share a name, pairing prefers the counterpart with the same parent directories instead of sorted-path order. The Name Sim. value is unchanged.

#### PDF, CLI and evidence

- PDF: fullwidth punctuation, enclosed CJK (㈜), Hangul Jamo (NFD file names) and CJK Extensions C–G are drawn with the CJK font instead of black squares.
- PDF: `--pdf-font`, `--pdf-lang` and the Consolas/Menlo code font are now actually embedded (before, they were silently ignored); a missing or unloadable `--pdf-font` is an error.
- PDF: Hangul Bates prefixes and suffixes are stamped correctly; other characters outside Windows-1252 are refused instead of being printed as black squares.
- PDF cover: the comment-mode label names the extensions whose comments were kept, and the status block uses the same wording as the other reports.
- CLI: unknown or non-text `--encoding` values and `--max-file-size` / `--max-diff-html-size` values under 1 byte or overflowing are rejected at startup.
- Manifest and bundle: a folder above the output whose name ends in `_files` no longer appears in report paths, and exports into such folders no longer fail.
- Evidence: a drive-letter-like component (`C:x`) is rejected at any depth; other colons in file names are accepted. On macOS the analysis snapshot no longer fails because the temp directory is under the `/var` symlink.
- Calibration: `--strip-comments` runs that include files with no comment rules are marked as an unvalidated profile.

#### Release and validation

- The tag workflow runs the full CI workflow and the test suite against the hash-locked bundle dependencies before building, and smoke-tests the built wheel before uploading.
- Annotated tags are accepted; `gh release` works without a checkout; marketplace publishing can be re-run safely (byte-identical VSIXs already published are skipped, different bytes fail); PyPI publishes only after the marketplaces.
- Validation harness thresholds use the engine's exact `jaccard >= t/100` comparison, which changes the normalize t=58 recall in `pr_curve.csv`. Corpus digests are platform-independent: the published SOCO digest changes from `131e9295…` to `c9fee2d4…` (same bytes). Calibration outputs record the measured corpus digest and refuse an unpinned corpus.
- `run_benchmarks.py --check` also compares threshold, provenance, comment mode, title and command, and fails when committed cases are missing or not re-run (`--allow-skips` to override).

### Extension

- **Review screen.** The Tree Viewer opens with a summary of counts and settings read straight from the analyzer's JSON (analysis state, matched and unmatched files, error and hash-only pairs, Deep Compare candidates, settings). A value the report does not carry is shown as `unknown`, never guessed.
- **Report presets** at export time (As configured / Technical report / Evidence report). A preset only switches output flags (page/file/Bates numbers, SHA-256 table), never matching or metrics, and the export dialog lists exactly what the report will contain.
- **Clearer failure messages.** A failed analysis or export now shows a short cause and next step (runtime missing, unreadable input, partial result refused, PDF failure, out of memory, …) with the full stderr in the *Diffinite* output channel.
- **Theme support.** All webviews use VS Code theme colors, so Light, Dark and High Contrast themes render correctly.
- **Fixed:** a Bates suffix or prefix starting with `-` (e.g. `-CONFIDENTIAL`) was read by the CLI as an unknown option and the run failed.
- **Fixed:** with *Binary files: Exclude*, a valid report was rejected as inconsistent because excluded binary pairs leave no result row.
- **Fixed:** hash-only pairs (binary or over `--max-file-size`) were shown as a content-similarity percentage. They now show the analyzer's own note (e.g. *Not compared by difflib (binary or not decodable as text); SHA-256 identical*) and `—` instead of +0/−0, and pairs with an error read *not compared*. A ratio, Jaccard or containment below 1 is never shown as 100.0%.
- The bundled Windows runtime no longer ships pip console-script launchers (`site-packages/bin/*.exe`).
- Wording: the extension README and help no longer describe SHA-256 hashes as chain-of-custody evidence, results as "legally sound", or the time hint as "calibrated"; the Options table now shows the real GUI defaults (No Autojunk, Hash and page/file/Bates numbers on). Bates presets pre-fill the start number but do not update it after export (the unused auto-update helper was removed); set the next unused number before each export.
- **Changed:** the Tree Viewer also lists files in A that have no 1:1 pair (Deep Compare cross-file matches such as renamed files, and unmatched files), so they can be included in the final report; before, their Deep Compare matches silently dropped out. Files with a Deep Compare similarity candidate are pre-selected, so the default selection can differ from 0.13.x. Phase 1 always lists unmatched files for this review, whatever the *Uncompared files* option says.
- **Changed:** the exclusion list (`~/.diffignore`) is read once when an analysis starts; Phase 2 and every export of that analysis use those exact bytes, so editing the file afterwards no longer changes an export. After Phase 2 the extension compares input SHA-256 values, the exclusion list and the pairing of the selected files with the reviewed Phase 1 and shows a warning (and a banner in Results) on any difference. An export whose input files no longer match the results on screen is not published.
- **Changed:** *Edit Dictionary* (Options panel) now creates `~/.diffignore` with every example commented out (and anchored, e.g. `/build/`). Previously it enabled bare names such as `build`, `env` and `target`, which removed source folders of those names at any depth from every later run. An existing file is not changed. The Options panel, review summary and Results header now state whether an exclusion list is active, with its rule count and SHA-256.
- **Changed:** the time-estimate pre-scan no longer blocks VS Code: it runs in the background inside the cancellable Phase 1 progress and skips files the exclusion list removes.
- **Changed:** Simple mode no longer shows K, W, a Jaccard threshold or the "Uncalibrated legacy threshold" warning, since no fingerprinting runs in that mode.
- **Changed:** the Options panel refuses to run with an empty or invalid number field (an empty threshold was sent as 0); a saved file-name threshold of 0 now loads back as 0, not 60.
- **Fixed:** a Deep report in which Deep Compare skipped binary files was rejected as malformed. Skipped files are now accepted and shown in the summary and banners as *skipped (binary or not decodable as text)*, with each file's reason; files below k-gram size and `--lang-aware` lexer fallbacks are shown too.
- **Fixed:** reports with pairs left out by *Binary files: Exclude*, or with pairs that could not be compared, were rejected as inconsistent. They are now accepted (requested = successful + failed + excluded; one result row per successful or error pair), and the excluded pairs are listed in a banner, the review summary and the Results header. Reports without these fields are still accepted.
- **Changed:** a selective report states how many unmatched files it left out (review summary and banner). The selection note now says that the B unmatched list is omitted and that the A unmatched list shows only the selected A files.
- **Changed:** the Options panel checks the Bates prefix and suffix as you type and refuses to run when they contain characters the stamp cannot draw (only Windows-1252 Latin, or Hangul with ASCII; the CLI refuses the rest). It also refuses more than 61 workers on Windows.
- **Changed:** the `~/.diffignore` template states that matching is case-sensitive on every OS (one line per spelling, e.g. `Thumbs.db` and `thumbs.db`), that `name/` matches folders at any depth and `*` does not cross `/`, and that `!` negation and `\` escapes are not supported.
- **Fixed:** an export could delete an existing `<name>_files` folder (including unrelated user files) and another run's `manifest.sha256.json` or `<name>_uncompared.txt`. The folder is now replaced only when a prior Diffinite manifest covers exactly its files with matching SHA-256; otherwise the export is refused before the analyzer runs. The bare manifest and legacy uncompared list are removed only when that manifest describes nothing but the report being replaced.
- **Fixed:** a merged export over an earlier split export of the same report left the old `<name>_files` folder on disk with no manifest; it is now removed in the same transaction (when that manifest owns it unchanged).
- **Fixed:** a staged manifest path that does not resolve inside the export folder now fails with a message naming the path, instead of a bare ENOENT.
- **Fixed:** "Preserve original folder tree" stayed disabled after ticking No Merge (or loading a history entry).
- **Fixed:** cancelling after the Python process had exited no longer skips killing its still-running worker processes (POSIX process group). On Windows, `taskkill` is no longer run once the analyzer has exited, because its process ID may already belong to another program; the cancellation message then says that worker processes may still be running instead of reporting a clean stop.
- **Fixed:** pipeline step messages now appear in the progress notification (they were read from the wrong stream), and Korean or other multi-byte text in error output is no longer garbled at chunk boundaries.
- **Fixed:** an output-side PermissionError (e.g. the report open in a PDF viewer) is reported as "report could not be written" instead of "input files could not be read", and exit codes such as 255 are no longer reported as an invalid option.
- **Fixed:** closing the Results or Options panel during a run no longer hides the "report saved" notice or replaces the real error; the save dialog now opens in the workspace folder (or next to folder A) instead of the drive root.

### Docs

- Corrected the K=5 rationale (Schleimer 2003 has no §4.2 and prescribes no k for source code), the "always detected" wording (a shared fingerprint is guaranteed; reporting still depends on the threshold), the collision-probability claim, and the Oracle v. Google wording that called token overlap "structural similarity".
- README Limitations now state plainly: no parsing/AST analysis, language-agnostic normalization keyword list, deep channel gives no line locations for N:M matches.
- Calibration disclosure now states Java-only scope, clustering in 7 assignments, and that the single false positive scored 100%.
- NOTICE corrected: datasets are downloaded, not tracked; earlier history did contain copies; citations fixed.

## [0.13.1] — 2026-06-23

### Docs

- Extension README: updated Normalize option description to document the calibrated threshold (93) and 45-token inconclusive band; corrected "Content Match" → "Line match (difflib)" in the Cover Page table; added Inconclusive column to the Deep Compare table; corrected Threshold (Deep) default to reflect channel-dependent behaviour.

## [0.13.0] — 2026-06-23

### Added

- **Measured normalize false-positive rate.** `--normalize` (identifier flattening) collapses small, standard code onto identical fingerprints, so independent work and renamed copies can score the same. A validation harness (`tests/validation/error_rate.py`, run via `python -m tests.validation.error_rate`) now measures precision/recall per file pair on the Karnalim IR-Plag corpus and commits the evidence under `example/validation/`. Every `--normalize` report discloses its measured false-positive rate — with the Wilson confidence interval, the per-level recall (near-verbatim only), and the small-file scope — so a flagged match is not read as a known copy verdict.
- **Calibrated normalize operating point.** Under `--normalize`, `--threshold-deep` now defaults to **93** (calibrated for false-positive ≤ 1%) instead of 5, and matches whose smaller file is below a 45-token floor are reported as **inconclusive** rather than confident findings. The raw (non-normalize) default stays 5.
- **`--lang-aware`** (opt-in): language-aware normalization via Pygments lexers (falling back to per-language keyword sets) so keywords like Rust `fn`/`pub` or Go `func` are preserved instead of flattened to `ID`, reducing false positives on non-JVM/Python/JS languages.
- **Unicode/i18n example** (`example/unicode`) and end-to-end coverage for non-ASCII filenames, CJK/Cyrillic/Arabic content, and emoji.

### Changed

- The "Content Match" headline is relabelled **"Line match (difflib)"** across all report formats, and the difflib `autojunk` state is now shown in every Analysis Configuration banner — the figure is a line-level difflib ratio, not semantic similarity.
- A deep-compare file-size cap (`--max-file-size`) now also bounds fingerprint extraction, so an untrusted large/pathological file cannot hang a run.

### Fixed

- Resolved dormant type-hint/import issues, an `AnalysisMetadata` field-order hazard, and a library entry point that omitted the normalize disclosure.

## [0.12.2] — 2026-06-22

### Fixed

- **Report labels — filename vs. content similarity**: every report format now shows filename similarity and content match as two clearly-labelled, distinct figures, so a 100% filename match is no longer mistaken for identical file content. The CSV exhibit index gains a `Content Match (%)` column alongside `Name Sim. (%)`; the Markdown summary, HTML evidence index, and per-file diff pages are relabelled consistently; binary pairs report their SHA-256 match status. (The PDF cover and JSON report already separated the two values.)

### Docs

- Corrected and expanded both READMEs: comment-stripping coverage (45+ extensions, derived from the language registry), previously-undocumented CLI flags, a PDF Font / CJK rendering section, and the `diffinite.pdfLang` / `diffinite.pdfFont` settings. Fixed the extension README's FSM state count, broken `master` license links, and the default deep-threshold value.

### Chore

- `.gitignore` now ignores generated CLI report outputs left in the `example/` root.

## [0.12.1] — 2026-06-17

### Security

- **Webview hardening**: every webview (options panel, result viewer, tree viewer) now sets a strict Content-Security-Policy with a per-render nonce, closing the script-injection surface. Rendered `html_diff` is backend-escaped and CSP-protected.

### Fixed

- **Cancellation, temp files, argument passing**: in-flight analysis/export processes are reliably terminated on cancel and temporary working files are cleaned up; hardened how analysis options and temp paths are forwarded to the bundled Python backend.

### Changed

- **Supply-chain hardened bundle build**: `build_bundle.ps1` now installs the embedded-Python dependencies from a pinned, hash-verified `requirements-bundle.lock` via `pip install --require-hashes`, with SHA-256 verification of the Python embeddable zip and `get-pip.py`.
- **Smaller VSIX**: the bundle prune step is fixed (it previously pruned nothing) and now runs last; `pip-licenses` is built in a throwaway directory instead of shipping into the runtime, dropping ~12 MB of `__pycache__`/`.pyc` and build-only packages.

### Docs

- Added a Platform Support matrix to the README; the embedded-Python runtime is scoped to Windows (macOS/Linux use system Python via the CLI).

## [0.12.0] — 2026-03-31

### Added

- **Parallel execution**: multi-process Phase-2 rendering for faster reports on large selections.
- **Persistent Options Panel**: the options panel remembers the last run's settings and directories.

### Fixed

- **CJK font rendering** in PDF output.

## [0.11.1] — 2026-03-28

### Fixed

- **CI/CD Pipeline**: Restore pytest across Python 3.10–3.13, add `libcairo2-dev` for Ubuntu runner, fix `vsce --dry-run` removal (unsupported in v3.x), unify release.yml to `pwsh`.
- **Tests**: Update `TestBreakPath` assertions to match CSS-based word wrapping (no more `<wbr>` tags).
- **Tests restored to repo**: 18 test files re-added with `skipif` guards for external-data tests.

### Changed

- **VSCE README**: Document progress bar, OOM defense, time estimation, SHA-256, encoding, uncompared modes, embedded Python runtime.
- **PyPI metadata**: Expand keywords for better discoverability (side-by-side, similarity, jaccard, copyright, litigation, vscode).
- **CI dependency chain**: VSCode Bundle job now requires all pytest jobs to pass first (`needs: test`).

## [0.11.0] — 2026-03-28

### Added

- **Real-time Progress Bar**: Python backend stdout (`[Worker-N] X/Y`) is parsed and fed into VS Code's native progress API for live percentage tracking.
- **Pre-analysis Time Estimation**: `dirScanner.ts` scans file sizes upfront and estimates Simple/Deep mode duration before analysis begins.
- **Dynamic CPU Calibration**: Phase 1 execution time is benchmarked to calibrate Phase 2 rendering time predictions (clamped 0.2x–5.0x).
- **OOM Defense**: Warns users when file pairs exceed 5MB, preventing silent crashes on large binary/generated files.
- **Uncompared File Modes**: `--uncompared-mode {inline,separate,none}` controls how unmatched files appear in reports.
- **Evidence Integrity Hashes**: `--hash` flag embeds SHA-256 hashes for all analyzed files directly in the report.
- **JSON Report Output**: `--report-json` for machine-readable output consumed by the VS Code extension tree viewer.
- **Default Export Filename**: Save dialog now defaults to `{dirA}_{dirB}_{timestamp}` pattern.

### Fixed

- **PDF Table Layout**: Removed `xhtml2pdf` shrink mode that minified fonts; applied `table-layout: fixed` with explicit column width weights.
- **PDF Word Wrap**: Replaced broken `<wbr>` hack with `pdf-word-wrap: CJK` for reliable long-path wrapping across all tables, lists, and body text.
- **Column Width Distribution**: Summary (4%/#, 34%/FileA, 34%/FileB, 8%/NameSim, 10%/Match, 5%/Added, 5%/Deleted), Deep Compare (40%/40%/10%/10%), Hash Evidence (5%/60%/20%/15%).

## [0.9.3] — 2026-03-18

### Added

- **Moved Block Detection**: `--detect-moved` flag detects code blocks that were moved (not just added/deleted) and highlights them in purple (original position) and blue (destination).
- **Bates Prefix / Suffix / Starting Number**: `--bates-prefix`, `--bates-suffix`, `--bates-start` CLI flags for customizable Bates labels (e.g. `PLAINTIFF-0001-CONFIDENTIAL`). Font auto-shrinks when label exceeds 30 characters.
- **Bates Presets (VSCode)**: Save case-specific Bates configurations in `settings.json` as `diffinite.batesPresets`. Select a preset in the GUI to auto-fill prefix/suffix/start fields.
- **Options Panel**: New fields for Detect Moved, Bates Prefix, Suffix, Starting Number, and Preset dropdown.

### Fixed

- Extension now correctly passes `--encoding`, `--sort-by`, `--sort-order`, and `--detect-moved` to CLI.
- Dark-mode CSS for moved-block highlighting in diff viewer.

## [0.6.0] — 2026-03-18

### Added

- Initial Marketplace release (version synced with PyPI)
- **Compare Directories** command with GUI options panel
- Scrollable block-by-block diff viewer
- Report export (PDF / HTML / Markdown)
- Configurable analysis options: mode, comment stripping, normalization, thresholds
- Bundled binary resolution with Python fallback
