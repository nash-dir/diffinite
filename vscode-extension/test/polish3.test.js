/**
 * Third polish pass: the extension says what the reports say.
 *
 * - The export summary states the SHA-256 table for Markdown like any format.
 * - The Deep Compare column is "Shared hashes", as in the reports.
 * - Under --by-word the +/- counts are described as words, not lines.
 * - "Candidate" is not shown; the inconclusive notice (notices.ts, mirroring
 *   notices.INCONCLUSIVE_NOTICE) is shown once when an inconclusive match is.
 * - Review labels for Analysis Status figures are the report's row labels
 *   (notices.ts STATUS_LABELS, compared with notices.analysis_status_rows).
 * - Deleted counts use U+2212 MINUS SIGN; the state reads "Complete".
 * - Wrapped code lines in the Result Viewer have a hanging indent.
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

const ROOT = path.join(__dirname, "..");
const PY_SRC = path.join(ROOT, "..", "src", "diffinite");
const src = (name) => fs.readFileSync(path.join(ROOT, "src", name), "utf8");
const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
const MINUS = "−";

/** One pair, one Deep Compare match; `inconclusive` and `unit` vary. */
function report({ inconclusive = false, unit = "line" } = {}) {
  const raw = fixture("report-v2.json");
  raw.metadata = { ...raw.metadata, threshold: 5, threshold_provenance: "legacy-uncalibrated", normalize: false, calibration_disclosure: null };
  raw.comparison_unit = unit;
  raw.results = [{
    file_a: "Ledger.java", file_b: "Ledger.cs", name_similarity: 84.2, ratio: 0.15, additions: 151, deletions: 1138,
    html_diff: "<table class=\"difftbl\"></table>", error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
  }];
  raw.deep_results = [{
    file_a: "Ledger.java", fingerprint_count_a: 40,
    matches: [{ file_b: "Ledger.cs", shared_hashes: 1234, jaccard: 0.2795, containment_a_in_b: 0.08, containment_b_in_a: 1, inconclusive }],
  }];
  raw.summary = { ...raw.summary, matched_pairs: 1, unmatched_a_count: 0, unmatched_b_count: 0 };
  raw.unmatched_a = [];
  raw.unmatched_b = [];
  return model.parseReport(raw);
}
const resultHtml = (r) => results.buildResultHtml(r, model.defaultAnalysisOptions(), "N");
const treeHtml = (r) => tree.buildTreeViewerHtml(r, tree.sortForReview(r), "N");
/** Visible text: markup, styles and scripts removed. */
const visible = (html) => html.replace(/<style>[^]*?<\/style>|<script[^]*?<\/script>/g, " ").replace(/<[^>]+>/g, " ");
const count = (text, part) => text.split(part).length - 1;

/* ---------- copy #3: SHA-256 table in the Markdown export summary ---------- */

test("export summary states the SHA-256 table for Markdown as for PDF and HTML", () => {
  for (const hash of [true, false]) {
    const options = { ...model.defaultAnalysisOptions(), hash };
    for (const format of ["pdf", "html", "md"]) {
      const lines = presets.describeReportOutput(options, format, { selectedPairs: null });
      assert.ok(lines.includes(`SHA-256 table of input files: ${hash ? "included" : "not included"}.`), `${format} hash=${hash}`);
      assert.ok(!lines.join("\n").includes("SHA-256 table of input files: not applicable"));
    }
  }
});

/* ---------- copy #5: "Shared hashes" ---------- */

test("the Deep Compare column is named Shared hashes", () => {
  const html = resultHtml(report());
  assert.match(html, /<th scope="col"[^>]*>Shared hashes<\/th>/);
  assert.doesNotMatch(html, />Shared<\/th>/);
  assert.doesNotMatch(visible(html) + html, /[Ss]hared fingerprints/);
});

/* ---------- copy #6: unit of the +/- counts ---------- */

