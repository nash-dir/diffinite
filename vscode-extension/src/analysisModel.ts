/** Pure analysis configuration, report parsing, and view-model logic. */
import {
  countLabel, lineMatchLabel, plural, reasonSentences, thresholdLabel, thresholdSourceLabel,
} from "./labels";

export type ThresholdMode = "auto" | "manual";

/**
 * The exclusion list (~/.diffignore) as read once when an analysis starts.
 * Phase 2 and every export reuse these exact bytes, so editing the file
 * after Phase 1 cannot change what the reviewed analysis covers.
 */
export interface IgnoreSnapshot {
  /** Where the bytes were read from (shown to the user; never sent to Python). */
  sourcePath: string;
  /** Lower-case hex SHA-256 of the bytes; Python records the same value. */
  sha256: string;
  base64: string;
  /** Non-empty, non-comment lines: the rules Python will apply. */
  ruleCount: number;
}

/** Input file SHA-256 values from a run's manifest.sha256.json, by relative path. */
export interface InputManifest {
  a: Record<string, string>;
  b: Record<string, string>;
}

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
  /** --sensitive-files: .env, private keys and credential files. */
  sensitiveFiles: SensitiveFilesMode;
  /** --include patterns, comma separated; empty collects every file. */
  includePatterns: string;
  metricsOnly?: boolean;
  filterJson?: string;
  /** Phase-2 file-A scope retained in memory so later exports reproduce it. */
  selectedFiles?: readonly string[];
  /**
   * Runtime only. undefined: read ~/.diffignore now. null: the analysis ran
   * with no exclusion list. Otherwise the frozen Phase-1 exclusion list.
   */
  ignoreSnapshot?: IgnoreSnapshot | null;
  /** Runtime only: inputs of the analysis shown in the Results panel. */
  reviewedInputs?: InputManifest | null;
  workers: number;
  noMerge: boolean;
  preserveTree: boolean;
  pdfFont: string;
  pdfLang: string;
  allowPartial: boolean;
}

export type SensitiveFilesMode = "exclude" | "include" | "error";

/** The --include patterns in an options string ("*.java, src/**"), in order. */
export function parseIncludePatterns(value: string | undefined): string[] {
  return (value || "").split(",").map((p) => p.trim()).filter((p) => p.length > 0);
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
    sensitiveFiles: "exclude",
    includePatterns: "",
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
        "It was preserved as a manual value; choose Default to let the analyzer apply its default."
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
  // "--flag=value" form: argparse would read a value such as "-CONFIDENTIAL"
  // (the suffix example shown in the Options panel) as an unknown option.
  if (opts.batesPrefix) { args.push(`--bates-prefix=${opts.batesPrefix}`); }
  if (opts.batesSuffix) { args.push(`--bates-suffix=${opts.batesSuffix}`); }
  if (opts.batesStart > 1) { args.push("--bates-start", String(opts.batesStart)); }
  if (opts.uncomparedFiles !== "inline") { args.push("--uncompared-files", opts.uncomparedFiles); }
  if (opts.binaryHandling !== "hash") { args.push("--binary-handling", opts.binaryHandling); }
  // Always explicit, so the report and the command line show the choice.
  args.push("--sensitive-files", opts.sensitiveFiles || "exclude");
  // "--include=PATTERN": a pattern starting with "-" must not read as an option.
  for (const pattern of parseIncludePatterns(opts.includePatterns)) { args.push(`--include=${pattern}`); }
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

/**
 * Reject numeric options the CLI would not accept, or that the webview sent
 * empty (Number("") is 0, a valid but extreme threshold). The ranges are the
 * ones cli.py enforces (k-gram, window, workers, bates start >= 1; thresholds
 * 0..100). Returns an error message, or null when the options are usable.
 */
export function validateRunOptions(
  opts: Partial<DiffiniteOptions>,
  platform: string = process.platform,
): string | null {
  const checks: Array<[string, unknown, number, number, boolean]> = [
    // [label, value, min, max, integer]
    ["File name matching threshold", opts.threshold, 0, 100, false],
    ["K-gram size", opts.kGram, 1, Number.MAX_SAFE_INTEGER, true],
    ["Window size", opts.window, 1, Number.MAX_SAFE_INTEGER, true],
    // cli.py _MAX_WINDOWS_WORKERS: CPython's process pool supports at most 61 workers on Windows.
    ["Workers", opts.workers, 1, platform === "win32" ? MAX_WINDOWS_WORKERS : Number.MAX_SAFE_INTEGER, true],
    ["Bates starting number", opts.batesStart, 1, Number.MAX_SAFE_INTEGER, true],
  ];
  if (opts.thresholdMode === "manual") {
    checks.push(["Manual Jaccard threshold", opts.thresholdDeep, 0, 100, false]);
  }
  for (const [label, value, min, max, integer] of checks) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return `${label} is empty or not a number.`;
    }
    if (value < min || value > max || (integer && !Number.isInteger(value))) {
      const range = max === Number.MAX_SAFE_INTEGER ? `at least ${min}` : `between ${min} and ${max}`;
      return `${label} must be ${integer ? "a whole number " : ""}${range}.`;
    }
  }
  const bates = batesLabelError(`${opts.batesPrefix ?? ""}${opts.batesSuffix ?? ""}`);
  if (bates) { return bates; }
  if (opts.sensitiveFiles !== undefined && !["exclude", "include", "error"].includes(opts.sensitiveFiles)) {
    return "Sensitive files must be Exclude, Include or Stop.";
  }
  return null;
}

