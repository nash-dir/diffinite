/** Pure analysis configuration, report parsing, and view-model logic. */

export type ThresholdMode = "auto" | "manual";

export interface DiffiniteOptions {
  mode: "simple" | "deep";
  stripComments: boolean;
  byWord: boolean;
  normalizeWhitespace: boolean;
  normalize: boolean;
  collapseIdentical: boolean;
  detectMoved: boolean;
  noAutojunk: boolean;
  threshold: number;
  kGram: number;
  window: number;
  thresholdMode: ThresholdMode;
  thresholdDeep: number;
  pageNumber: boolean;
  fileNumber: boolean;
  batesNumber: boolean;
  hash: boolean;
  encoding: string;
  sortBy: string;
  sortOrder: string;
  batesPrefix: string;
  batesSuffix: string;
  batesStart: number;
  uncomparedFiles: "inline" | "separate" | "none";
  binaryHandling: "exclude" | "hash" | "error";
  metricsOnly?: boolean;
  filterJson?: string;
  /** Phase-2 file-A scope retained in memory so later exports reproduce it. */
  selectedFiles?: readonly string[];
  workers: number;
  noMerge: boolean;
  preserveTree: boolean;
  pdfFont: string;
  pdfLang: string;
  allowPartial: boolean;
}

export function defaultAnalysisOptions(): DiffiniteOptions {
  return {
    mode: "deep",
    stripComments: false,
    byWord: false,
    normalizeWhitespace: false,
    normalize: false,
    collapseIdentical: false,
    detectMoved: false,
    noAutojunk: true,
    threshold: 60,
    kGram: 5,
    window: 4,
    thresholdMode: "auto",
    // Retained only as the editable manual value. Auto mode never sends it.
    thresholdDeep: 5,
    pageNumber: true,
    fileNumber: true,
    batesNumber: true,
    hash: true,
    encoding: "auto",
    sortBy: "",
    sortOrder: "asc",
    batesPrefix: "",
    batesSuffix: "",
    batesStart: 1,
    uncomparedFiles: "inline",
    binaryHandling: "hash",
    workers: 4,
    noMerge: false,
    preserveTree: true,
    pdfFont: "",
    pdfLang: "ko",
    allowPartial: false,
  };
}

export function migratePersistedOptions(
  persisted?: Partial<DiffiniteOptions> & { thresholdMode?: unknown }
): { options: DiffiniteOptions; warnings: string[] } {
  const warnings: string[] = [];
  const options = { ...defaultAnalysisOptions(), ...(persisted || {}) } as DiffiniteOptions;
  if (persisted && persisted.thresholdMode !== "auto" && persisted.thresholdMode !== "manual") {
    if (typeof persisted.thresholdDeep === "number") {
      // Old state cannot distinguish the former UI default from an intentional
      // user value. Preserve it as manual and require an explicit reset to Auto.
      options.thresholdMode = "manual";
      warnings.push(
        `Legacy thresholdDeep ${persisted.thresholdDeep} is ambiguous. ` +
        "It was preserved as a manual value; choose Auto to let Python select the channel default."
      );
    } else {
      options.thresholdMode = "auto";
    }
  }
  return { options, warnings };
}

