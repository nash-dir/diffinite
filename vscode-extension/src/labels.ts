/**
 * Display formats for figures and settings shown in the webviews.
 *
 * These mirror the report-wide helpers in src/diffinite/models.py
 * (percent_label, line_match_label, overlap_label, name_similarity_label,
 * threshold_label, count_label), so a figure reads the same on screen and in
 * the exported Markdown, HTML and PDF reports. test/polish.test.js checks the
 * outputs against values produced by the Python helpers.
 */

/** Decimals for line (or word) match and file-name similarity (models.LINE_MATCH_DECIMALS). */
export const LINE_MATCH_DECIMALS = 1;
/** Decimals for Jaccard and containment (models.OVERLAP_DECIMALS). */
export const OVERLAP_DECIMALS = 2;

/**
 * `value.toFixed(decimals)` with Python's rounding of an exact tie (half to
 * even, as in `f"{value:.{decimals}f}"`). Both round the exact binary value;
 * they differ only when that value lies exactly halfway, where JavaScript
 * rounds away from zero.
 */
function fixedLikePython(value: number, decimals: number): string {
  const rounded = value.toFixed(decimals);
  if (!Number.isFinite(value) || value < 0) { return rounded; }
  // toFixed(100) is the exact decimal expansion of a double in this range.
  const exact = value.toFixed(100);
  const dot = exact.indexOf(".");
  const tail = exact.slice(dot + 1 + decimals);
  if (!/^50*$/.test(tail)) { return rounded; }
  const truncated = decimals === 0 ? exact.slice(0, dot) : exact.slice(0, dot + 1 + decimals);
  const lastDigit = Number(truncated.charAt(truncated.length - 1));
  return lastDigit % 2 === 0 ? truncated : rounded;
}

/**
 * A 0..1 fraction as a percentage. 100% is shown only for an exact 1.0; a
 * value below 1 that would round to 100 is capped at the largest value below
 * it at this precision (99.9% or 99.99%).
 */
export function percentLabel(fraction: number, decimals = 2): string {
  let text = `${fixedLikePython(fraction * 100, decimals)}%`;
  if (fraction < 1 && text === `${(100).toFixed(decimals)}%`) {
    text = `${(100 - 10 ** -decimals).toFixed(decimals)}%`;
  }
  return text;
}

/** Line (or word) match ratio, 0..1, with one decimal. */
export function lineMatchLabel(fraction: number): string {
  return percentLabel(fraction, LINE_MATCH_DECIMALS);
}

/** Jaccard or containment, 0..1, with two decimals. */
export function overlapLabel(fraction: number): string {
  return percentLabel(fraction, OVERLAP_DECIMALS);
}

/** File-name similarity, 0..100, as a percentage with one decimal. */
export function nameSimilarityLabel(score: number): string {
  return percentLabel(score / 100, LINE_MATCH_DECIMALS);
}

/** A threshold in percent (0..100): "93%" when whole, else "92.5%". */
export function thresholdLabel(percent: number | null | undefined): string {
  if (percent === null || percent === undefined || !Number.isFinite(percent)) { return "not set"; }
  if (Number.isInteger(percent)) { return `${percent}%`; }
  // Python's "{:g}" keeps 6 significant digits and drops trailing zeros.
  return `${Number(percent.toPrecision(6))}%`;
}

/** An integer count with thousands separators: 12,345 (independent of the locale). */
export function countLabel(n: number): string {
  const sign = n < 0 ? "-" : "";
  return sign + String(Math.trunc(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "1 file", "2 files"; the count uses thousands separators. */
export function plural(n: number, singular: string, pluralForm = `${singular}s`): string {
  return `${countLabel(n)} ${n === 1 ? singular : pluralForm}`;
}

/** Name of the per-pair match metric: "Line match", or "Word match" under --by-word. */
export function matchMetricName(comparisonUnit: string | null | undefined): string {
  return comparisonUnit === "word" ? "Word match" : "Line match";
}

/** Where the Jaccard threshold came from, in plain words (never the internal token). */
export function thresholdSourceLabel(provenance: string | null | undefined): string {
  switch (provenance) {
    case "user": return "Set by user";
    case "normalize-default": return "Default for normalized comparison";
    case "legacy-uncalibrated": return "Default (5%)";
    default: return "Not recorded";
  }
}

/**
 * Analysis state as the reports print it in the State row
 * (models.analysis_state_label): "Complete" or "Incomplete" for the JSON
 * "state" values "complete" and "incomplete", or "Unknown" when an older
 * report does not record it.
 */
export function analysisStateLabel(state: string | null | undefined): string {
  if (state === "complete") { return "Complete"; }
  if (state === "incomplete") { return "Incomplete"; }
  return "Unknown";
}

/** U+2212 MINUS SIGN, for deletion counts (pdf_gen.MINUS; a hyphen is not a minus). */
export const MINUS = "−";

/** A count of added lines or words: "+1,098". */
export function addedCountLabel(n: number): string {
  return `+${countLabel(n)}`;
}

/** A count of deleted lines or words with a true minus sign, U+2212 then "1,098". */
export function deletedCountLabel(n: number): string {
  return `${MINUS}${countLabel(n)}`;
}

/** Unit of the +/- counts: "words" under --by-word, else "lines". */
export function changeUnit(comparisonUnit: string | null | undefined): string {
  return comparisonUnit === "word" ? "words" : "lines";
}

/**
 * Sentences for the analyzer's incomplete-analysis reason codes, word for
 * word as pdf_gen.INCOMPLETE_REASON_TEXT (test/polish.test.js checks them).
 */
export const INCOMPLETE_REASON_TEXT: Readonly<Record<string, string>> = {
  "collection-file-skipped": "Some input files could not be read.",
  "collection-file-unhashed": "Some input files could not be hashed.",
  "diff-worker-failure": "A comparison process failed, so some file pairs were not compared.",
  "diff-pair-error": "Some file pairs were not compared because a file could not be read or decoded.",
  "diff-payload-truncated": "Some side-by-side diffs were over the size limit and are not included.",
  "deep-file-or-worker-failure": "Some files could not be processed by Deep Compare.",
  "deep-index-truncated":
    "The Deep Compare index reached the --max-index-entries limit, so some cross-matches are not reported.",
};

/** pdf_gen._UNKNOWN_REASON_TEXT: a code this version does not know. */
export const UNKNOWN_REASON_TEXT = "Another part of the analysis did not complete.";

/** One sentence per recorded reason, each stated once, in the order recorded. */
export function reasonSentences(codes: readonly string[]): string[] {
  const out: string[] = [];
  for (const code of codes) {
    const sentence = INCOMPLETE_REASON_TEXT[code] ?? UNKNOWN_REASON_TEXT;
    if (!out.includes(sentence)) { out.push(sentence); }
  }
  return out;
}
