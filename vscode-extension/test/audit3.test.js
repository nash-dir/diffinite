/**
 * Regressions for the third audit round (extension side of the Python
 * report changes): excluded / error pairs, comparison notes, Deep files
 * below k-gram size, selection omitted counts, Windows cancellation, Bates
 * label validation and the exclusion-list template.
 */
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");

const vscodeStub = {
  Uri: { file: (fsPath) => ({ fsPath }) },
  ViewColumn: { Active: -1, One: 1, Beside: -2 },
  ProgressLocation: { Notification: 15 },
  workspace: { workspaceFolders: undefined, getConfiguration: () => ({ get: (_k, d) => d }) },
  env: { openExternal: async () => true },
  window: {},
  commands: { executeCommand: async () => undefined },
};
const originalLoad = Module._load;
Module._load = function load(request, ...rest) {
  if (request === "vscode") { return vscodeStub; }
  return originalLoad.call(this, request, ...rest);
};

const model = require("../out/analysisModel.js");
const runner = require("../out/runner.js");
const results = require("../out/resultViewer.js");
const tree = require("../out/treeViewer.js");
const presets = require("../out/reportPresets.js");
const ignoreList = require("../out/ignoreList.js");
const { buildReviewSummary } = require("../out/reviewSummary.js");

const root = path.join(__dirname, "..");
const source = (rel) => fs.readFileSync(path.join(root, rel), "utf8");
const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));

function row(overrides = {}) {
  return {
    file_a: "a.py", file_b: "a.py", name_similarity: 100, ratio: 0.5, additions: 1, deletions: 2,
    html_diff: "", error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
    comparison_method: "difflib", hash_only_reason: null, comparison_note: null,
    ...overrides,
  };
}

/**
 * A report in the current pipeline.py shape: 4 matched pairs, of which one
 * difflib pair, one SHA-256-only pair, one error pair (failed, with a row)
 * and one pair excluded by --binary-handling exclude (no row).
 */
function currentShapeReport({ diff = {}, deep = {}, selection, resultsList } = {}) {
  const raw = fixture("report-v2.json");
  raw.metadata.binary_handling = "exclude";
  raw.results = resultsList || [
    row(),
    row({
      file_a: "logo.bin", file_b: "logo.bin", ratio: 1, additions: 0, deletions: 0, binary: true,
      hash_match: true, comparison_method: "sha256-only", hash_only_reason: "max-file-size-exceeded",
      comparison_note: "Not compared by difflib (over --max-file-size); SHA-256 identical",
    }),
    row({
      file_a: "locked.py", file_b: "locked.py", ratio: 0, additions: 0, deletions: 0,
      error: "PermissionError", comparison_method: "not-compared",
    }),
  ];
  raw.summary.matched_pairs = raw.results.length;
  raw.summary.excluded_matched_pairs = 1;
  raw.analysis_status.state = "incomplete";
  raw.analysis_status.reasons = ["diff-pair-error"];
  raw.analysis_status.diff = {
    requested_pair_count: 4, successful_pair_count: 2, failed_pair_count: 1,
    failed_pairs: [{ file_a: "locked.py", file_b: "locked.py", reason: "pair-error: PermissionError" }],
    error_pair_count: 1,
    excluded_pair_count: 1,
    excluded_pairs: [{ file_a: "asset.dat", file_b: "asset.dat", reason: "binary-excluded" }],
    ...diff,
  };
  raw.analysis_status.deep = {
    requested_file_count: 5, successful_file_count: 3, failed_file_count: 0, failed_files: [],
    skipped_binary_file_count: 2,
    skipped_binary_files: [
      { side: "A", path: "blob.py", reason: "skipped-binary-content" },
      { side: "B", path: "data.xyz", reason: "skipped-undecodable-unregistered-extension" },
    ],
    unfingerprinted_file_count: 1,
    unfingerprinted_files: [{ side: "A", path: "tiny.py", reason: "below-k-gram-size" }],
    lang_aware_fallback_files: [],
    ...deep,
  };
  raw.analysis_status.selection = selection || { omitted_unmatched_a_count: 0, omitted_unmatched_b_count: 0 };
  return raw;
}