export function buildCoreArgs(opts: DiffiniteOptions): string[] {
  const args: string[] = ["--mode", opts.mode];
  if (opts.stripComments) { args.push("--strip-comments"); }
  if (opts.byWord) { args.push("--by-word"); }
  if (opts.normalizeWhitespace) { args.push("--normalize-whitespace"); }
  if (opts.normalize) { args.push("--normalize"); }
  if (opts.collapseIdentical) { args.push("--collapse-identical"); }
  if (opts.detectMoved) { args.push("--detect-moved"); }
  if (opts.noAutojunk) { args.push("--no-autojunk"); }
  args.push("--threshold", String(opts.threshold));
  args.push("--k-gram", String(opts.kGram));
  args.push("--window", String(opts.window));
  if (opts.thresholdMode === "manual") {
    args.push("--threshold-deep", String(opts.thresholdDeep));
  }
  if (opts.pageNumber) { args.push("--page-number"); }
  if (opts.fileNumber) { args.push("--file-number"); }
  if (opts.batesNumber) { args.push("--bates-number"); }
  if (opts.hash) { args.push("--hash"); }
  if (opts.encoding && opts.encoding !== "auto") { args.push("--encoding", opts.encoding); }
  if (opts.sortBy) { args.push("--sort-by", opts.sortBy, "--sort-order", opts.sortOrder || "asc"); }
  if (opts.batesPrefix) { args.push("--bates-prefix", opts.batesPrefix); }
  if (opts.batesSuffix) { args.push("--bates-suffix", opts.batesSuffix); }
  if (opts.batesStart > 1) { args.push("--bates-start", String(opts.batesStart)); }
  if (opts.uncomparedFiles !== "inline") { args.push("--uncompared-files", opts.uncomparedFiles); }
  if (opts.binaryHandling !== "hash") { args.push("--binary-handling", opts.binaryHandling); }
  if (opts.metricsOnly) { args.push("--metrics-only"); }
  if (opts.filterJson) { args.push("--filter-json", opts.filterJson); }
  if (opts.workers > 1) { args.push("--workers", String(opts.workers)); }
  if (opts.noMerge) { args.push("--no-merge"); }
  if (opts.noMerge && !opts.preserveTree) { args.push("--no-preserve-tree"); }
  if (opts.allowPartial) { args.push("--allow-partial"); }
  if (opts.pdfFont) { args.push("--pdf-font", opts.pdfFont); }
  else if (opts.pdfLang) { args.push("--pdf-lang", opts.pdfLang); }
  return args;
}

type UnknownRecord = Record<string, unknown>;

export interface ReportMetadata {
  exec_mode: string;
  k: number | null;
  w: number | null;
  threshold: number | null;
  threshold_provenance: string;
  autojunk: boolean | null;
  normalize: boolean | null;
  lang_aware: boolean | null;
  deep_index_truncated: boolean | null;
  calibration_disclosure: string | null;
}

export interface ReportResult {
  file_a: string;
  file_b: string;
  name_similarity: number;
  ratio: number;
  additions: number;
  deletions: number;
  html_diff: string;
  error: string | null;
  binary: boolean;
  truncation: {
    truncated: boolean | null;
    reason: string | null;
    original_bytes: number | null;
    omitted_bytes: number | null;
  };
}

export interface DeepReportMatch {
  file_b: string;
  shared_hashes: number;
  jaccard: number;
  /** Directional containment (shared / unique hashes of A or B); null for reports that predate it. */
  containment_a_in_b: number | null;
  containment_b_in_a: number | null;
  inconclusive: boolean | null;
}

export interface AnalysisStatusReport {
  state: "complete" | "incomplete" | "unknown";
  reasons: string[];
  collection: { failed_file_count: number | null; failed_files: UnknownRecord[] };
  diff: { requested_pair_count: number | null; successful_pair_count: number | null; failed_pair_count: number | null; failed_pairs: UnknownRecord[] };
  deep: { requested_file_count: number | null; successful_file_count: number | null; failed_file_count: number | null; failed_files: UnknownRecord[] };
  truncation: { deep_index_truncated: boolean | null; diff_truncated_count: number | null };
}

export interface DiffiniteReport {
  schema_version: number;
  metadata: ReportMetadata;
  preprocessing: UnknownRecord;
  analysis_status: AnalysisStatusReport;
  dir_a: string;
  dir_b: string;
  comparison_unit: string;
  comment_mode: string;
  summary: { matched_pairs: number; unmatched_a_count: number; unmatched_b_count: number };
  results: ReportResult[];
  deep_results: Array<{ file_a: string; fingerprint_count_a: number; matches: DeepReportMatch[] }>;
  unmatched_a: string[];
  unmatched_b: string[];
}