test("+/- counts are described in words under --by-word and in lines otherwise", () => {
  const word = resultHtml(report({ unit: "word" }));
  assert.match(word, /title="Words only in B">\+151</);
  assert.match(word, new RegExp(`title="Words only in A">${MINUS}1,138<`));
  assert.doesNotMatch(word, /Lines only in/);
  const line = resultHtml(report());
  assert.match(line, /title="Lines only in B"/);
  assert.match(treeHtml(report({ unit: "word" })), new RegExp(`title="\\+: words only in B\\. ${MINUS}: words only in A\\."`));
  assert.match(treeHtml(report()), /title="\+: lines only in B\./);
});

/* ---------- copy #7: no "candidate"; the inconclusive notice ---------- */

test("INCONCLUSIVE_NOTICE and its token floor match notices.py and calibration.py", () => {
  const cal = fs.readFileSync(path.join(PY_SRC, "calibration.py"), "utf8");
  const floor = /^INCONCLUSIVE_TOKEN_FLOOR: int = (\d+)$/m.exec(cal);
  assert.ok(floor, "INCONCLUSIVE_TOKEN_FLOOR not found in calibration.py");
  assert.equal(notices.INCONCLUSIVE_TOKEN_FLOOR, Number(floor[1]));
  const py = fs.readFileSync(path.join(PY_SRC, "notices.py"), "utf8").replace(/"\s*\n\s*f?"/g, "");
  const m = /^INCONCLUSIVE_NOTICE = \(\s*f?"([^]*?)"\s*\)/m.exec(py);
  assert.ok(m, "INCONCLUSIVE_NOTICE not found in notices.py");
  assert.equal(notices.INCONCLUSIVE_NOTICE, m[1].replace("{INCONCLUSIVE_TOKEN_FLOOR}", floor[1]));
});

test("the inconclusive notice appears once when an inconclusive match is shown, never otherwise", () => {
  const on = report({ inconclusive: true });
  const off = report({ inconclusive: false });
  for (const build of [resultHtml, treeHtml]) {
    assert.equal(count(build(on), notices.INCONCLUSIVE_NOTICE), 1);
    assert.equal(count(build(off), notices.INCONCLUSIVE_NOTICE), 0);
  }
  assert.match(resultHtml(on), /27\.95% \(inconclusive\)/);
});

test("the screens never show the undefined term candidate", () => {
  for (const r of [report({ inconclusive: true }), report()]) {
    for (const html of [resultHtml(r), treeHtml(r)]) {
      assert.doesNotMatch(visible(html), /candidate/i);
    }
    for (const fact of buildReviewSummary(r).facts) { assert.doesNotMatch(fact.label, /candidate/i); }
  }
  const facts = buildReviewSummary(report({ inconclusive: true })).facts;
  assert.equal(facts.find((f) => f.label === "Deep Compare pairs at or above the threshold").value, "1");
  assert.equal(facts.find((f) => f.label === "Deep Compare pairs marked inconclusive").value, "1");
});

/* ---------- copy #8: Analysis Status labels ---------- */

test("STATUS_LABELS are exactly the labels of notices.analysis_status_rows", () => {
  const py = fs.readFileSync(path.join(PY_SRC, "notices.py"), "utf8");
  const start = py.indexOf("def analysis_status_rows(");
  const end = py.indexOf("\ndef ", start + 1);
  assert.ok(start >= 0 && end > start, "analysis_status_rows not found in notices.py");
  const body = py.slice(start, end);
  const pyLabels = new Set([...body.matchAll(/\(\s*"([^"\n]+)",/g)].map((m) => m[1]));
  assert.deepEqual(new Set(Object.values(notices.STATUS_LABELS)), pyLabels);
});

test("review facts that are Analysis Status figures use the report's labels", () => {
  const raw = fixture("report-v2.json");
  const facts = buildReviewSummary(model.parseReport(raw)).facts.map((f) => f.label);
  for (const label of [notices.STATUS_LABELS.state, notices.STATUS_LABELS.pairsFailed, notices.STATUS_LABELS.inputsNotRead]) {
    assert.ok(facts.includes(label), `missing ${label}`);
  }
  const deep = buildReviewSummary(report()).facts.map((f) => f.label);
  assert.ok(deep.includes(notices.STATUS_LABELS.deepSkipped));
  assert.ok(deep.includes(notices.STATUS_LABELS.deepBelowKgram));
  const retired = ["Analysis state", "Pairs with errors", "Inputs skipped while collecting", "Inputs skipped by Deep Compare",
    "Inputs below k-gram size", "Matched pairs left out by the binary-file policy", "omitted by the selection (A / B)"];
  const text = src("reviewSummary.ts");
  for (const old of retired) { assert.ok(!text.includes(old), `reviewSummary.ts still says "${old}"`); }
});

test("the state reads Complete or Incomplete, as in the reports", () => {
  assert.equal(labels.analysisStateLabel("complete"), "Complete");
  assert.equal(labels.analysisStateLabel("incomplete"), "Incomplete");
  // models.ANALYSIS_STATE_LABELS holds the same words.
  const models = fs.readFileSync(path.join(PY_SRC, "models.py"), "utf8");
  assert.match(models, /"complete": "Complete"/);
  assert.match(models, /"incomplete": "Incomplete"/);
  assert.match(models, /ANALYSIS_STATE_LABELS\.get\(state or "", "Unknown"\)/);
  assert.equal(labels.analysisStateLabel(undefined), "Unknown");
  const fact = buildReviewSummary(report()).facts.find((f) => f.label === "State");
  assert.match(fact.value, /^(Complete|Incomplete|Unknown)$/);
});

/* ---------- copy #9: U+2212 minus ---------- */

test("deleted counts use U+2212, never a hyphen", () => {
  assert.equal(labels.deletedCountLabel(1138), `${MINUS}1,138`);
  assert.equal(labels.addedCountLabel(1098), "+1,098");
  for (const html of [resultHtml(report()), treeHtml(report())]) {
    assert.ok(html.includes(`${MINUS}1,138`));
    assert.doesNotMatch(visible(html), /(^|\s)-1,138/);
  }
});

/* ---------- visual #6 and #10: hanging indent, settings line ---------- */

test("wrapped code lines in the Result Viewer have a hanging indent", () => {
  assert.match(resultHtml(report()), /\.difftbl td\.code pre \{ padding-left: 2ch; text-indent: -2ch; \}/);
});

test("every label in the Results settings line has the same dim style", () => {
  const html = resultHtml(report());
  const bar = /<div class="meta-bar">([^]*?)<\/div>/.exec(html);
  assert.ok(bar);
  const spans = [...bar[1].matchAll(/<span([^>]*)>/g)].map((m) => m[1].replace(/\s*title="[^"]*"/, ""));
  assert.ok(spans.length >= 7);
  assert.ok(spans.every((attrs) => attrs === ""), "a settings label carries its own class or style");
  assert.match(bar[1], /<span>Comments \(line diff \/ Deep Compare\):/);
});