/* ---------------- analysisModel: count rules ---------------- */

test("a report with excluded and error pairs is accepted (requested = successful + failed + excluded)", () => {
  const report = model.parseLiveReport(currentShapeReport());
  assert.equal(report.analysis_status.diff.excluded_pair_count, 1);
  assert.equal(report.analysis_status.diff.error_pair_count, 1);
  assert.equal(report.analysis_status.diff.excluded_pairs[0].file_a, "asset.dat");
});

test("the same rule holds for every --binary-handling mode", () => {
  for (const mode of ["hash", "error", "exclude", undefined]) {
    const raw = currentShapeReport();
    if (mode === undefined) { delete raw.metadata.binary_handling; } else { raw.metadata.binary_handling = mode; }
    assert.doesNotThrow(() => model.parseLiveReport(raw), String(mode));
  }
});

test("inconsistent excluded / error counts are rejected", () => {
  assert.throws(() => model.parseLiveReport(currentShapeReport({ diff: { excluded_pair_count: 2 } })),
    /excluded_pair_count must equal/);
  assert.throws(() => model.parseLiveReport(currentShapeReport({ diff: { requested_pair_count: 5 } })),
    /successful plus failed plus excluded/);
  // One row too many for successful + error_pair_count.
  const extra = currentShapeReport();
  extra.results.push(row({ file_a: "b.py", file_b: "b.py" }));
  extra.summary.matched_pairs = extra.results.length;
  assert.throws(() => model.parseLiveReport(extra), /plus error_pair_count must equal results\.length/);
  // error_pair_count must match the rows that carry an error.
  const wrongErrors = currentShapeReport();
  wrongErrors.results[2] = row({ file_a: "locked.py", file_b: "locked.py" });
  assert.throws(() => model.parseLiveReport(wrongErrors), /error_pair_count must equal the number of results with an error/);
  assert.throws(() => model.parseLiveReport(currentShapeReport({ diff: { error_pair_count: 2 } })),
    /error_pair_count must not exceed/);
});

test("reports without the new fields keep the old rules", () => {
  assert.doesNotThrow(() => model.parseLiveReport(fixture("report-v2.json")));
  // Older writers: exclude counted dropped pairs as successful, without a row.
  const legacy = fixture("report-v2.json");
  legacy.metadata.binary_handling = "exclude";
  legacy.analysis_status.diff = { requested_pair_count: 2, successful_pair_count: 2, failed_pair_count: 0, failed_pairs: [] };
  legacy.results = [row()];
  legacy.summary.matched_pairs = 1;
  const report = model.parseLiveReport(legacy);
  assert.equal(report.analysis_status.diff.excluded_pair_count, null);
  assert.equal(report.analysis_status.selection.omitted_unmatched_a_count, null);
  // The legacy summary still derives the excluded count from the missing rows.
  const fact = buildReviewSummary(report).facts.find((f) => f.label === "File pairs not compared (--binary-handling exclude)");
  assert.equal(fact.value, "1");
  // Without exclude, the old strict rule still applies.
  legacy.metadata.binary_handling = "hash";
  assert.throws(() => model.parseLiveReport(legacy), /must equal results\.length/);
});

test("malformed selection and below-k-gram fields are rejected", () => {
  assert.throws(() => model.parseLiveReport(currentShapeReport({ selection: { omitted_unmatched_a_count: -1, omitted_unmatched_b_count: 0 } })),
    /omitted_unmatched_a_count/);
  assert.throws(() => model.parseLiveReport(currentShapeReport({ deep: { unfingerprinted_file_count: 3 } })),
    /unfingerprinted_file_count must equal/);
  const badMethod = currentShapeReport();
  badMethod.results[0].comparison_method = "guess";
  assert.throws(() => model.parseLiveReport(badMethod), /comparison_method must be/);
});

/* ---------------- display ---------------- */