function record(value: unknown): UnknownRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as UnknownRecord : {};
}
function text(value: unknown, fallback = ""): string { return typeof value === "string" ? value : fallback; }
function num(value: unknown, fallback: number | null = null): number | null { return typeof value === "number" && Number.isFinite(value) ? value : fallback; }
function bool(value: unknown): boolean | null { return typeof value === "boolean" ? value : null; }
function records(value: unknown): UnknownRecord[] { return Array.isArray(value) ? value.map(record) : []; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []; }

function liveReportError(path: string, expectation: string): never {
  throw new Error(`Invalid live report: ${path} ${expectation}.`);
}

function requireRecord(value: unknown, path: string): UnknownRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return liveReportError(path, "must be an object");
  }
  return value as UnknownRecord;
}

function requireString(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) {
    return liveReportError(path, `must be ${allowEmpty ? "a string" : "a non-empty string"}`);
  }
  return value;
}

function requireNullableString(value: unknown, path: string): void {
  if (value !== null && typeof value !== "string") {
    liveReportError(path, "must be a string or null");
  }
}

function requireFiniteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return liveReportError(path, "must be a finite number");
  }
  return value;
}

function requireNullableNumber(value: unknown, path: string): void {
  if (value !== null) { requireFiniteNumber(value, path); }
}

function requireCount(value: unknown, path: string): number {
  const valueAsNumber = requireFiniteNumber(value, path);
  if (!Number.isInteger(valueAsNumber) || valueAsNumber < 0) {
    return liveReportError(path, "must be a non-negative integer");
  }
  return valueAsNumber;
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    return liveReportError(path, "must be a boolean");
  }
  return value;
}

function requireArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) {
    return liveReportError(path, "must be an array");
  }
  return value;
}

function requireStringArray(value: unknown, path: string): string[] {
  const values = requireArray(value, path);
  values.forEach((item, index) => requireString(item, `${path}[${index}]`, true));
  return values as string[];
}

