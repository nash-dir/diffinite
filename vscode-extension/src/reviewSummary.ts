/**
 * Review summary — counts and settings shown at the top of the Tree Viewer.
 *
 * Every value is read directly from the analyzer's JSON report. Nothing is
 * inferred or scored here: when the report does not carry a value, the
 * summary says "unknown" instead of guessing.
 */
import { DiffiniteReport, buildReportViewModel } from "./analysisModel";

export interface SummaryFact {
  label: string;
  value: string;
  /** True when the value means part of the input was not fully analysed. */
  attention: boolean;
}

export interface ReviewSummary {
  facts: SummaryFact[];
  settings: string[];
  errorPairs: number;
  binaryPairs: number;
}

function count(value: number | null): string {
  return value === null ? "unknown" : String(value);
}

export function buildReviewSummary(report: DiffiniteReport): ReviewSummary {
  const meta = report.metadata;
  const status = report.analysis_status;
  const errorPairs = report.results.filter((r) => r.error !== null).length;
  const binaryPairs = report.results.filter((r) => r.binary).length;
  const skipped = status.collection.failed_file_count;

  const stateText = status.state === "complete" ? "Complete"
    : status.state === "incomplete" ? "Incomplete" : "Unknown";

  // Pairs the matcher produced (same relative path, else name similarity above
  // the filename threshold). Pairs dropped by --binary-handling exclude are
  // counted as requested but have no result row.
  const requested = status.diff.requested_pair_count;
  const failed = status.diff.failed_pair_count;
  const excluded = requested !== null && failed !== null
    ? requested - failed - report.results.length : null;

  const facts: SummaryFact[] = [
    { label: "Analysis state", value: stateText, attention: status.state !== "complete" },
    { label: "Matched pairs (same path or similar name)", value: String(requested ?? report.summary.matched_pairs), attention: false },
    { label: "Files only in A (no match)", value: String(report.summary.unmatched_a_count), attention: false },
    { label: "Files only in B (no match)", value: String(report.summary.unmatched_b_count), attention: false },
    { label: "Pairs with errors", value: String(errorPairs), attention: errorPairs > 0 },
    { label: "Inputs skipped while collecting", value: count(skipped), attention: skipped === null || skipped > 0 },
    { label: "Hash-only pairs (binary or over the size limit; no line diff)", value: String(binaryPairs), attention: binaryPairs > 0 },
  ];
  if (excluded !== null && excluded > 0) {
    facts.push({ label: "Matched pairs left out by the binary-file policy", value: String(excluded), attention: true });
  }

  if (meta.exec_mode === "deep") {
    const rows = buildReportViewModel(report).deepRows;
    facts.push(
      { label: "Deep Compare similarity candidates", value: String(rows.filter((r) => r.kind === "candidate").length), attention: false },
      { label: "Deep Compare inconclusive (판단 유보)", value: String(rows.filter((r) => r.kind === "inconclusive").length), attention: false },
    );
  } else {
    facts.push({ label: "Deep Compare (cross-file)", value: meta.exec_mode === "simple" ? "Not run (Simple mode)" : "unknown", attention: false });
  }

  const onOff = (v: boolean | null) => (v === null ? "unknown" : v ? "on" : "off");
  const settings: string[] = [
    `Mode: ${meta.exec_mode}`,
    `Comparison unit: ${report.comparison_unit}; comments: ${report.comment_mode}`,
    `Line-diff autojunk heuristic: ${onOff(meta.autojunk)}`,
  ];
  if (meta.exec_mode === "deep") {
    settings.push(
      `Fingerprint K=${count(meta.k)}, W=${count(meta.w)}; identifier normalization: ${onOff(meta.normalize)}`,
      `Candidate threshold (Jaccard): ${meta.threshold === null ? "unknown" : `${meta.threshold.toFixed(1)}%`} ` +
        `(source: ${meta.threshold_provenance})`,
    );
  }
  if (report.dir_a || report.dir_b) {
    settings.push(`A: ${report.dir_a}`, `B: ${report.dir_b}`);
  }

  return { facts, settings, errorPairs, binaryPairs };
}