test("excluded pairs, skipped files with reasons and below-k-gram files are disclosed", () => {
  const report = model.parseLiveReport(currentShapeReport());
  const banners = model.buildReportViewModel(report).banners;
  const excluded = banners.find((b) => /binary-file policy/.test(b.title));
  assert.match(excluded.message, /asset\.dat vs\. asset\.dat \(binary-excluded\)/);
  const skipped = banners.find((b) => /binary or not decodable as text/.test(b.title));
  assert.match(skipped.message, /A:blob\.py \(skipped-binary-content\)/);
  assert.match(skipped.message, /B:data\.xyz \(skipped-undecodable-unregistered-extension\)/);
  const below = banners.find((b) => /below k-gram size/.test(b.title));
  assert.match(below.message, /A:tiny\.py/);
  const incomplete = banners.find((b) => b.title === "Incomplete analysis");
  assert.match(incomplete.message, /1 left out by the binary-file policy/);
  assert.match(incomplete.message, /2 skipped \(binary or not decodable as text\), 1 below k-gram size/);
  assert.doesNotMatch(banners.map((b) => b.message).join(" "), /skipped as binary content/);

  const facts = buildReviewSummary(report).facts;
  const fact = (prefix) => facts.find((f) => f.label.startsWith(prefix));
  assert.equal(fact("File pairs not compared (--binary-handling exclude)").value, "1");
  assert.equal(fact("Deep Compare files skipped (binary or not decodable as text)").value, "2");
  assert.equal(fact("Deep Compare files with fewer tokens than the k-gram size").value, "1");
  assert.equal(fact("Deep Compare files with fewer tokens than the k-gram size").attention, true);

  const html = results.buildResultHtml(report, model.defaultAnalysisOptions(), "N");
  assert.match(html, /<strong>1<\/strong> matched pair not compared \(binary-file policy\)/);
  assert.match(html, /asset\.dat vs\. asset\.dat/);
});

test("older reports show below-k-gram as unknown instead of 0", () => {
  const raw = fixture("report-v2.json");
  const fact = buildReviewSummary(model.parseReport(raw)).facts.find((f) => f.label === "Deep Compare files with fewer tokens than the k-gram size");
  assert.equal(fact.value, "unknown");
});

test("selection omitted counts are shown; zero or absent shows nothing", () => {
  const report = model.parseLiveReport(currentShapeReport({ selection: { omitted_unmatched_a_count: 2, omitted_unmatched_b_count: 7 } }));
  const fact = buildReviewSummary(report).facts.find((f) => f.label.startsWith("Unmatched files omitted by the selection"));
  assert.equal(fact.value, "2 in A; 7 in B");
  const banner = model.buildReportViewModel(report).banners.find((b) => b.title === "Selective report");
  assert.match(banner.message, /2 in A, 7 in B/);
  const none = model.parseLiveReport(currentShapeReport());
  assert.equal(buildReviewSummary(none).facts.some((f) => f.label.startsWith("Unmatched files omitted")), false);
  assert.equal(model.buildReportViewModel(none).banners.some((b) => b.title === "Selective report"), false);
});

test("pairs difflib did not compare show the analyzer's note and no +0/-0", () => {
  const report = model.parseLiveReport(currentShapeReport());
  const [difflib, hashOnly, failed] = report.results;
  assert.equal(model.similarityText(difflib), "50.0%");
  assert.equal(model.similarityText(hashOnly), "Not compared by difflib (over --max-file-size); SHA-256 identical");
  assert.equal(model.similarityText(failed), "not compared");
  assert.equal(model.hasLineCounts(difflib), true);
  assert.equal(model.hasLineCounts(hashOnly), false);
  assert.equal(model.hasLineCounts(failed), false);

  const html = results.buildResultHtml(report, model.defaultAnalysisOptions(), "N");
  assert.match(html, /Not compared by difflib \(over --max-file-size\); SHA-256 identical/);
  assert.equal((html.match(/>Not compared line by line; no line counts</g) || []).length, 2, "hash-only and error pairs show no line counts");
  assert.equal((html.match(/>\+0</g) || []).length, 0);

  const treeHtml = tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N");
  assert.equal((treeHtml.match(/class="added">\+0</g) || []).length, 0);
  assert.equal((treeHtml.match(/title="Not compared line by line">n\/a/g) || []).length, 2);
  assert.match(treeHtml, /Not compared by difflib \(over --max-file-size\); SHA-256 identical/);
});