function validateLiveStatus(
  source: UnknownRecord,
  resultCount: number,
  actualDiffTruncatedCount: number,
  metadataDeepIndexTruncated: boolean,
): void {
  const status = requireRecord(source.analysis_status, "analysis_status");
  const state = requireString(status.state, "analysis_status.state");
  if (state !== "complete" && state !== "incomplete") {
    liveReportError("analysis_status.state", "must be 'complete' or 'incomplete'");
  }
  const reasons = requireStringArray(status.reasons, "analysis_status.reasons");
  const collection = requireRecord(status.collection, "analysis_status.collection");
  const collectionFailed = requireCount(
    collection.failed_file_count,
    "analysis_status.collection.failed_file_count",
  );
  const collectionFailedFiles = requireArray(
    collection.failed_files,
    "analysis_status.collection.failed_files",
  );
  collectionFailedFiles.forEach((item, index) => {
    requireRecord(item, `analysis_status.collection.failed_files[${index}]`);
  });
  if (collectionFailed !== collectionFailedFiles.length) {
    liveReportError(
      "analysis_status.collection.failed_file_count",
      "must equal analysis_status.collection.failed_files.length",
    );
  }

  const validateCounts = (
    value: unknown,
    path: "analysis_status.diff" | "analysis_status.deep",
    requestedKey: "requested_pair_count" | "requested_file_count",
    successfulKey: "successful_pair_count" | "successful_file_count",
    failedKey: "failed_pair_count" | "failed_file_count",
    detailsKey: "failed_pairs" | "failed_files",
  ): { requested: number; successful: number; failed: number } => {
    const counts = requireRecord(value, path);
    const requested = requireCount(counts[requestedKey], `${path}.${requestedKey}`);
    const successful = requireCount(counts[successfulKey], `${path}.${successfulKey}`);
    const failed = requireCount(counts[failedKey], `${path}.${failedKey}`);
    const details = requireArray(counts[detailsKey], `${path}.${detailsKey}`);
    details.forEach((item, index) => requireRecord(item, `${path}.${detailsKey}[${index}]`));
    if (failed !== details.length) {
      liveReportError(`${path}.${failedKey}`, `must equal ${path}.${detailsKey}.length`);
    }
    if (requested !== successful + failed) {
      liveReportError(`${path}.${requestedKey}`, `must equal successful plus failed counts`);
    }
    return { requested, successful, failed };
  };

  const diff = validateCounts(
    status.diff, "analysis_status.diff",
    "requested_pair_count", "successful_pair_count", "failed_pair_count", "failed_pairs",
  );
  const deep = validateCounts(
    status.deep, "analysis_status.deep",
    "requested_file_count", "successful_file_count", "failed_file_count", "failed_files",
  );
  if (diff.successful !== resultCount) {
    liveReportError("analysis_status.diff.successful_pair_count", "must equal results.length");
  }

  const truncation = requireRecord(status.truncation, "analysis_status.truncation");
  const deepIndexTruncated = requireBoolean(
    truncation.deep_index_truncated,
    "analysis_status.truncation.deep_index_truncated",
  );
  const diffTruncatedCount = requireCount(
    truncation.diff_truncated_count,
    "analysis_status.truncation.diff_truncated_count",
  );
  if (diffTruncatedCount !== actualDiffTruncatedCount) {
    liveReportError(
      "analysis_status.truncation.diff_truncated_count",
      "must equal the number of truncated results",
    );
  }
  if (deepIndexTruncated !== metadataDeepIndexTruncated) {
    liveReportError(
      "analysis_status.truncation.deep_index_truncated",
      "must match metadata.deep_index_truncated",
    );
  }

  const hasIncompleteEvidence = reasons.length > 0
    || collectionFailed > 0
    || diff.failed > 0
    || deep.failed > 0
    || deepIndexTruncated
    || diffTruncatedCount > 0;
  if (state === "complete" && hasIncompleteEvidence) {
    liveReportError("analysis_status.state", "cannot be complete when failures, truncation, or reasons are present");
  }
  if (state === "incomplete" && reasons.length === 0) {
    liveReportError("analysis_status.reasons", "must explain an incomplete state");
  }
}

/**
 * Validate reports created by the subprocess in this extension invocation.
 * Imported legacy reports continue to use parseReport(), whose fallbacks are
 * intentionally permissive. A live subprocess must never turn malformed JSON
 * into an apparently valid empty analysis.
 */
