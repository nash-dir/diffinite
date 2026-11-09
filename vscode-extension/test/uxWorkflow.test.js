const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const test = require("node:test");

// The webview builders live in modules that import "vscode". Their HTML
// builders never touch the API, so an empty stub is enough to load them.
const originalLoad = Module._load;
Module._load = function load(request, ...rest) {
  if (request === "vscode") { return {}; }
  return originalLoad.call(this, request, ...rest);
};

const model = require("../out/analysisModel.js");
const presets = require("../out/reportPresets.js");
const { classifyFailure } = require("../out/failureClassifier.js");
const { buildReviewSummary } = require("../out/reviewSummary.js");
const tree = require("../out/treeViewer.js");
const results = require("../out/resultViewer.js");

function fixture(name) {
  return JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
}

function result(overrides = {}) {
  return {
    file_a: "a.py", file_b: "b.py", name_similarity: 100, ratio: 0.5,
    additions: 1, deletions: 1, html_diff: "", error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
    ...overrides,
  };
}

function reportWith(rows, overrides = {}, requested = rows.length) {
  const raw = fixture("report-v2.json");
  return model.parseReport({
    ...raw,
    results: rows,
    summary: { matched_pairs: rows.length, unmatched_a_count: 2, unmatched_b_count: 3 },
    analysis_status: {
      ...raw.analysis_status,
      diff: { requested_pair_count: requested, successful_pair_count: requested, failed_pair_count: 0, failed_pairs: [] },
    },
    ...overrides,
  });
}

/* ---------------- Report presets ---------------- */

const OPTION_VARIANTS = [
  {},
  { mode: "simple", byWord: true, stripComments: true },
  { normalize: true, thresholdMode: "manual", thresholdDeep: 17, detectMoved: true },
  { pageNumber: false, fileNumber: false, batesNumber: false, hash: false, batesPrefix: "P-", batesSuffix: "-S", batesStart: 9 },
  { noMerge: true, preserveTree: false, uncomparedFiles: "separate", selectedFiles: ["a.py"] },
];

test("presets never change the arguments that decide the metrics", () => {
  for (const variant of OPTION_VARIANTS) {
    const options = { ...model.defaultAnalysisOptions(), ...variant };
    const baseline = presets.analysisArgs(options);
    for (const preset of presets.REPORT_PRESETS) {
      assert.deepEqual(
        presets.analysisArgs(presets.applyReportPreset(options, preset.id)),
        baseline,
        `preset ${preset.id} changed analysis args for ${JSON.stringify(variant)}`,
      );
    }
  }
});

test("presets only touch output keys and the configured preset changes nothing", () => {
  const options = { ...model.defaultAnalysisOptions(), batesNumber: false, hash: false };
  assert.deepEqual(presets.applyReportPreset(options, "configured"), options);
  const outputKeys = new Set(["pageNumber", "fileNumber", "batesNumber", "hash"]);
  for (const preset of presets.REPORT_PRESETS) {
    const applied = presets.applyReportPreset(options, preset.id);
    for (const key of Object.keys(options)) {
      if (!outputKeys.has(key)) { assert.deepEqual(applied[key], options[key], `${preset.id} changed ${key}`); }
    }
  }
  const evidence = presets.applyReportPreset(options, "evidence");
  assert.equal(evidence.batesNumber, true);
  assert.equal(evidence.hash, true);
  const technical = presets.applyReportPreset({ ...options, batesNumber: true }, "technical");
  assert.equal(technical.batesNumber, false);
});

test("unknown presets and formats from the webview are rejected", () => {
  for (const bad of ["", "executive", null, undefined, 1, "__proto__", "toString"]) {
    assert.equal(presets.isReportPresetId(bad), false, String(bad));
  }
  for (const bad of ["pdf ", "json", "PDF", null]) {
    assert.equal(presets.isReportFormat(bad), false, String(bad));
  }
  assert.throws(() => presets.applyReportPreset(model.defaultAnalysisOptions(), "executive"));
});

test("export description states scope, format limits and the hash caveat", () => {
  const options = { ...model.defaultAnalysisOptions(), batesPrefix: "CASE-", batesStart: 7 };
  const pdf = presets.describeReportOutput(options, "pdf", { selectedPairs: 3 }).join("\n");
  assert.match(pdf, /3 file pair\(s\) selected/);
  assert.match(pdf, /unmatched files are omitted/);
  assert.match(pdf, /prefix CASE-.*starting at 7/);
  assert.match(pdf, /do not by themselves establish authenticity/);
  const md = presets.describeReportOutput(options, "md", { selectedPairs: null }).join("\n");
  assert.match(md, /every matched file pair/);
  assert.match(md, /not applicable to Markdown/);
  assert.doesNotMatch(md, /Bates numbers: yes/);
});

test("Bates text starting with '-' is passed as one --flag=value argument", () => {
  const args = model.buildCoreArgs({ ...model.defaultAnalysisOptions(), batesPrefix: "-P", batesSuffix: "-CONFIDENTIAL" });
  assert.ok(args.includes("--bates-prefix=-P"));
  assert.ok(args.includes("--bates-suffix=-CONFIDENTIAL"));
  assert.equal(args.includes("-CONFIDENTIAL"), false);
});

