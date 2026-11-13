/**
 * Report-style contract for the extension UI (second polish pass).
 *
 * - Figures use the same formats as the Python reports (models.py helpers,
 *   mirrored in src/labels.ts).
 * - Each metric has one name: "Line match" (or "Word match"), "Name
 *   similarity", "Jaccard", "A in B", "B in A".
 * - The threshold source and the incomplete-analysis reasons are shown in
 *   plain words, never as internal tokens.
 * - Notices come from src/notices.ts, which mirrors src/diffinite/notices.py.
 * - The Result Viewer's navigation bar never covers diff content, and the
 *   diff styling stays legible in High Contrast and with CJK text.
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
  window: {},
  commands: { executeCommand: async () => undefined },
};
const originalLoad = Module._load;
Module._load = function load(request, ...rest) {
  if (request === "vscode") { return vscodeStub; }
  return originalLoad.call(this, request, ...rest);
};

const labels = require("../out/labels.js");
const model = require("../out/analysisModel.js");
const results = require("../out/resultViewer.js");
const tree = require("../out/treeViewer.js");
const notices = require("../out/notices.js");
const presets = require("../out/reportPresets.js");
const { buildReviewSummary } = require("../out/reviewSummary.js");
const { pipelineStepMessage } = require("../out/lineBuffer.js");
const runner = require("../out/runner.js");

const ROOT = path.join(__dirname, "..");
const src = (name) => fs.readFileSync(path.join(ROOT, "src", name), "utf8");
const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));

/** One matched pair (InventoryLedger), one Deep Compare row, 1 unmatched file per side. */
function onePairReport(overrides = {}) {
  const raw = fixture("report-v2.json");
  raw.metadata = { ...raw.metadata, threshold: 5, threshold_provenance: "legacy-uncalibrated", normalize: false, calibration_disclosure: null };
  raw.results = [{
    file_a: "InventoryLedger.java", file_b: "InventoryLedger.cs", name_similarity: 84.21052631578947,
    ratio: 0.15, additions: 1098, deletions: 3411, html_diff: "<table class=\"difftbl\"></table>", error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
  }];
  raw.deep_results = [{
    file_a: "InventoryLedger.java", fingerprint_count_a: 40,
    matches: [{ file_b: "InventoryLedger.cs", shared_hashes: 1234, jaccard: 0.2795, containment_a_in_b: 0.0824, containment_b_in_a: 1, inconclusive: false }],
  }];
  raw.summary = { ...raw.summary, matched_pairs: 1, unmatched_a_count: 1, unmatched_b_count: 1 };
  raw.unmatched_a = ["OnlyA.java"];
  raw.unmatched_b = ["OnlyB.cs"];
  Object.assign(raw, overrides);
  return model.parseReport(raw);
}

/* ---------------- number formats (copy-review #6, #7; visual #2) ---------------- */

// Values produced by src/diffinite/models.py (line_match_label, overlap_label,
// name_similarity_label, threshold_label, count_label) with the .venv-ci
// interpreter. 0.1225, 0.0125 and 0.03125 are exact binary halves, where
// Python rounds half to even and plain toFixed would not.
const PY = {
  line: [[0, "0.0%"], [1, "100.0%"], [0.5, "50.0%"], [0.99999, "99.9%"], [0.9994, "99.9%"], [0.99995, "99.9%"],
    [0.12345, "12.3%"], [0.1225, "12.2%"], [0.0125, "1.2%"], [0.2795, "28.0%"], [0.28205, "28.2%"], [0.0824, "8.2%"],
    [0.15, "15.0%"], [0.333333, "33.3%"], [0.6666666, "66.7%"], [5e-05, "0.0%"], [0.995, "99.5%"], [0.005, "0.5%"],
    [0.0005, "0.1%"], [0.1235, "12.3%"], [0.4445, "44.5%"], [0.03125, "3.1%"]],
  overlap: [[0, "0.00%"], [1, "100.00%"], [0.5, "50.00%"], [0.99999, "99.99%"], [0.9994, "99.94%"], [0.99995, "99.99%"],
    [0.12345, "12.35%"], [0.1225, "12.25%"], [0.0125, "1.25%"], [0.2795, "27.95%"], [0.28205, "28.21%"], [0.0824, "8.24%"],
    [0.15, "15.00%"], [0.333333, "33.33%"], [0.6666666, "66.67%"], [5e-05, "0.01%"], [4.9e-05, "0.00%"], [0.995, "99.50%"],
    [0.005, "0.50%"], [0.0005, "0.05%"], [0.1235, "12.35%"], [0.4445, "44.45%"], [0.03125, "3.12%"]],
  name: [[0, "0.0%"], [100, "100.0%"], [84.21052631578947, "84.2%"], [99.96, "99.9%"], [12.25, "12.2%"], [50, "50.0%"], [66.66666, "66.7%"]],
  threshold: [[93, "93%"], [5, "5%"], [92.5, "92.5%"], [0.1, "0.1%"], [45, "45%"], [33.333333333, "33.3333%"], [null, "not set"]],
  count: [[0, "0"], [7, "7"], [999, "999"], [1000, "1,000"], [12345, "12,345"], [1234567, "1,234,567"], [-3411, "-3,411"]],
};