export function parseLiveReport(raw: unknown): DiffiniteReport {
  const source = requireRecord(raw, "live report");
  // Python diffinite <= 0.13.x wrote no schema_version. With a system Python
  // (diffinite.pythonPath / non-Windows builds) that is the likely cause, so say
  // how to fix it instead of reporting a malformed field.
  if (source.schema_version === undefined && typeof source.dir_a === "string") {
    liveReportError(
      "schema_version",
      "is missing: the diffinite Python package is older than 0.14.0. " +
        "Upgrade it (pip install -U diffinite) or use the bundled runtime",
    );
  }
  const schemaVersion = requireCount(source.schema_version, "schema_version");
  // The current Python JSON writer contract is schema v2 (pipeline.py).
  if (schemaVersion !== 2) {
    liveReportError("schema_version", "is unsupported; this extension requires schema version 2");
  }

  requireString(source.dir_a, "dir_a");
  requireString(source.dir_b, "dir_b");
  requireString(source.comparison_unit, "comparison_unit");
  requireString(source.comment_mode, "comment_mode");
  requireRecord(source.preprocessing, "preprocessing");

  const metadata = requireRecord(source.metadata, "metadata");
  requireString(metadata.exec_mode, "metadata.exec_mode");
  requireNullableNumber(metadata.k, "metadata.k");
  requireNullableNumber(metadata.w, "metadata.w");
  requireNullableNumber(metadata.threshold, "metadata.threshold");
  requireString(metadata.threshold_provenance, "metadata.threshold_provenance");
  requireBoolean(metadata.autojunk, "metadata.autojunk");
  requireBoolean(metadata.normalize, "metadata.normalize");
  requireBoolean(metadata.lang_aware, "metadata.lang_aware");
  requireBoolean(metadata.deep_index_truncated, "metadata.deep_index_truncated");
  requireNullableString(metadata.calibration_disclosure, "metadata.calibration_disclosure");

  const results = requireArray(source.results, "results");
  results.forEach((value, index) => {
    const resultPath = `results[${index}]`;
    const item = requireRecord(value, resultPath);
    requireString(item.file_a, `${resultPath}.file_a`);
    requireString(item.file_b, `${resultPath}.file_b`);
    requireFiniteNumber(item.name_similarity, `${resultPath}.name_similarity`);
    requireFiniteNumber(item.ratio, `${resultPath}.ratio`);
    requireCount(item.additions, `${resultPath}.additions`);
    requireCount(item.deletions, `${resultPath}.deletions`);
    requireString(item.html_diff, `${resultPath}.html_diff`, true);
    requireNullableString(item.error, `${resultPath}.error`);
    requireBoolean(item.binary, `${resultPath}.binary`);
    const truncation = requireRecord(item.truncation, `${resultPath}.truncation`);
    requireBoolean(truncation.truncated, `${resultPath}.truncation.truncated`);
    requireNullableString(truncation.reason, `${resultPath}.truncation.reason`);
    requireNullableNumber(truncation.original_bytes, `${resultPath}.truncation.original_bytes`);
    requireNullableNumber(truncation.omitted_bytes, `${resultPath}.truncation.omitted_bytes`);
  });

  const summary = requireRecord(source.summary, "summary");
  const matchedPairs = requireCount(summary.matched_pairs, "summary.matched_pairs");
  requireCount(summary.unmatched_a_count, "summary.unmatched_a_count");
  requireCount(summary.unmatched_b_count, "summary.unmatched_b_count");
  if (matchedPairs !== results.length) {
    liveReportError("summary.matched_pairs", "must equal results.length");
  }

  requireStringArray(source.unmatched_a, "unmatched_a");
  requireStringArray(source.unmatched_b, "unmatched_b");
  if (source.deep_results !== null) {
    requireArray(source.deep_results, "deep_results").forEach((value, index) => {
      const resultPath = `deep_results[${index}]`;
      const item = requireRecord(value, resultPath);
      requireString(item.file_a, `${resultPath}.file_a`);
      requireCount(item.fingerprint_count_a, `${resultPath}.fingerprint_count_a`);
      requireArray(item.matches, `${resultPath}.matches`).forEach((match, matchIndex) => {
        const matchPath = `${resultPath}.matches[${matchIndex}]`;
        const matchRecord = requireRecord(match, matchPath);
        requireString(matchRecord.file_b, `${matchPath}.file_b`);
        requireCount(matchRecord.shared_hashes, `${matchPath}.shared_hashes`);
        requireFiniteNumber(matchRecord.jaccard, `${matchPath}.jaccard`);
        requireBoolean(matchRecord.inconclusive, `${matchPath}.inconclusive`);
      });
    });
  }

  const actualDiffTruncatedCount = results.filter((value) => {
    const item = value as UnknownRecord;
    return (item.truncation as UnknownRecord).truncated === true;
  }).length;
  validateLiveStatus(
    source,
    results.length,
    actualDiffTruncatedCount,
    metadata.deep_index_truncated as boolean,
  );
  return parseReport(source);
}