/* ---------------- Failure classification ---------------- */

test("failures are classified from the analyzer's own messages", () => {
  const cases = [
    ["Analysis cancelled by user.", "cancelled"],
    ["Export cancelled, but analyzer PID 12 is still running after forced termination", "cancelled-incomplete"],
    ["Analysis cancelled; the analyzer did not emit a close event before timeout.", "cancelled-incomplete"],
    ["Failed to parse JSON report: Error: ENOENT: no such file or directory, open 'x.json'", "invalid-report"],
    ["Failed to publish complete export artifacts: Error: ENOENT: no such file or directory, rename 'a' -> 'b'", "unknown"],
    ["Failed to start diffinite. Check that the bundled binary exists\nspawn python ENOENT", "runtime-missing"],
    ["diffinite exited with code 1:\nModuleNotFoundError: No module named 'diffinite'", "runtime-missing"],
    ["diffinite exited with code 1:\nRuntimeError: Input collection was incomplete: 2 file or directory entry", "unreadable-input"],
    ["diffinite export failed (code 1):\nRuntimeError: PDF rendering failed for 2 report part(s)", "pdf-failed"],
    ["diffinite exited with code 1:\nMemoryError", "out-of-memory"],
    ["diffinite exited with code 1:\nRuntimeError: 1 rendering worker(s) crashed; refusing a partial report", "partial-refused"],
    ["diffinite exited with code 1:\ndiffinite.evidence.SourceIntegrityError: Refusing linked output", "integrity"],
    ["diffinite exited with code 2:\nusage: diffinite\ndiffinite: error: --k-gram must be >= 1.", "invalid-argument"],
    ["Invalid live report: schema_version is missing", "invalid-report"],
    ["something nobody anticipated", "unknown"],
  ];
  for (const [message, kind] of cases) {
    assert.equal(classifyFailure(new Error(message)).kind, kind, message);
  }
});

test("the final exception line wins over earlier warning lines", () => {
  const stderr = [
    "diffinite export failed (code 1):",
    "WARNING Access Denied (PermissionError) for a.py",
    "ERROR PDF conversion failed for x.pdf: boom",
    "Traceback (most recent call last):",
    "RuntimeError: PDF rendering failed for 1 report part(s); no successful PDF report",
  ].join("\n");
  const failure = classifyFailure(new Error(stderr));
  assert.equal(failure.kind, "pdf-failed");
  assert.equal(failure.details, stderr, "details keep the original text");
});

/* ---------------- Review summary ---------------- */

test("summary counts come straight from the report", () => {
  const report = reportWith([
    result(),
    result({ file_a: "c.bin", file_b: "c.bin", binary: true, ratio: 1 }),
    result({ file_a: "d.py", file_b: "d.py", error: "Access Denied (PermissionError)", ratio: 0 }),
  ], {
    deep_results: [{
      file_a: "a.py", fingerprint_count_a: 3,
      matches: [
        { file_b: "b.py", shared_hashes: 3, jaccard: 0.4, inconclusive: false },
        { file_b: "x.py", shared_hashes: 1, jaccard: 0.9, inconclusive: true },
      ],
    }],
  });
  const summary = buildReviewSummary(report);
  const fact = (label) => summary.facts.find((f) => f.label.startsWith(label));
  assert.equal(fact("Matched pairs").value, "3");
  assert.equal(fact("Files only in A").value, "2");
  assert.equal(fact("Files only in B").value, "3");
  assert.equal(fact("Pairs with errors").value, "1");
  assert.equal(fact("Pairs with errors").attention, true);
  assert.equal(fact("Hash-only pairs").value, "1");
  assert.equal(fact("Deep Compare similarity candidates").value, "1");
  assert.equal(fact("Deep Compare inconclusive").value, "1");
  assert.equal(summary.errorPairs, 1);
  assert.equal(summary.binaryPairs, 1);
});

test("pairs dropped by the binary-file policy are shown, not silently missing", () => {
  const summary = buildReviewSummary(reportWith([result()], {}, 3));
  const fact = summary.facts.find((f) => f.label.startsWith("Matched pairs left out"));
  assert.equal(fact.value, "2");
  assert.equal(fact.attention, true);
  assert.equal(summary.facts.find((f) => f.label.startsWith("Matched pairs (")).value, "3");
  assert.equal(buildReviewSummary(reportWith([result()])).facts.some((f) => f.label.startsWith("Matched pairs left out")), false);
});

test("summary says unknown instead of guessing for legacy reports", () => {
  const legacy = model.parseReport(fixture("report-v1.json"));
  const summary = buildReviewSummary(legacy);
  const state = summary.facts.find((f) => f.label === "Analysis state");
  assert.equal(state.value, "Unknown");
  assert.equal(state.attention, true);
  assert.equal(summary.facts.find((f) => f.label.startsWith("Inputs skipped")).value, "unknown");
});

