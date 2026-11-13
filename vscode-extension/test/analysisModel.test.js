const assert = require("node:assert/strict");
const test = require("node:test");

const model = require("../out/analysisModel.js");
const fs = require("node:fs");
const path = require("node:path");
const tempFiles = require("../out/tempFiles.js");

function fixture(name) {
  return JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
}

function argsFor(overrides = {}) {
  return model.buildCoreArgs({ ...model.defaultAnalysisOptions(), ...overrides });
}

function hasDeepThreshold(args) {
  return args.includes("--threshold-deep");
}

test("raw + auto omits --threshold-deep", () => {
  assert.equal(hasDeepThreshold(argsFor({ normalize: false, thresholdMode: "auto" })), false);
});

test("normalize + auto lets Python choose its calibrated default", () => {
  const args = argsFor({ normalize: true, thresholdMode: "auto" });
  assert.equal(hasDeepThreshold(args), false);
  assert.equal(args.includes("93"), false);
});

test("raw and normalize manual thresholds are passed as user values", () => {
  for (const normalize of [false, true]) {
    const args = argsFor({ normalize, thresholdMode: "manual", thresholdDeep: 17 });
    const index = args.indexOf("--threshold-deep");
    assert.ok(index >= 0);
    assert.equal(args[index + 1], "17");
  }
});

test("ambiguous legacy thresholdDeep 5 is retained and warned, not silently reset", () => {
  const migrated = model.migratePersistedOptions({ normalize: true, thresholdDeep: 5 });
  assert.equal(migrated.options.thresholdMode, "manual");
  assert.equal(migrated.options.thresholdDeep, 5);
  assert.match(migrated.warnings.join(" "), /legacy|ambiguous|5/i);
});

test("legacy JSON remains parseable and missing semantics fall back to unknown", () => {
  const report = model.parseReport(fixture("report-v1.json"));
  assert.equal(report.schema_version, 1);
  assert.equal(report.metadata.threshold_provenance, "unknown");
  assert.equal(report.metadata.normalize, null);
  assert.equal(report.analysis_status.state, "unknown");
});

test("live subprocess JSON requires the current complete schema", () => {
  const report = model.parseLiveReport(fixture("report-v2.json"));
  assert.equal(report.schema_version, 2);
  assert.equal(report.analysis_status.state, "complete");

  assert.throws(
    () => model.parseLiveReport(newReport({ schema_version: 3 })),
    /schema_version|unsupported/i,
  );
});

test("a v1 report from an older Python package explains the version mismatch", () => {
  assert.throws(
    () => model.parseLiveReport(fixture("report-v1.json")),
    /older than 0\.14\.0/,
  );
});

test("live subprocess JSON rejects missing required fields instead of fabricating an empty report", () => {
  assert.throws(
    () => model.parseLiveReport({}),
    /schema_version|dir_a|live report/i,
  );

  const missingCollectionStatus = newReport();
  delete missingCollectionStatus.analysis_status.collection;
  assert.throws(
    () => model.parseLiveReport(missingCollectionStatus),
    /analysis_status\.collection/i,
  );
});

test("live subprocess JSON rejects inconsistent summary and status counts", () => {
  const summaryMismatch = newReport();
  summaryMismatch.summary = { ...summaryMismatch.summary, matched_pairs: 1 };
  assert.throws(() => model.parseLiveReport(summaryMismatch), /matched_pairs|results/i);

  const statusMismatch = newReport();
  statusMismatch.analysis_status = {
    ...statusMismatch.analysis_status,
    diff: {
      requested_pair_count: 2,
      successful_pair_count: 1,
      failed_pair_count: 0,
      failed_pairs: [],
    },
  };
  assert.throws(() => model.parseLiveReport(statusMismatch), /requested_pair_count|status/i);

  const truncationMismatch = newReport({
    results: [{
      file_a: "a.py", file_b: "b.py", name_similarity: 100,
      ratio: 0.5, additions: 1, deletions: 1, html_diff: "truncated",
      error: null, binary: false,
      truncation: {
        truncated: true, reason: "max-diff-html-size",
        original_bytes: 4096, omitted_bytes: 2048,
      },
    }],
    summary: { matched_pairs: 1, unmatched_a_count: 0, unmatched_b_count: 0 },
    analysis_status: {
      state: "complete", reasons: [],
      collection: { failed_file_count: 0, failed_files: [] },
      diff: { requested_pair_count: 1, successful_pair_count: 1, failed_pair_count: 0, failed_pairs: [] },
      deep: { requested_file_count: 0, successful_file_count: 0, failed_file_count: 0, failed_files: [] },
      truncation: { deep_index_truncated: false, diff_truncated_count: 0 },
    },
  });
  assert.throws(() => model.parseLiveReport(truncationMismatch), /diff_truncated_count|truncat/i);
});

function newReport(overrides = {}) {
  return { ...fixture("report-v2.json"), ...overrides };
}

test("inconclusive is rendered as Inconclusive, not as a candidate", () => {
  const report = model.parseReport(newReport({
    deep_results: [{
      file_a: "a.py", fingerprint_count_a: 2,
      matches: [{ file_b: "b.py", shared_hashes: 2, jaccard: 0.99, inconclusive: true }],
    }],
  }));
  const view = model.buildReportViewModel(report);
  assert.equal(view.deepRows[0].label, "Inconclusive");
  assert.equal(view.deepRows[0].kind, "inconclusive");
});

test("manual normalize threshold and canonical disclosure produce warnings", () => {
  const view = model.buildReportViewModel(model.parseReport(newReport()));
  assert.ok(view.banners.some((b) => /threshold set by user/i.test(b.title)));
  assert.ok(view.banners.some((b) => b.message === "Canonical Python disclosure"));
});