export function parseReport(raw: unknown): DiffiniteReport {
  const source = record(raw);
  const meta = record(source.metadata);
  const summary = record(source.summary);
  const status = record(source.analysis_status);
  const collectionStatus = record(status.collection);
  const diffStatus = record(status.diff);
  const deepStatus = record(status.deep);
  const truncationStatus = record(status.truncation);
  const rawState = text(status.state, "unknown");
  const state: AnalysisStatusReport["state"] = rawState === "complete" || rawState === "incomplete" ? rawState : "unknown";

  const results = records(source.results).map((item): ReportResult => {
    const truncation = record(item.truncation);
    return {
      file_a: text(item.file_a, "unknown"), file_b: text(item.file_b, "unknown"),
      name_similarity: num(item.name_similarity, 0) || 0, ratio: num(item.ratio, 0) || 0,
      additions: num(item.additions, 0) || 0, deletions: num(item.deletions, 0) || 0,
      html_diff: text(item.html_diff), error: typeof item.error === "string" ? item.error : null,
      binary: bool(item.binary) || false,
      truncation: {
        truncated: bool(truncation.truncated), reason: typeof truncation.reason === "string" ? truncation.reason : null,
        original_bytes: num(truncation.original_bytes), omitted_bytes: num(truncation.omitted_bytes),
      },
    };
  });

  const deepResults = records(source.deep_results).map((item) => ({
    file_a: text(item.file_a, "unknown"),
    fingerprint_count_a: num(item.fingerprint_count_a, 0) || 0,
    matches: records(item.matches).map((match): DeepReportMatch => ({
      file_b: text(match.file_b, "unknown"), shared_hashes: num(match.shared_hashes, 0) || 0,
      jaccard: num(match.jaccard, 0) || 0, inconclusive: bool(match.inconclusive),
      containment_a_in_b: num(match.containment_a_in_b), containment_b_in_a: num(match.containment_b_in_a),
    })),
  }));

  return {
    schema_version: num(source.schema_version, 1) || 1,
    metadata: {
      exec_mode: text(meta.exec_mode, "unknown"), k: num(meta.k), w: num(meta.w), threshold: num(meta.threshold),
      threshold_provenance: text(meta.threshold_provenance, "unknown"), autojunk: bool(meta.autojunk),
      normalize: bool(meta.normalize), lang_aware: bool(meta.lang_aware),
      deep_index_truncated: bool(meta.deep_index_truncated),
      calibration_disclosure: typeof meta.calibration_disclosure === "string" ? meta.calibration_disclosure : null,
    },
    preprocessing: record(source.preprocessing),
    analysis_status: {
      state, reasons: strings(status.reasons),
      collection: {
        failed_file_count: num(collectionStatus.failed_file_count),
        failed_files: records(collectionStatus.failed_files),
      },
      diff: {
        requested_pair_count: num(diffStatus.requested_pair_count), successful_pair_count: num(diffStatus.successful_pair_count),
        failed_pair_count: num(diffStatus.failed_pair_count), failed_pairs: records(diffStatus.failed_pairs),
      },
      deep: {
        requested_file_count: num(deepStatus.requested_file_count), successful_file_count: num(deepStatus.successful_file_count),
        failed_file_count: num(deepStatus.failed_file_count), failed_files: records(deepStatus.failed_files),
      },
      truncation: {
        deep_index_truncated: bool(truncationStatus.deep_index_truncated),
        diff_truncated_count: num(truncationStatus.diff_truncated_count),
      },
    },
    dir_a: text(source.dir_a), dir_b: text(source.dir_b), comparison_unit: text(source.comparison_unit, "unknown"),
    comment_mode: text(source.comment_mode, "unknown"),
    summary: {
      matched_pairs: num(summary.matched_pairs, results.length) || 0,
      unmatched_a_count: num(summary.unmatched_a_count, 0) || 0,
      unmatched_b_count: num(summary.unmatched_b_count, 0) || 0,
    },
    results, deep_results: deepResults,
    unmatched_a: strings(source.unmatched_a), unmatched_b: strings(source.unmatched_b),
  };
}

export interface ReportBanner { kind: "warning" | "info"; title: string; message: string; }
export interface ReportViewModel {
  banners: ReportBanner[];
  deepRows: Array<DeepReportMatch & { file_a: string; kind: "candidate" | "inconclusive" | "unknown"; label: string }>;
}