test("simple mode reports Deep Compare as not run", () => {
  const raw = fixture("report-v2.json");
  const report = model.parseReport({ ...raw, metadata: { ...raw.metadata, exec_mode: "simple" } });
  const deep = buildReviewSummary(report).facts.find((f) => f.label.startsWith("Deep Compare"));
  assert.equal(deep.value, "Not run (Simple mode)");
});

/* ---------------- Tree Viewer ---------------- */

test("diff paths cannot escape the compared folders", () => {
  const root = path.resolve("/tmp/diffinite-root");
  assert.equal(tree.resolveInside(root, "pkg/a.py"), path.join(root, "pkg", "a.py"));
  assert.equal(tree.resolveInside(root, "../outside.py"), null);
  assert.equal(tree.resolveInside(root, "pkg/../../outside.py"), null);
  assert.equal(tree.resolveInside(root, path.resolve("/etc/passwd")), null);
  assert.equal(tree.resolveInside(root, ""), null);
  assert.equal(tree.resolveInside(root, ".."), null);
  assert.equal(tree.resolveInside(root, "..eslintrc"), path.join(root, "..eslintrc"));
  assert.equal(tree.resolveInside(root, "...config/x.js"), path.join(root, "...config", "x.js"));
});

test("tree viewer escapes file names and keeps Korean/long paths intact", () => {
  const evil = `<img src=x onerror="alert(1)">.py`;
  const korean = "한글 디렉터리/아주 긴 파일 이름 (복사본) [최종] #1 & 2.py";
  const long = "a/".repeat(80) + "deep.py";
  const report = reportWith([result({ file_a: evil, file_b: korean }), result({ file_a: long, file_b: long, ratio: 0 })]);
  const rows = tree.sortForReview(report);
  const html = tree.buildTreeViewerHtml(report, rows, "NONCE123");
  assert.equal(html.includes(evil), false, "raw markup must not appear");
  assert.ok(html.includes("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;.py"));
  assert.ok(html.includes("한글 디렉터리/아주 긴 파일 이름 (복사본) [최종] #1 &amp; 2.py"));
  assert.ok(html.includes(long));
  assert.match(html, /script-src 'nonce-NONCE123'/);
  assert.equal((html.match(/<script/g) || []).length, 1, "only the nonce'd script");
  // Pre-selection is unchanged: ratio > 0 checked, ratio 0 not.
  assert.equal((html.match(/class="file-cb"[^>]*checked/g) || []).length, 1);
});

test("tree viewer handles an empty result set", () => {
  const report = reportWith([]);
  const html = tree.buildTreeViewerHtml(report, [], "N");
  assert.match(html, /No matched file pairs/);
  assert.match(html, /of 0 pairs selected/);
});

test("tree viewer sorts by content then name similarity", () => {
  const report = reportWith([
    result({ file_a: "low.py", ratio: 0.1 }),
    result({ file_a: "tie-low-name.py", ratio: 0.9, name_similarity: 10 }),
    result({ file_a: "tie-high-name.py", ratio: 0.9, name_similarity: 90 }),
  ]);
  assert.deepEqual(tree.sortForReview(report).map((r) => r.file_a), ["tie-high-name.py", "tie-low-name.py", "low.py"]);
});

/* ---------------- Webview theming ---------------- */

test("webviews take colours from the VS Code theme, not a fixed dark palette", () => {
  const report = reportWith([result({ html_diff: '<table class="difftbl"></table>' })]);
  const htmls = [
    tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N"),
    results.buildResultHtml(report, { ...model.defaultAnalysisOptions(), selectedFiles: ["a.py"] }, "N"),
  ];
  for (const html of htmls) {
    assert.match(html, /var\(--vscode-editor-background/);
    assert.equal(/--bg:\s*#1e1e1e/.test(html), false);
    // A red/yellow/green scale on similarity reads as a verdict.
    assert.equal(/badge-(high|mid|low)/.test(html), false);
  }
});

test("result viewer offers every preset and format with a matching description", () => {
  const report = reportWith([result()]);
  const html = results.buildResultHtml(report, { ...model.defaultAnalysisOptions(), selectedFiles: ["a.py"] }, "N");
  for (const preset of presets.REPORT_PRESETS) {
    assert.ok(html.includes(`value="${preset.id}"`));
    for (const format of ["pdf", "html", "md"]) {
      assert.ok(html.includes(`data-combo="${preset.id}:${format}"`), `${preset.id}:${format}`);
    }
  }
  assert.match(html, /1 file pair\(s\) selected/);
});

test("hash-only and failed pairs are not shown as a content percentage", () => {
  assert.equal(model.similarityText(result({ ratio: 0.456 })), "45.6%");
  assert.equal(model.similarityText(result({ binary: true, ratio: 1 })), "identical (SHA-256)");
  assert.equal(model.similarityText(result({ binary: true, ratio: 0 })), "differs (SHA-256)");
  assert.equal(model.similarityText(result({ error: "Access Denied (PermissionError)", ratio: 0 })), "not compared");
  const report = reportWith([result({ file_a: "big.bin", binary: true, ratio: 0 })]);
  const html = tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N");
  assert.match(html, /differs \(SHA-256\)/);
  assert.doesNotMatch(html, /<strong>0\.0%<\/strong>/);
});
