/**
 * Review summary — counts and settings shown at the top of the Tree Viewer.
 *
 * Every value is read directly from the analyzer's JSON report. Nothing is
 * inferred or scored here: when the report does not carry a value, the
 * summary says "unknown" instead of guessing.
 */
import { DiffiniteReport, buildReportViewModel } from "./analysisModel";
import { analysisStateLabel, countLabel, thresholdLabel, thresholdSourceLabel } from "./labels";
import { STATUS_LABELS } from "./notices";

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
  return value === null ? "unknown" : countLabel(value);
}

function sensitiveFilesLabel(mode: string, excluded: number): string {
  if (mode === "exclude") { return `Excluded (${countLabel(excluded)} found)`; }
  if (mode === "include") { return "Included (compared like any other file)"; }
  if (mode === "error") { return "Stop the run when found (none found)"; }
  return "unknown";
}

export function buildReviewSummary(report: DiffiniteReport): ReviewSummary {
  const meta = report.metadata;
  const status = report.analysis_status;
  const errorPairs = report.results.filter((r) => r.error !== null).length;
  const binaryPairs = report.results.filter((r) => r.binary).length;
  const skipped = status.collection.failed_file_count;

  const stateText = analysisStateLabel(status.state);

  // Pairs the matcher produced (same relative path, else name similarity above
  // the filename threshold). Pairs dropped by --binary-handling exclude are
  // counted as requested but have no result row. Current reports state the
  // number; older ones (no excluded_pair_count) counted them as successful,
  // so it is derived there from the rows that are missing.
  const requested = status.diff.requested_pair_count;
  const failed = status.diff.failed_pair_count;
  const excluded = status.diff.excluded_pair_count !== null
    ? status.diff.excluded_pair_count
    : requested !== null && failed !== null
      ? requested - failed - report.results.length : null;

  // The reports' "File pairs failed" row counts the failed pairs recorded in
  // the status, which include every pair shown with an error (older reports
  // without that count fall back to the error rows).
  const failedPairs = Math.max(failed ?? 0, errorPairs);

  const facts: SummaryFact[] = [
    { label: STATUS_LABELS.state, value: stateText, attention: status.state !== "complete" },
    { label: "Matched pairs (same path or similar name)", value: countLabel(requested ?? report.summary.matched_pairs), attention: false },
    { label: "Files only in A (no match)", value: countLabel(report.summary.unmatched_a_count), attention: false },
    { label: "Files only in B (no match)", value: countLabel(report.summary.unmatched_b_count), attention: false },
    { label: STATUS_LABELS.pairsFailed, value: countLabel(failedPairs), attention: failedPairs > 0 },
    { label: STATUS_LABELS.inputsNotRead, value: count(skipped), attention: skipped === null || skipped > 0 },
    { label: "Hash-only pairs (binary or over the size limit; no line diff)", value: countLabel(binaryPairs), attention: binaryPairs > 0 },
  ];
  if (excluded !== null && excluded > 0) {
    facts.push({ label: STATUS_LABELS.pairsExcluded, value: countLabel(excluded), attention: true });
  }
  // A selective run lists only the selected A files among the unmatched and
  // omits the B list; the report states how many it left out.
  const omittedA = status.selection.omitted_unmatched_a_count;
  const omittedB = status.selection.omitted_unmatched_b_count;
  if ((omittedA ?? 0) > 0 || (omittedB ?? 0) > 0) {
    facts.push({
      label: STATUS_LABELS.selectionOmitted,
      value: `${count(omittedA)} in A; ${count(omittedB)} in B`,
      attention: true,
    });
  }
  // Inputs the collection policy left out are not compared; the reports list
  // each one with its rule, so the count is always stated here.
  const excludedInputs = status.exclusion.excluded_count;
  facts.push({
    label: STATUS_LABELS.inputsExcluded,
    value: count(excludedInputs),
    attention: excludedInputs === null || excludedInputs > 0,
  });
  const rules = meta.ignore_patterns.length;
  facts.push({
    label: "Exclusion list rules applied (~/.diffignore)",
    value: meta.ignore_file_sha256 === null ? "none" : countLabel(rules),
    attention: rules > 0,
  });
  const sensitiveExcluded = status.exclusion.excluded.filter((e) => e.source === "sensitive-preset").length;
  facts.push({
    label: "Sensitive files (.env, private keys, credential files)",
    value: sensitiveFilesLabel(meta.sensitive_files, sensitiveExcluded),
    attention: false,
  });

  if (meta.exec_mode === "deep") {
    const rows = buildReportViewModel(report).deepRows;
    const skippedBinary = status.deep.skipped_binary_file_count;
    const belowKgram = status.deep.unfingerprinted_file_count;
    facts.push(
      { label: STATUS_LABELS.deepReported, value: countLabel(rows.length), attention: false },
      { label: "Deep Compare pairs marked inconclusive", value: countLabel(rows.filter((r) => r.kind === "inconclusive").length), attention: false },
      { label: STATUS_LABELS.deepSkipped, value: count(skippedBinary), attention: skippedBinary === null || skippedBinary > 0 },
      { label: STATUS_LABELS.deepBelowKgram, value: count(belowKgram), attention: belowKgram === null || belowKgram > 0 },
    );
  } else {
    facts.push({ label: "Deep Compare (cross-file)", value: meta.exec_mode === "simple" ? "Not run (Simple mode)" : "unknown", attention: false });
  }

  const onOff = (v: boolean | null) => (v === null ? "unknown" : v ? "on" : "off");
  const settings: string[] = [
    `Mode: ${meta.exec_mode}`,
    `Comparison unit: ${report.comparison_unit}; comments: ${report.comment_mode}`,
    `Line diff autojunk: ${onOff(meta.autojunk)}`,
  ];
  if (meta.exec_mode === "deep") {
    settings.push(
      `K-gram size (K): ${count(meta.k)}; window size (W): ${count(meta.w)}; identifier normalization: ${onOff(meta.normalize)}`,
      `Jaccard threshold: ${meta.threshold === null ? "unknown" : thresholdLabel(meta.threshold)}`,
      `Threshold source: ${thresholdSourceLabel(meta.threshold_provenance)}`,
    );
  }
  if (meta.ignore_file_sha256 !== null) {
    settings.push(
      `Exclusion list SHA-256: ${meta.ignore_file_sha256}`,
      `Exclusion rules: ${meta.ignore_patterns.length ? meta.ignore_patterns.join("; ") : "none active"}`,
    );
  }
  if (meta.include_patterns.length) {
    settings.push(`Include filter: ${meta.include_patterns.join("; ")}`);
  }
  if (report.dir_a || report.dir_b) {
    settings.push(`Directory A: ${report.dir_a}`, `Directory B: ${report.dir_b}`);
  }

  return { facts, settings, errorPairs, binaryPairs };
}