test("older reports without comparison_method keep the SHA-256 wording", () => {
  const legacy = model.parseReport({ results: [{ ...row({ binary: true, ratio: 0 }), comparison_method: undefined, comparison_note: undefined }] });
  assert.equal(legacy.results[0].comparison_method, null);
  assert.equal(model.similarityText(legacy.results[0]), "differs (SHA-256)");
});

test("a value below 1 is never shown as 100.0%", () => {
  assert.equal(model.percentText(1), "100.0%");
  assert.equal(model.percentText(0.99999), "99.9%");
  assert.equal(model.percentText(0.9994), "99.9%");
  assert.equal(model.percentText(0.5), "50.0%");
  assert.equal(model.similarityText(model.parseReport({ results: [row({ ratio: 0.99996 })] }).results[0]), "99.9%");
  const raw = fixture("report-v2.json");
  raw.deep_results = [{ file_a: "a.py", fingerprint_count_a: 10, matches: [
    { file_b: "b.py", shared_hashes: 9, jaccard: 0.99997, containment_a_in_b: 0.99996, containment_b_in_a: 1, inconclusive: false },
  ] }];
  const html = results.buildResultHtml(model.parseReport(raw), model.defaultAnalysisOptions(), "N");
  // Jaccard and containment carry two decimals (models.overlap_label).
  assert.match(html, /<span class="jlabel ">99\.99%<\/span>/);
  assert.doesNotMatch(html, /<span class="jlabel ">100\.00%/);
  assert.match(html, /<td>99\.99%<\/td>\s*<td>100\.00%<\/td>/);
});

/* ---------------- selection note wording ---------------- */

test("selection notes say the B list is omitted and A lists only selected files", () => {
  const treeSource = source("src/treeViewer.ts");
  assert.doesNotMatch(treeSource, /Lists of unmatched files are omitted from a selective report/);
  assert.match(treeSource, /list of files only in B is omitted/);
  assert.match(treeSource, /shows only the selected A files/);
  const lines = presets.describeReportOutput(model.defaultAnalysisOptions(), "html", { selectedPairs: 2 });
  const scope = lines.find((l) => l.startsWith("Scope:"));
  assert.match(scope, /list of files only in B is omitted/);
  assert.match(scope, /only the selected A files/);
});

/* ---------------- runner: Windows cancellation ---------------- */

test("taskkill is not allowed once the parent has exited (PID reuse)", () => {
  assert.equal(runner.windowsTreeKillAllowed({ exitCode: null, signalCode: null }), true);
  assert.equal(runner.windowsTreeKillAllowed({ exitCode: 0, signalCode: null }), false);
  assert.equal(runner.windowsTreeKillAllowed({ exitCode: null, signalCode: "SIGTERM" }), false);
  const src = source("src/runner.ts");
  assert.match(src, /os\.platform\(\) === "win32" && proc\.pid && !windowsTreeKillAllowed\(proc\)/);
});

test("cancellation messages are honest about workers that may remain", () => {
  const unreachable = runner.cancellationError("Analysis", { closed: false, stillRunning: false, pid: 42, workersUnreachable: true });
  assert.match(unreachable.message, /had already exited/);
  assert.match(unreachable.message, /may still be running/);
  const timedOut = runner.cancellationError("Export", { closed: false, stillRunning: false, pid: 42 });
  assert.match(timedOut.message, /may still be running/);
  assert.match(timedOut.message, /Existing output was preserved/);
  const clean = runner.cancellationError("Analysis", { closed: true, stillRunning: false, pid: 42 });
  assert.equal(clean.message, "Analysis canceled by user.");
});