test("label helpers produce the same text as the Python helpers", () => {
  for (const [v, want] of PY.line) { assert.equal(labels.lineMatchLabel(v), want, `line ${v}`); }
  for (const [v, want] of PY.overlap) { assert.equal(labels.overlapLabel(v), want, `overlap ${v}`); }
  for (const [v, want] of PY.name) { assert.equal(labels.nameSimilarityLabel(v), want, `name ${v}`); }
  for (const [v, want] of PY.threshold) { assert.equal(labels.thresholdLabel(v), want, `threshold ${v}`); }
  for (const [v, want] of PY.count) { assert.equal(labels.countLabel(v), want, `count ${v}`); }
  // The existing similarity helper is the line match format.
  assert.equal(model.percentText(0.1225), "12.2%");
});

test("decimal places match the constants in models.py", () => {
  const py = fs.readFileSync(path.join(ROOT, "..", "src", "diffinite", "models.py"), "utf8");
  assert.match(py, new RegExp(`^LINE_MATCH_DECIMALS = ${labels.LINE_MATCH_DECIMALS}$`, "m"));
  assert.match(py, new RegExp(`^OVERLAP_DECIMALS = ${labels.OVERLAP_DECIMALS}$`, "m"));
});

test("Result Viewer: Jaccard and containment with two decimals, name similarity with one and a percent sign", () => {
  const html = results.buildResultHtml(onePairReport(), model.defaultAnalysisOptions(), "N");
  assert.match(html, /<span class="jlabel ">27\.95%<\/span>/);
  assert.match(html, /<td>8\.24%<\/td>/);
  assert.match(html, /<td>100\.00%<\/td>/);
  assert.match(html, /<td>1,234<\/td>/);
  assert.match(html, /Name similarity: 84\.2%/);
  assert.match(html, /\+1,098/);
  assert.match(html, /−3,411/);
  assert.match(html, /Jaccard threshold: 5%</);
  assert.doesNotMatch(html, /[^\d.]5\.0%/);
});

test("Review screen: threshold in the contract format, Jaccard of an unpaired file with two decimals", () => {
  const report = onePairReport({ results: [] });
  const settings = buildReviewSummary(report).settings.join("\n");
  assert.match(settings, /Jaccard threshold: 5%$/m);
  const html = tree.buildTreeViewerHtml(report, [], "N");
  assert.match(html, /Jaccard 27\.95%/);
});

/* ---------------- metric names, plurals, alignment (visual #10, #18) ---------------- */

test("each metric has one name; no implementation names in the UI", () => {
  const report = onePairReport();
  const treeHtml = tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N");
  const resultHtml = results.buildResultHtml(report, model.defaultAnalysisOptions(), "N");
  for (const [name, html] of [["Tree Viewer", treeHtml], ["Result Viewer", resultHtml]]) {
    assert.doesNotMatch(html, /Content sim|content similarity|\(difflib\)|Name sim\./i, name);
  }
  assert.match(treeHtml, /<th scope="col" class="c-num"[^>]*>Line match<\/th>/);
  assert.match(treeHtml, /<th scope="col" class="c-num"[^>]*>Name similarity<\/th>/);
  assert.match(resultHtml, /<span class="block-sim num">Line match: 15\.0%<\/span>/);
  assert.match(resultHtml, /<th scope="col">File A<\/th><th scope="col">File B<\/th>/);

  const byWord = onePairReport({ comparison_unit: "word" });
  assert.match(tree.buildTreeViewerHtml(byWord, tree.sortForReview(byWord), "N"), />Word match<\/th>/);
  assert.match(results.buildResultHtml(byWord, model.defaultAnalysisOptions(), "N"), /Word match: 15\.0%/);
});

