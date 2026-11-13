/**
 * Fixed notices shown on the review screen and the result viewer.
 *
 * The wording is the same as the Python reports (src/diffinite/notices.py),
 * so the screen and the exported report state the same limits. Every screen
 * that states one of these notices imports it from here; test/polish.test.js
 * compares each constant with notices.py.
 */
export const SCOPE_NOTICE =
  "Similarity figures measure textual and token overlap between the files compared. " +
  "They do not establish copying, derivation or infringement.";

export const SHORT_CODE_NOTICE =
  "Short files and small code fragments can show high similarity even when written independently, " +
  "because language syntax and common idioms leave little room for variation.";

export const INTEGRITY_NOTICE =
  "SHA-256 digests identify the exact files analyzed. A digest shows that a file is unchanged only when it is " +
  "compared with an independently retained copy. The manifest is not a digital signature.";

/** Scope and Limitations list items (plain text) for a webview. */
export const SCREEN_NOTICES: readonly string[] = [SCOPE_NOTICE, SHORT_CODE_NOTICE];

/**
 * calibration.INCONCLUSIVE_TOKEN_FLOOR: a Deep Compare match is marked
 * inconclusive when the smaller file has fewer normalized tokens than this.
 * The value is set in calibration.py; test/polish3.test.js checks it.
 */
export const INCONCLUSIVE_TOKEN_FLOOR = 45;

/** notices.INCONCLUSIVE_NOTICE: shown wherever an inconclusive Deep Compare match is shown. */
export const INCONCLUSIVE_NOTICE =
  "A match is marked inconclusive when, after normalization, the smaller file " +
  `has fewer than ${INCONCLUSIVE_TOKEN_FLOOR} tokens. This is a precaution; no ` +
  "separate error rate was measured for matches between files this short.";

/**
 * Row labels of the reports' Analysis Status table, word for word as
 * notices.analysis_status_rows. A screen that shows one of these figures uses
 * the label from here; test/polish3.test.js compares the set with notices.py.
 */
export const STATUS_LABELS = {
  state: "State",
  inputsNotRead: "Inputs not read",
  inputsExcluded: "Inputs excluded by policy",
  pairsCompared: "File pairs compared",
  pairsFailed: "File pairs failed",
  pairsExcluded: "File pairs not compared (--binary-handling exclude)",
  selectionOmitted: "Unmatched files omitted by the selection filter",
  diffsTruncated: "Inline diffs truncated",
  deepProcessed: "Deep Compare files processed",
  deepFailed: "Deep Compare files failed",
  deepSkipped: "Deep Compare files skipped (binary or not decodable as text)",
  deepBelowKgram: "Deep Compare files with fewer tokens than the k-gram size",
  langAwareFallback: "Language-aware lexer fallback (registry keywords used)",
  deepReported: "Deep Compare pairs at or above the threshold",
  deepIndex: "Deep Compare index",
} as const;