/** cli.py _MAX_WINDOWS_WORKERS (CPython concurrent.futures.process._MAX_WINDOWS_WORKERS = 63 - 2). */
export const MAX_WINDOWS_WORKERS = 61;

/**
 * Why a Bates prefix + suffix cannot be stamped, or null when it can. Same
 * rule as pdf_gen.bates_font_for, which makes the CLI refuse the run: the
 * stamp fonts draw only Windows-1252 (Helvetica, WinAnsi) or Hangul
 * (HYGothic-Medium, with ASCII only). Self-contained on purpose: the Options
 * webview embeds this function's source.
 */
export function batesLabelError(text: string): string | null {
  // The 27 characters cp1252 maps into 0x80-0x9F (WHATWG/Unicode cp1252 table;
  // 0x81, 0x8D, 0x8F, 0x90 and 0x9D are unassigned).
  const cp1252High = "\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\u017d" +
    "\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178";
  const hex = (ch: string): string => "U+" + (ch.codePointAt(0) || 0).toString(16).toUpperCase().padStart(4, "0");
  let hangul = false;
  let nonAsciiLatin: string | null = null;
  for (const ch of text) {
    const code = ch.codePointAt(0) || 0;
    // C0 controls and DEL print as nothing, so the stamp would differ from the index.
    if (code < 0x20 || code === 0x7F || (code >= 0x80 && code < 0xA0 && !cp1252High.includes(ch))) {
      return `Bates prefix/suffix contains a control character (${hex(ch)}).`;
    }
    if (code < 0x80) { continue; }
    if ((code >= 0xA0 && code <= 0xFF) || cp1252High.includes(ch)) {
      if (nonAsciiLatin === null) { nonAsciiLatin = ch; }
      continue;
    }
    // U+AC00-D7A3 Hangul Syllables, U+3131-318E Hangul Compatibility Jamo (pdf_gen._is_bates_hangul).
    if ((code >= 0xAC00 && code <= 0xD7A3) || (code >= 0x3131 && code <= 0x318E)) {
      hangul = true;
      continue;
    }
    return `Bates prefix/suffix character "${ch}" (${hex(ch)}) cannot be drawn by the Bates stamp fonts; ` +
      "use Latin (Windows-1252) characters or Hangul.";
  }
  if (hangul && nonAsciiLatin !== null) {
    return `Bates prefix/suffix character "${nonAsciiLatin}" (${hex(nonAsciiLatin)}) cannot be drawn together ` +
      "with Hangul; a label with Hangul may use only ASCII Latin characters.";
  }
  return null;
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
  /** Exclusion rules Python applied (from --ignore-file); [] when none. */
  ignore_patterns: string[];
  /** SHA-256 of the exclusion list file Python read; null when none was passed. */
  ignore_file_sha256: string | null;
  /** --sensitive-files policy: "exclude", "include", "error"; "unknown" in older reports. */
  sensitive_files: string;
  /** --include patterns; [] when every file was collected. */
  include_patterns: string[];
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
  /**
   * How the pair was compared: "difflib", "sha256-only" or "not-compared"
   * (pipeline.py). null in reports written before the field existed.
   */
  comparison_method: string | null;
  /** Python's text for a pair difflib did not compare (hash_only_label); null otherwise. */
  comparison_note: string | null;
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
  diff: {
    requested_pair_count: number | null; successful_pair_count: number | null; failed_pair_count: number | null; failed_pairs: UnknownRecord[];
    /** Failed pairs that still have a "not compared" result row; null in older reports. */
    error_pair_count: number | null;
    /** Matched pairs left out by --binary-handling exclude; null in older reports (which counted them as successful). */
    excluded_pair_count: number | null; excluded_pairs: UnknownRecord[];
  };
  deep: {
    requested_file_count: number | null; successful_file_count: number | null; failed_file_count: number | null; failed_files: UnknownRecord[];
    /** Inputs Deep Compare did not fingerprint because their content is binary (0 in older reports). */
    skipped_binary_file_count: number | null; skipped_binary_files: UnknownRecord[];
    /** Files read but too short for one k-gram (no fingerprints); null in older reports. */
    unfingerprinted_file_count: number | null; unfingerprinted_files: UnknownRecord[];
    /** --lang-aware files whose lexer failed and that used the registry-keyword tier. */
    lang_aware_fallback_files: UnknownRecord[];
    /** Pairs at or above the Jaccard threshold: null when Deep Compare did not run, 0 when it found none. */
    reported_pair_count: number | null;
  };
  /** Inputs the collection policy left out (ignore file, --include, sensitive files); null in older reports. */
  exclusion: { excluded_count: number | null; excluded: UnknownRecord[] };
  /** Unmatched files a selective (--filter-json) run left out of its lists; null in older reports. */
  selection: { omitted_unmatched_a_count: number | null; omitted_unmatched_b_count: number | null };
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
  errorResultCount: number,
  actualDiffTruncatedCount: number,
  metadataDeepIndexTruncated: boolean,
  binaryHandling: string,
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
  ): { requested: number; successful: number; failed: number; skipped: number; excluded: number | null; errorPairs: number | null } => {
    const counts = requireRecord(value, path);
    const requested = requireCount(counts[requestedKey], `${path}.${requestedKey}`);
    const successful = requireCount(counts[successfulKey], `${path}.${successfulKey}`);
    const failed = requireCount(counts[failedKey], `${path}.${failedKey}`);
    const details = requireArray(counts[detailsKey], `${path}.${detailsKey}`);
    details.forEach((item, index) => requireRecord(item, `${path}.${detailsKey}[${index}]`));
    if (failed !== details.length) {
      liveReportError(`${path}.${failedKey}`, `must equal ${path}.${detailsKey}.length`);
    }
    // deep_compare.py counts binary inputs it did not fingerprint in a third
    // bucket: successful = requested - failed - skipped_binary. Older v2
    // writers omit the fields, which means none were skipped.
    let skipped = 0;
    if (path === "analysis_status.deep" && counts.skipped_binary_file_count !== undefined) {
      skipped = requireCount(counts.skipped_binary_file_count, `${path}.skipped_binary_file_count`);
      const skippedFiles = requireArray(counts.skipped_binary_files, `${path}.skipped_binary_files`);
      skippedFiles.forEach((item, index) => requireRecord(item, `${path}.skipped_binary_files[${index}]`));
      if (skipped !== skippedFiles.length) {
        liveReportError(`${path}.skipped_binary_file_count`, `must equal ${path}.skipped_binary_files.length`);
      }
    }
    // Optional list fields shown in the review: when present they must be lists of records,
    // so a malformed value is rejected instead of being shown as "none".
    if (path === "analysis_status.deep") {
      for (const key of ["unfingerprinted_files", "lang_aware_fallback_files"] as const) {
        if (counts[key] !== undefined) {
          requireArray(counts[key], `${path}.${key}`)
            .forEach((item, index) => requireRecord(item, `${path}.${key}[${index}]`));
        }
      }
    }
    // pipeline.py lists matched pairs left out by --binary-handling exclude
    // in a third bucket: requested = successful + failed + excluded. Writers
    // before that field counted them as successful (no result row).
    let excluded: number | null = null;
    if (path === "analysis_status.diff" && counts.excluded_pair_count !== undefined) {
      excluded = requireCount(counts.excluded_pair_count, `${path}.excluded_pair_count`);
      const excludedPairs = requireArray(counts.excluded_pairs, `${path}.excluded_pairs`);
      excludedPairs.forEach((item, index) => requireRecord(item, `${path}.excluded_pairs[${index}]`));
      if (excluded !== excludedPairs.length) {
        liveReportError(`${path}.excluded_pair_count`, `must equal ${path}.excluded_pairs.length`);
      }
    }
    if (path === "analysis_status.deep" && counts.unfingerprinted_file_count !== undefined) {
      const below = requireCount(counts.unfingerprinted_file_count, `${path}.unfingerprinted_file_count`);
      const belowFiles = requireArray(counts.unfingerprinted_files, `${path}.unfingerprinted_files`);
      belowFiles.forEach((item, index) => requireRecord(item, `${path}.unfingerprinted_files[${index}]`));
      if (below !== belowFiles.length) {
        liveReportError(`${path}.unfingerprinted_file_count`, `must equal ${path}.unfingerprinted_files.length`);
      }
    }
    if (requested !== successful + failed + skipped + (excluded ?? 0)) {
      liveReportError(
        `${path}.${requestedKey}`,
        path === "analysis_status.deep"
          ? "must equal successful plus failed plus skipped-binary counts"
          : excluded !== null
            ? "must equal successful plus failed plus excluded counts"
            : "must equal successful plus failed counts",
      );
    }
    let errorPairs: number | null = null;
    if (path === "analysis_status.diff" && counts.error_pair_count !== undefined) {
      errorPairs = requireCount(counts.error_pair_count, `${path}.error_pair_count`);
      if (errorPairs > failed) {
        liveReportError(`${path}.error_pair_count`, `must not exceed ${path}.${failedKey}`);
      }
    }
    return { requested, successful, failed, skipped, excluded, errorPairs };
  };

  const diff = validateCounts(
    status.diff, "analysis_status.diff",
    "requested_pair_count", "successful_pair_count", "failed_pair_count", "failed_pairs",
  );
  const deep = validateCounts(
    status.deep, "analysis_status.deep",
    "requested_file_count", "successful_file_count", "failed_file_count", "failed_files",
  );
  if (diff.errorPairs !== null) {
    // Current writers: every successful pair and every pair that failed with
    // an error has a result row (the latter shows "not compared"); excluded
    // pairs have none. This holds for every --binary-handling mode.
    if (resultCount !== diff.successful + diff.errorPairs) {
      liveReportError(
        "analysis_status.diff.successful_pair_count",
        "plus error_pair_count must equal results.length",
      );
    }
    if (diff.errorPairs !== errorResultCount) {
      liveReportError("analysis_status.diff.error_pair_count", "must equal the number of results with an error");
    }
  } else if (binaryHandling === "exclude" && diff.excluded === null) {
    // Older writers counted a pair dropped by --binary-handling exclude as
    // processed successfully but wrote no result row for it.
    if (resultCount > diff.successful) {
      liveReportError("analysis_status.diff.successful_pair_count", "must be at least results.length");
    }
  } else if (diff.successful !== resultCount) {
    liveReportError("analysis_status.diff.successful_pair_count", "must equal results.length");
  }
  if (status.selection !== undefined) {
    const selection = requireRecord(status.selection, "analysis_status.selection");
    requireCount(selection.omitted_unmatched_a_count, "analysis_status.selection.omitted_unmatched_a_count");
    requireCount(selection.omitted_unmatched_b_count, "analysis_status.selection.omitted_unmatched_b_count");
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
  if (metadata.ignore_file_sha256 !== undefined) {
    requireNullableString(metadata.ignore_file_sha256, "metadata.ignore_file_sha256");
  }
  if (metadata.ignore_patterns !== undefined) {
    requireStringArray(metadata.ignore_patterns, "metadata.ignore_patterns");
  }
  if (metadata.sensitive_files !== undefined) {
    requireString(metadata.sensitive_files, "metadata.sensitive_files");
  }
  if (metadata.include_patterns !== undefined) {
    requireStringArray(metadata.include_patterns, "metadata.include_patterns");
  }
  // Absent in reports written before the exclusion list existed; when present
  // it must be well formed and its count must match its list.
  const statusForExclusion = requireRecord(source.analysis_status, "analysis_status");
  if (statusForExclusion.exclusion !== undefined) {
    const exclusion = requireRecord(statusForExclusion.exclusion, "analysis_status.exclusion");
    const excludedCount = requireCount(exclusion.excluded_count, "analysis_status.exclusion.excluded_count");
    const excludedList = requireArray(exclusion.excluded, "analysis_status.exclusion.excluded");
    excludedList.forEach((value, index) => {
      const itemPath = `analysis_status.exclusion.excluded[${index}]`;
      const item = requireRecord(value, itemPath);
      for (const key of ["side", "path", "kind", "source", "rule"]) {
        requireString(item[key], `${itemPath}.${key}`);
      }
    });
    if (excludedList.length !== excludedCount) {
      liveReportError("analysis_status.exclusion.excluded_count", "must equal the number of excluded entries");
    }
  }
  // Absent in older v2 writers: fall back to the strict equality check.
  const binaryHandling = text(metadata.binary_handling);

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
    if (item.comparison_method !== undefined) {
      const method = requireString(item.comparison_method, `${resultPath}.comparison_method`);
      if (method !== "difflib" && method !== "sha256-only" && method !== "not-compared") {
        liveReportError(`${resultPath}.comparison_method`, "must be 'difflib', 'sha256-only' or 'not-compared'");
      }
      requireNullableString(item.comparison_note, `${resultPath}.comparison_note`);
    }
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
  // pipeline.py counts a pair as failed when its error is a non-empty string.
  const errorResultCount = results.filter((value) => {
    const error = (value as UnknownRecord).error;
    return typeof error === "string" && error.length > 0;
  }).length;
  validateLiveStatus(
    source,
    results.length,
    errorResultCount,
    actualDiffTruncatedCount,
    metadata.deep_index_truncated as boolean,
    binaryHandling,
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
  const selectionStatus = record(status.selection);
  const exclusionStatus = record(status.exclusion);
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
      comparison_method: typeof item.comparison_method === "string" ? item.comparison_method : null,
      comparison_note: typeof item.comparison_note === "string" ? item.comparison_note : null,
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
      ignore_patterns: strings(meta.ignore_patterns),
      ignore_file_sha256: typeof meta.ignore_file_sha256 === "string" ? meta.ignore_file_sha256 : null,
      sensitive_files: text(meta.sensitive_files, "unknown"),
      include_patterns: strings(meta.include_patterns),
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
        // Absent in older reports: unknown (null), never 0.
        error_pair_count: num(diffStatus.error_pair_count),
        excluded_pair_count: num(diffStatus.excluded_pair_count),
        excluded_pairs: records(diffStatus.excluded_pairs),
      },
      deep: {
        requested_file_count: num(deepStatus.requested_file_count), successful_file_count: num(deepStatus.successful_file_count),
        failed_file_count: num(deepStatus.failed_file_count), failed_files: records(deepStatus.failed_files),
        // Absent in reports written before the field existed: unknown, not 0.
        skipped_binary_file_count: num(deepStatus.skipped_binary_file_count),
        skipped_binary_files: records(deepStatus.skipped_binary_files),
        unfingerprinted_file_count: num(deepStatus.unfingerprinted_file_count),
        unfingerprinted_files: records(deepStatus.unfingerprinted_files),
        lang_aware_fallback_files: records(deepStatus.lang_aware_fallback_files),
        reported_pair_count: num(deepStatus.reported_pair_count),
      },
      exclusion: {
        excluded_count: num(exclusionStatus.excluded_count),
        excluded: records(exclusionStatus.excluded),
      },
      selection: {
        omitted_unmatched_a_count: num(selectionStatus.omitted_unmatched_a_count),
        omitted_unmatched_b_count: num(selectionStatus.omitted_unmatched_b_count),
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

/**
 * Display text for a pair's similarity value. Hash-only pairs (binary, or
 * over --max-file-size) carry ratio 1.0/0.0 from a SHA-256 comparison
 * (pipeline.py), and pairs with an error were not compared at all, so
 * neither is shown as a content percentage.
 */
export function similarityText(result: ReportResult): string {
  if (result.error !== null || result.comparison_method === "not-compared") { return "not compared"; }
  // Current reports state that difflib did not run; show Python's own
  // wording (e.g. "Not compared by difflib (...); SHA-256 identical").
  if (typeof result.comparison_method === "string" && result.comparison_method !== "difflib") {
    return result.comparison_note || "not compared line by line";
  }
  if (result.binary) { return result.ratio >= 1 ? "identical (SHA-256)" : "differs (SHA-256)"; }
  return percentText(result.ratio);
}

/**
 * A line (or word) match ratio, 0..1, as a percentage with one decimal.
 * 100.0% is shown only for an exact 1.0 (models.line_match_label).
 */
export function percentText(ratio: number): string {
  return lineMatchLabel(ratio);
}

/** True when a pair's +/- line counts come from difflib (not hash-only, not an error). */
export function hasLineCounts(result: ReportResult): boolean {
  if (result.error !== null || result.binary) { return false; }
  return typeof result.comparison_method !== "string" || result.comparison_method === "difflib";
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
      message: "The report does not record whether every input was read and compared.",
    });
  }
  const incomplete = report.analysis_status.state === "incomplete"
    || meta.deep_index_truncated === true
    || report.results.some((result) => result.truncation.truncated === true);
  if (incomplete) {
    const reasons = report.analysis_status.reasons.length
      ? reasonSentences(report.analysis_status.reasons)
      : ["Part of the output was truncated or is partial."];
    const details: string[] = [];
    const collectionStatus = report.analysis_status.collection;
    const diffStatus = report.analysis_status.diff;
    const deepStatus = report.analysis_status.deep;
    if (diffStatus.successful_pair_count !== null && diffStatus.requested_pair_count !== null) {
      const excludedText = diffStatus.excluded_pair_count
        ? `, ${countLabel(diffStatus.excluded_pair_count)} left out by the binary-file policy` : "";
      details.push(`Line comparison: ${countLabel(diffStatus.successful_pair_count)} of ${plural(diffStatus.requested_pair_count, "pair")} processed ` +
        `(${diffStatus.failed_pair_count === null ? "failures not recorded" : `${countLabel(diffStatus.failed_pair_count)} failed`}${excludedText})`);
    }
    if (deepStatus.successful_file_count !== null && deepStatus.requested_file_count !== null) {
      const skippedText = deepStatus.skipped_binary_file_count
        ? `, ${countLabel(deepStatus.skipped_binary_file_count)} skipped (binary or not decodable as text)` : "";
      const belowText = deepStatus.unfingerprinted_file_count
        ? `, ${countLabel(deepStatus.unfingerprinted_file_count)} below k-gram size` : "";
      details.push(`Deep Compare: ${countLabel(deepStatus.successful_file_count)} of ${plural(deepStatus.requested_file_count, "file")} processed ` +
        `(${deepStatus.failed_file_count === null ? "failures not recorded" : `${countLabel(deepStatus.failed_file_count)} failed`}${skippedText}${belowText})`);
    }
    for (const failed of collectionStatus.failed_files) {
      details.push(`Input not read: ${text(failed.side, "?")}:${text(failed.path, "?")} (${text(failed.reason, "reason not recorded")})`);
    }
    for (const failed of diffStatus.failed_pairs) {
      details.push(`Pair not compared: ${text(failed.file_a, "?")} vs. ${text(failed.file_b, "?")} (${text(failed.reason, "reason not recorded")})`);
    }
    for (const failed of deepStatus.failed_files) {
      details.push(`File not processed by Deep Compare: ${text(failed.side, "?")}:${text(failed.path, "?")} (${text(failed.reason, "reason not recorded")})`);
    }
    const detailText = details.length ? ` ${details.join("; ")}.` : "";
    banners.push({ kind: "warning", title: "Incomplete analysis", message: `${reasons.join(" ")}${detailText} This result does not cover every input.` });
  }
  for (const result of report.results) {
    if (result.truncation.truncated === true) {
      const omitted = result.truncation.omitted_bytes === null
        ? "omitted byte count unknown"
        : `${countLabel(result.truncation.omitted_bytes)} bytes omitted`;
      banners.push({
        kind: "warning",
        title: "Truncated diff",
        message: `${result.file_a} vs. ${result.file_b}: ${result.truncation.reason ?? "reason not recorded"}; ${omitted}.`,
      });
    }
  }
  const sideAndPath = (item: UnknownRecord, withReason: boolean): string => {
    const reason = text(item.reason);
    return `${text(item.side, "?")}:${text(item.path, "?")}${withReason && reason ? ` (${reason})` : ""}`;
  };
  const excludedPairs = report.analysis_status.diff.excluded_pairs;
  if (excludedPairs.length > 0) {
    // Same disclosure as pipeline._analysis_status_summary.
    banners.push({
      kind: "info",
      title: "Matched pairs not compared (binary-file policy)",
      message: `${excludedPairs.length === 1 ? "1 matched pair was" : `${countLabel(excludedPairs.length)} matched pairs were`} ` +
        `left out by the binary-file policy and ${excludedPairs.length === 1 ? "has" : "have"} no result: ` +
        `${excludedPairs.map((item) => `${text(item.file_a, "?")} vs. ${text(item.file_b, "?")}` +
          (text(item.reason) ? ` (${text(item.reason)})` : "")).join("; ")}.`,
    });
  }
  const selection = report.analysis_status.selection;
  if ((selection.omitted_unmatched_a_count ?? 0) > 0 || (selection.omitted_unmatched_b_count ?? 0) > 0) {
    banners.push({
      kind: "info",
      title: "Selective report",
      message: "Unmatched files omitted from this report by the selection: " +
        `${selection.omitted_unmatched_a_count === null ? "not recorded" : countLabel(selection.omitted_unmatched_a_count)} in A, ` +
        `${selection.omitted_unmatched_b_count === null ? "not recorded" : countLabel(selection.omitted_unmatched_b_count)} in B. ` +
        "The unmatched counts do not describe the whole folders.",
    });
  }
  const skippedBinary = report.analysis_status.deep.skipped_binary_files;
  if (skippedBinary.length > 0) {
    // Same disclosure as the Python text/PDF reports (pipeline.py).
    banners.push({
      kind: "info",
      title: "Deep Compare skipped files (binary or not decodable as text)",
      message: `${plural(skippedBinary.length, "input file")} ${skippedBinary.length === 1 ? "was" : "were"} not fingerprinted because ` +
        `${skippedBinary.length === 1 ? "it is" : "they are"} binary or could not be decoded as text: ` +
        `${skippedBinary.map((item) => sideAndPath(item, true)).join("; ")}.`,
    });
  }
  const belowKgram = report.analysis_status.deep.unfingerprinted_files;
  if (belowKgram.length > 0) {
    banners.push({
      kind: "info",
      title: "Deep Compare files below k-gram size",
      message: `${plural(belowKgram.length, "input file")} ${belowKgram.length === 1 ? "was read but is" : "were read but are"} shorter than one k-gram, ` +
        `so ${belowKgram.length === 1 ? "it has no fingerprints and was" : "they have no fingerprints and were"} not compared by Deep Compare: ` +
        `${belowKgram.map((item) => sideAndPath(item, false)).join("; ")}.`,
    });
  }
  const fallback = report.analysis_status.deep.lang_aware_fallback_files;
  if (fallback.length > 0) {
    banners.push({
      kind: "info",
      title: "Language-aware lexer fallback",
      message: `${plural(fallback.length, "file")} could not be lexed and used the registry-keyword tier: ` +
        `${fallback.map((item) => `${text(item.side, "?")}:${text(item.path, "?")} (${text(item.tier, "?")})`).join("; ")}.`,
    });
  }
  // The Jaccard threshold only applies to Deep Compare. Simple mode never
  // fingerprints, so its (recorded but unused) threshold is not described
  // (same rule as cli.py and pipeline.py). One banner states the threshold:
  // Python's disclosure when the report carries it.
  if (meta.exec_mode !== "simple") {
    if (meta.threshold_provenance === "unknown" || meta.threshold === null) {
      banners.push({ kind: "warning", title: "Metadata unavailable", message: "This report does not record the effective threshold or its source." });
    } else {
      const title = meta.threshold_provenance === "user" ? "Threshold set by user"
        : meta.threshold_provenance === "legacy-uncalibrated" ? "Default threshold"
          : meta.threshold_provenance === "normalize-default" ? "Default threshold for normalized comparison"
            : "Jaccard threshold";
      const fallback = `Jaccard threshold: ${thresholdLabel(meta.threshold)}. Source: ${thresholdSourceLabel(meta.threshold_provenance)}.`;
      banners.push({
        kind: meta.normalize ? "warning" : "info",
        title,
        message: meta.calibration_disclosure || fallback,
      });
    }
  }

  const deepRows = report.deep_results.flatMap((result) => result.matches.map((match) => ({
    ...match,
    file_a: result.file_a,
    kind: match.inconclusive === true ? "inconclusive" as const : match.inconclusive === false ? "candidate" as const : "unknown" as const,
    label: match.inconclusive === true ? "Inconclusive" : match.inconclusive === false ? "Candidate" : "Status unknown",
  })));
  return { banners, deepRows };
}