test("counts are written with the singular noun for 1", () => {
  const report = onePairReport();
  const resultHtml = results.buildResultHtml(report, model.defaultAnalysisOptions(), "N");
  assert.match(resultHtml, /<strong>1<\/strong> matched pair<\/span>/);
  assert.match(resultHtml, /<strong>1<\/strong> file only in A<\/span>/);
  assert.doesNotMatch(resultHtml, /1<\/strong> matched pairs/);
  const treeHtml = tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N");
  // The script sets "Generate report (1 file)" for one selected file.
  assert.match(treeHtml, /count === 1 \? ' file\)' : ' files\)'/);
  assert.match(treeHtml, /of 2 A files selected/);
  assert.equal(labels.plural(1, "file"), "1 file");
  assert.equal(labels.plural(2, "match", "matches"), "2 matches");
  assert.equal(labels.plural(1200, "pair"), "1,200 pairs");
  const scope = presets.describeReportOutput(model.defaultAnalysisOptions(), "pdf", { selectedPairs: 1 })[0];
  assert.match(scope, /the 1 file pair selected/);
});

test("the Diff column has a header and the include column is spelled out", () => {
  const report = onePairReport();
  const html = tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N");
  assert.match(html, /<th scope="col" class="c-inc">Include<\/th>/);
  assert.match(html, /<th scope="col" class="c-act">Diff<\/th>/);
  assert.doesNotMatch(html, /Inc\./);
  assert.doesNotMatch(html, /sr-only">Actions/);
});

test("summary facts form one label and value ledger, so rules align when a label wraps", () => {
  const source = src("treeViewer.ts");
  const facts = source.match(/\.facts \{[^}]*\}/)[0];
  assert.doesNotMatch(facts, /auto-fill|repeat\(/);
  assert.match(source, /\.fact \{ display: grid; grid-template-columns: minmax\(0, 1fr\)/);
});

/* ---------------- threshold source and reasons in plain words (copy-review #5) ---------------- */

test("threshold source is shown in plain words, never the internal token", () => {
  assert.equal(labels.thresholdSourceLabel("user"), "Set by user");
  assert.equal(labels.thresholdSourceLabel("normalize-default"), "Default for normalized comparison");
  assert.equal(labels.thresholdSourceLabel("legacy-uncalibrated"), "Default (5%)");
  assert.equal(labels.thresholdSourceLabel("unknown"), "Not recorded");
  assert.equal(labels.thresholdSourceLabel(undefined), "Not recorded");

  for (const [token, words] of [["legacy-uncalibrated", "Default (5%)"], ["normalize-default", "Default for normalized comparison"], ["user", "Set by user"]]) {
    const raw = fixture("report-v2.json");
    raw.metadata = { ...raw.metadata, threshold: 5, threshold_provenance: token, calibration_disclosure: null };
    const report = model.parseReport(raw);
    const html = results.buildResultHtml(report, model.defaultAnalysisOptions(), "N");
    assert.ok(html.includes(`Threshold source: ${words}`), token);
    const settings = buildReviewSummary(report).settings.join("\n");
    assert.ok(settings.includes(`Threshold source: ${words}`), token);
    const view = model.buildReportViewModel(report);
    for (const text of [html, settings, ...view.banners.map((b) => `${b.title} ${b.message}`)]) {
      assert.ok(!text.includes(token === "user" ? "provenance" : token), `${token} leaks`);
    }
  }
});

test("incomplete-analysis reasons are plain sentences, never reason codes", () => {
  const raw = fixture("report-v2.json");
  const codes = ["collection-file-skipped", "collection-file-unhashed", "diff-worker-failure", "diff-pair-error",
    "diff-payload-truncated", "deep-file-or-worker-failure", "deep-index-truncated"];
  raw.analysis_status = { ...raw.analysis_status, state: "incomplete", reasons: codes };
  const banner = model.buildReportViewModel(model.parseReport(raw)).banners.find((b) => b.title === "Incomplete analysis");
  for (const code of codes) { assert.ok(!banner.message.includes(code), code); }
  assert.equal(labels.reasonSentences(codes).length, codes.length);
  assert.doesNotMatch(banner.message, /Recorded reasons/);
  // Every code the analyzer can record has a sentence.
  const pipeline = fs.readFileSync(path.join(ROOT, "..", "src", "diffinite", "pipeline.py"), "utf8");
  const recorded = [...pipeline.matchAll(/mark_incomplete\("([a-z-]+)"\)/g)].map((m) => m[1]);
  assert.ok(recorded.length > 0);
  for (const code of recorded) {
    assert.notEqual(labels.reasonSentences([code])[0], labels.UNKNOWN_REASON_TEXT, `no sentence for ${code}`);
  }
});

test("reason sentences and threshold source words match the Python reports", () => {
  // Join Python's implicitly concatenated string literals.
  const pdfGen = fs.readFileSync(path.join(ROOT, "..", "src", "diffinite", "pdf_gen.py"), "utf8").replace(/"\s*\n\s*"/g, "");
  const block = /^INCOMPLETE_REASON_TEXT[^{]*\{([^]*?)^\}/m.exec(pdfGen)[1];
  const py = {};
  for (const m of block.matchAll(/"([a-z-]+)":\s*\(?\s*"([^"]*)"/g)) { py[m[1]] = m[2]; }
  assert.deepEqual(py, { ...labels.INCOMPLETE_REASON_TEXT });
  assert.ok(pdfGen.includes(`_UNKNOWN_REASON_TEXT = "${labels.UNKNOWN_REASON_TEXT}"`), "unknown-reason text differs");

  const models = fs.readFileSync(path.join(ROOT, "..", "src", "diffinite", "models.py"), "utf8");
  const table = /^THRESHOLD_SOURCE_LABELS[^{]*\{([^]*?)^\}/m.exec(models)[1];
  const words = {};
  for (const m of table.matchAll(/"([a-z-]+)":\s*"([^"]*)"/g)) { words[m[1]] = m[2]; }
  assert.ok(Object.keys(words).length >= 3);
  for (const [token, text] of Object.entries(words)) { assert.equal(labels.thresholdSourceLabel(token), text, token); }
  assert.match(models, /THRESHOLD_SOURCE_LABELS\.get\(provenance or "", "Not recorded"\)/);

  // The State row of the reports' Analysis Status is capitalized.
  assert.equal(labels.analysisStateLabel("complete"), "Complete");
  assert.equal(labels.analysisStateLabel("incomplete"), "Incomplete");
});

/* ---------------- notices from one module (copy-review #10) ---------------- */

test("every notice in notices.ts matches notices.py", () => {
  const py = fs.readFileSync(path.join(ROOT, "..", "src", "diffinite", "notices.py"), "utf8");
  const flat = py.replace(/"\s*\n\s*"/g, "");
  const pyConst = (name) => {
    const m = new RegExp(`^${name} = \\(\\s*"([^]*?)"\\s*\\)`, "m").exec(flat);
    assert.ok(m, `${name} not found in notices.py`);
    return m[1];
  };
  assert.equal(notices.INTEGRITY_NOTICE, pyConst("INTEGRITY_NOTICE"));
  assert.equal(notices.SHORT_CODE_NOTICE, pyConst("SHORT_CODE_NOTICE"));
  // The screen notice drops "in this report" only.
  assert.equal(notices.SCOPE_NOTICE, pyConst("SCOPE_NOTICE").replace(" in this report", ""));
});

test("notice wording is not copied by hand outside notices.ts", () => {
  const phrases = ["independently retained copy", "do not establish copying", "leave little room for variation"];
  for (const file of fs.readdirSync(path.join(ROOT, "src"))) {
    if (!file.endsWith(".ts") || file === "notices.ts") { continue; }
    const text = src(file);
    for (const phrase of phrases) { assert.ok(!text.includes(phrase), `${file} repeats "${phrase}"`); }
  }
  const lines = presets.describeReportOutput(model.defaultAnalysisOptions(), "pdf", { selectedPairs: null });
  assert.equal(lines.filter((l) => l === notices.INTEGRITY_NOTICE).length, 1);
});

/* ---------------- copy (copy-review #11, #15) ---------------- */

test("help and options text: no duplicated default wording, no internal channel term", () => {
  const help = src("helpViewer.ts");
  assert.doesNotMatch(help, /applies the default threshold/);
  assert.doesNotMatch(help + src("optionsPanel.ts"), /selected channel/);
});

test("user-visible text uses US spelling", () => {
  const uk = /\b(cancelled|cancelling|colour|centre|analysed|analyse|normalis|behaviour|licence)\b/i;
  const strings = [];
  for (const file of fs.readdirSync(path.join(ROOT, "src"))) {
    if (!file.endsWith(".ts")) { continue; }
    // String and template literals only; identifiers such as isCancellationRequested are code.
    for (const m of src(file).matchAll(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g)) {
      strings.push([file, m[0]]);
    }
  }
  for (const [file, s] of strings) {
    // A bare token such as "cancelled" (a failure kind) is an identifier, not text.
    if (/^["'`][a-z-]+["'`]$/.test(s)) { continue; }
    const hit = uk.exec(s);
    assert.equal(hit, null, `${file}: ${hit && s.slice(0, 120)}`);
  }
});

test("progress text has no ellipsis", () => {
  for (const file of ["runner.ts", "compareCommand.ts", "resultViewer.ts", "optionsPanel.ts", "treeViewer.ts"]) {
    for (const m of src(file).matchAll(/(?:message|title|textContent)\s*[:=]\s*(`[^`]*`|"[^"]*"|'[^']*')/g)) {
      assert.ok(!/…|\.\.\./.test(m[1]), `${file}: ${m[1]}`);
    }
  }
  assert.equal(pipelineStepMessage("2026-11-10 10:00:00,000 [INFO] Step 2: Collecting files…"), "Step 2: Collecting files");
  assert.equal(pipelineStepMessage("[INFO] Step 3: Matching..."), "Step 3: Matching");
  assert.equal(runner.renderProgressMessage(5, 20), "Rendering: 5 of 20 pairs (25%)");
  assert.equal(runner.renderProgressMessage(0, 1), "Rendering: 0 of 1 pair (0%)");
});

test("Result Viewer text has no ellipsis", () => {
  const raw = fixture("report-v2.json");
  raw.metadata = { ...raw.metadata, ignore_file_sha256: "a".repeat(64), ignore_patterns: ["*.tmp"] };
  const html = results.buildResultHtml(model.parseReport(raw), model.defaultAnalysisOptions(), "N");
  const visible = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, "");
  assert.doesNotMatch(visible, /…|\.\.\./);
  assert.match(visible, /1 rule, SHA-256 prefix aaaaaaaaaaaa/);
});

/* ---------------- layout and theming (visual #6, #7, #8) ---------------- */

test("the navigation bar is docked below the scrolling page and cannot cover diff content", () => {
  const html = results.buildResultHtml(onePairReport(), model.defaultAnalysisOptions(), "N");
  const page = html.indexOf('<div class="page" id="page"');
  const pageEnd = html.indexOf("</main>\n  </div>");
  const nav = html.indexOf('<nav class="dock-nav"');
  assert.ok(page > 0 && pageEnd > page && nav > pageEnd, "nav must follow the scrolling page, outside it");
  const css = html.match(/<style>([\s\S]*?)<\/style>/)[1];
  assert.doesNotMatch(css, /position:\s*fixed/);
  assert.match(css, /\.page \{ flex: 1 1 auto; min-height: 0; overflow-y: auto;/);
  assert.match(css, /\.dock-nav \{ flex: none;/);
  assert.match(css, /html, body \{ height: 100%; overflow: hidden; \}/);
});

test("High Contrast diff: no dashed outlines, placeholder rows keep a cue, no focus-colored block frame", () => {
  const css = src("resultViewer.ts");
  assert.doesNotMatch(css, /outline: 1px dashed/);
  assert.doesNotMatch(css, /\.diff-block\.active \{ border-color/);
  assert.match(css, /\.difftbl td\.ln\.del \{ box-shadow: inset 3px 0 0 var\(--diff-del-border\); \}/);
  assert.match(css, /body\.vscode-high-contrast \.difftbl \.empty,[\s\S]*?var\(--border\) 7px 8px/);
});

test("no synthesized bold or italic for file names and CJK text", () => {
  assert.match(src("webviewUtils.ts"), /font-synthesis: none;/);
  const css = src("resultViewer.ts");
  assert.match(css, /\.block-diff \.code span\[style\] \{ font-style: normal !important; font-weight: normal !important; \}/);
  assert.match(css, /\.difftbl thead th \{[^}]*font-weight: normal;/);
  assert.doesNotMatch(css, /\.jlabel-inconclusive \{[^}]*italic/);
});