test("index truncation and partial worker failure produce Incomplete analysis banner", () => {
  const raw = newReport();
  raw.analysis_status = {
    ...raw.analysis_status,
    state: "incomplete",
    reasons: ["deep-index-truncated", "worker-failure"],
    deep: { requested_file_count: 2, successful_file_count: 1, failed_file_count: 1, failed_files: [{ side: "B", path: "b.py", reason: "boom" }] },
    truncation: { deep_index_truncated: true, diff_truncated_count: 0 },
  };
  const view = model.buildReportViewModel(model.parseReport(raw));
  const banner = view.banners.find((b) => b.title === "Incomplete analysis");
  assert.ok(banner);
  // Reason codes are stated as plain sentences, never as internal tokens.
  assert.match(banner.message, /Deep Compare index reached the --max-index-entries limit/);
  assert.match(banner.message, /Another part of the analysis did not complete/);
  assert.doesNotMatch(banner.message, /deep-index-truncated|worker-failure/);
  assert.match(banner.message, /does not cover every input/);
  assert.match(banner.message, /1 of 2 files processed/);
  assert.match(banner.message, /b\.py/);
});

test("collection failures are shown as incomplete evidence inputs", () => {
  const raw = newReport();
  raw.analysis_status = {
    ...raw.analysis_status,
    state: "incomplete",
    reasons: ["collection-file-skipped"],
    collection: {
      failed_file_count: 1,
      failed_files: [{ side: "A", path: "restricted/source.py", reason: "unreadable" }],
    },
  };
  const report = model.parseLiveReport(raw);
  const banner = model.buildReportViewModel(report).banners.find((b) => b.title === "Incomplete analysis");
  assert.ok(banner);
  assert.match(banner.message, /restricted\/source\.py/);
});

test("truncated diff banner preserves reason and known omitted bytes", () => {
  const raw = newReport({
    results: [{
      file_a: "large-a.py", file_b: "large-b.py", name_similarity: 100,
      ratio: 0.5, additions: 1, deletions: 1, html_diff: "truncated",
      error: null, binary: false,
      truncation: {
        truncated: true, reason: "max-diff-html-size",
        original_bytes: 4096, omitted_bytes: 4096,
      },
    }],
  });
  const view = model.buildReportViewModel(model.parseReport(raw));
  const banner = view.banners.find((b) => b.title === "Truncated diff");
  assert.ok(banner);
  assert.match(banner.message, /large-a\.py/);
  assert.match(banner.message, /max-diff-html-size/);
  assert.match(banner.message, /4,096 bytes omitted/);
});

test("missing fields use safe fallbacks instead of throwing", () => {
  const report = model.parseReport({ dir_a: "a", dir_b: "b" });
  const view = model.buildReportViewModel(report);
  assert.equal(report.results.length, 0);
  assert.equal(report.metadata.threshold_provenance, "unknown");
  assert.ok(view.banners.some((b) => /metadata unavailable/i.test(b.title)));
  assert.ok(view.banners.some((b) => /completeness unknown/i.test(b.title)));
});

test("temporary JSON paths are collision-safe and cleanup removes their directories", () => {
  const first = tempFiles.createTempJsonFile("diffinite-test-");
  const second = tempFiles.createTempJsonFile("diffinite-test-");
  assert.notEqual(first.directory, second.directory);
  fs.writeFileSync(first.filePath, "{}", "utf8");
  first.cleanup();
  second.cleanup();
  assert.equal(fs.existsSync(first.directory), false);
  assert.equal(fs.existsSync(second.directory), false);
});

test("help text does not overstate checksums or classify copying", () => {
  const helpSource = fs.readFileSync(path.join(__dirname, "..", "src", "helpViewer.ts"), "utf8");
  assert.doesNotMatch(helpSource, /cryptographic chain of custody/i);
  assert.doesNotMatch(helpSource, /identified as a ["']clone["']/i);
  assert.doesNotMatch(helpSource, /if the plagiarist/i);
});

function excludeReport({ binaryHandling, requested, results }) {
  const raw = fixture("report-v2.json");
  const rows = Array.from({ length: results }, (_, i) => ({
    file_a: `f${i}.py`, file_b: `f${i}.py`, name_similarity: 100, ratio: 1, additions: 0, deletions: 0,
    html_diff: "", error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
  }));
  return {
    ...raw,
    metadata: { ...raw.metadata, ...(binaryHandling ? { binary_handling: binaryHandling } : {}) },
    results: rows,
    summary: { ...raw.summary, matched_pairs: results },
    analysis_status: {
      ...raw.analysis_status,
      diff: { requested_pair_count: requested, successful_pair_count: requested, failed_pair_count: 0, failed_pairs: [] },
    },
  };
}

test("binary-handling exclude may leave fewer result rows than processed pairs", () => {
  // pipeline.py counts an excluded binary pair as processed but writes no row.
  const report = model.parseLiveReport(excludeReport({ binaryHandling: "exclude", requested: 2, results: 1 }));
  assert.equal(report.results.length, 1);
  assert.throws(
    () => model.parseLiveReport(excludeReport({ binaryHandling: "exclude", requested: 1, results: 2 })),
    /at least results\.length/,
  );
});

test("every other binary policy still requires one row per processed pair", () => {
  for (const binaryHandling of ["hash", "error", undefined]) {
    assert.throws(
      () => model.parseLiveReport(excludeReport({ binaryHandling, requested: 2, results: 1 })),
      /must equal results\.length/,
      String(binaryHandling),
    );
  }
});