export function buildReportViewModel(report: DiffiniteReport): ReportViewModel {
  const banners: ReportBanner[] = [];
  const meta = report.metadata;
  if (report.analysis_status.state === "unknown") {
    banners.push({
      kind: "warning",
      title: "Analysis completeness unknown",
      message: "분석 완전성 정보가 없습니다. 이 결과를 완전한 분석으로 해석하지 마십시오.",
    });
  }
  const incomplete = report.analysis_status.state === "incomplete"
    || meta.deep_index_truncated === true
    || report.results.some((result) => result.truncation.truncated === true);
  if (incomplete) {
    const reasons = report.analysis_status.reasons.length ? report.analysis_status.reasons.join(", ") : "reported output is truncated or partial";
    const details: string[] = [];
    const collectionStatus = report.analysis_status.collection;
    const diffStatus = report.analysis_status.diff;
    const deepStatus = report.analysis_status.deep;
    if (diffStatus.successful_pair_count !== null && diffStatus.requested_pair_count !== null) {
      details.push(`Diff ${diffStatus.successful_pair_count}/${diffStatus.requested_pair_count} processed (${diffStatus.failed_pair_count ?? "unknown"} failed)`);
    }
    if (deepStatus.successful_file_count !== null && deepStatus.requested_file_count !== null) {
      details.push(`Deep ${deepStatus.successful_file_count}/${deepStatus.requested_file_count} processed (${deepStatus.failed_file_count ?? "unknown"} failed)`);
    }
    for (const failed of collectionStatus.failed_files) {
      details.push(`Input skipped ${text(failed.side, "?")}:${text(failed.path, "?")} (${text(failed.reason, "unknown")})`);
    }
    for (const failed of diffStatus.failed_pairs) {
      details.push(`Failed pair ${text(failed.file_a, "?")} ↔ ${text(failed.file_b, "?")} (${text(failed.reason, "unknown")})`);
    }
    for (const failed of deepStatus.failed_files) {
      details.push(`Failed file ${text(failed.side, "?")}:${text(failed.path, "?")} (${text(failed.reason, "unknown")})`);
    }
    const detailText = details.length ? ` ${details.join("; ")}.` : "";
    banners.push({ kind: "warning", title: "Incomplete analysis", message: `불완전 결과: ${reasons}.${detailText} 완전한 분석으로 해석하지 마십시오.` });
  }
  for (const result of report.results) {
    if (result.truncation.truncated === true) {
      const omitted = result.truncation.omitted_bytes === null
        ? "omitted byte count unknown"
        : `${result.truncation.omitted_bytes} bytes omitted`;
      banners.push({
        kind: "warning",
        title: "Truncated diff",
        message: `${result.file_a} ↔ ${result.file_b}: ${result.truncation.reason ?? "unknown reason"}; ${omitted}.`,
      });
    }
  }
  if (meta.threshold_provenance === "unknown" || meta.threshold === null) {
    banners.push({ kind: "warning", title: "Metadata unavailable", message: "Legacy JSON omits effective threshold provenance; treat it as unknown." });
  } else if (meta.threshold_provenance === "user") {
    banners.push({ kind: "warning", title: "Manual threshold", message: `User threshold ${meta.threshold} was applied. Python's disclosure below states whether calibration applies.` });
  } else if (meta.threshold_provenance === "legacy-uncalibrated") {
    banners.push({ kind: "warning", title: "Uncalibrated legacy threshold", message: "The historical raw default is a manual-review filter, not a calibrated safety value." });
  }
  if (meta.calibration_disclosure) {
    banners.push({ kind: meta.normalize ? "warning" : "info", title: "Threshold disclosure", message: meta.calibration_disclosure });
  }

  const deepRows = report.deep_results.flatMap((result) => result.matches.map((match) => ({
    ...match,
    file_a: result.file_a,
    kind: match.inconclusive === true ? "inconclusive" as const : match.inconclusive === false ? "candidate" as const : "unknown" as const,
    label: match.inconclusive === true ? "판단 유보" : match.inconclusive === false ? "유사 후보" : "상태 미상",
  })));
  return { banners, deepRows };
}