/* ---------------- exclusion-list template ---------------- */

test("the exclusion-list template states case-sensitivity and unsupported syntax", () => {
  const text = ignoreList.DEFAULT_IGNORE_PATTERNS;
  assert.doesNotMatch(text, /dirnamess/);
  assert.match(text, /case-sensitive on every operating system/);
  assert.match(text, /"!" negation/);
  assert.ok(text.includes('"\\" escapes'), "the backslash must survive the template literal");
  // Every non-comment line stays commented: the template enables no rule.
  const active = text.split(/\r?\n/).filter((l) => l.trim() && !l.trim().startsWith("#"));
  assert.deepEqual(active, []);
});

/* ---------------- Bates prefix / suffix ---------------- */

test("Bates labels follow the CLI's bates_font_for rule", () => {
  for (const ok of ["", "PLAINTIFF-", "-CONFIDENTIAL", "Café-", "€-", "원고-", "ㄱ-A"]) {
    assert.equal(model.batesLabelError(ok), null, ok);
  }
  assert.match(model.batesLabelError("日本-"), /U\+65E5\) cannot be drawn/);
  assert.match(model.batesLabelError("\u0081"), /U\+0081/);
  assert.match(model.batesLabelError("😀"), /U\+1F600/);
  assert.match(model.batesLabelError("원고-é"), /together with Hangul/);
});

test("run options refuse an undrawable Bates label and >61 workers on Windows", () => {
  const base = model.defaultAnalysisOptions();
  assert.match(model.validateRunOptions({ ...base, batesPrefix: "原告-" }), /Bates prefix\/suffix/);
  assert.match(model.validateRunOptions({ ...base, batesPrefix: "원고-", batesSuffix: "-é" }), /together with Hangul/);
  assert.equal(model.validateRunOptions({ ...base, batesPrefix: "원고-" }), null);
  assert.match(model.validateRunOptions({ ...base, workers: 62 }, "win32"), /Workers must be a whole number between 1 and 61/);
  assert.equal(model.validateRunOptions({ ...base, workers: 61 }, "win32"), null);
  assert.equal(model.validateRunOptions({ ...base, workers: 62 }, "linux"), null);
});

test("the Options webview embeds the same Bates check and shows it inline", () => {
  const src = source("src/optionsPanel.ts");
  assert.match(src, /const batesLabelError = \$\{batesLabelError\.toString\(\)\};/);
  assert.match(src, /id="batesError" role="alert"/);
  assert.match(src, /addEventListener\('input', checkBatesLabel\)/);
  // The embedded source must be self-contained JavaScript.
  const fn = new Function(`return (${model.batesLabelError.toString()});`)();
  assert.equal(fn("원고-"), null);
  assert.match(fn("日"), /cannot be drawn/);
});

/* ---------------- docs ---------------- */

test("CHANGELOG names the Options panel button as it is labelled", () => {
  const changelog = source("CHANGELOG.md");
  assert.match(source("src/optionsPanel.ts"), />Edit Dictionary</);
  assert.match(changelog, /\*Edit Dictionary\*/);
  assert.doesNotMatch(changelog, /Edit Exclusion List/);
  assert.doesNotMatch(source("README.md"), /Edit Exclusion List/);
});

test("Bates labels with control characters are refused in the UI as in the CLI", () => {
  const model = require("../out/analysisModel.js");
  assert.match(model.batesLabelError("A\tB"), /control character \(U\+0009\)/);
  assert.match(model.batesLabelError("A\u007fB"), /U\+007F/);
  assert.equal(model.batesLabelError("PLAINTIFF-"), null);
});

test("malformed optional deep lists are rejected, not shown as none", () => {
  const model = require("../out/analysisModel.js");
  const fs = require("node:fs");
  const path = require("node:path");
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "report-v2.json"), "utf8"));
  raw.analysis_status.deep.lang_aware_fallback_files = "not-a-list";
  assert.throws(() => model.parseLiveReport(raw), /lang_aware_fallback_files/);
});
