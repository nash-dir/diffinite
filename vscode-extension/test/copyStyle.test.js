/**
 * House style for the extension UI: no decorative typography, English only,
 * and the scope and short-code notices on the review and result screens.
 *
 * Every webview is built through its real builder (Tree Viewer, Result
 * Viewer, Options panel, Help) from ASCII fixtures, so any forbidden
 * character found here comes from the extension's own text.
 */
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");

let capturedHtml = [];
const fakePanel = () => {
  const panel = {
    webview: { html: "", onDidReceiveMessage: () => ({ dispose() {} }), postMessage: async () => true },
    onDidDispose: () => ({ dispose() {} }),
    onDidChangeViewState: () => ({ dispose() {} }),
    reveal: () => undefined,
    dispose: () => undefined,
  };
  capturedHtml.push(panel);
  return panel;
};
const vscodeStub = {
  Uri: { file: (fsPath) => ({ fsPath }) },
  ViewColumn: { Active: -1, One: 1, Beside: -2 },
  ProgressLocation: { Notification: 15 },
  ConfigurationTarget: { Global: 1 },
  workspace: { workspaceFolders: undefined, getConfiguration: () => ({ get: (_k, d) => d, update: async () => undefined }) },
  env: { openExternal: async () => true },
  window: {
    createWebviewPanel: fakePanel,
    showWarningMessage: async () => undefined,
    showInformationMessage: async () => undefined,
    showErrorMessage: async () => undefined,
  },
  commands: { executeCommand: async () => undefined },
};
const originalLoad = Module._load;
Module._load = function load(request, ...rest) {
  if (request === "vscode") { return vscodeStub; }
  return originalLoad.call(this, request, ...rest);
};

const model = require("../out/analysisModel.js");
const results = require("../out/resultViewer.js");
const tree = require("../out/treeViewer.js");
const options = require("../out/optionsPanel.js");
const help = require("../out/helpViewer.js");
const notices = require("../out/notices.js");
const { buildReviewSummary } = require("../out/reviewSummary.js");
const presets = require("../out/reportPresets.js");

const FORBIDDEN = {
  "·": "middle dot",
  "—": "em dash",
  "–": "en dash",
  "⚠": "warning sign",
  "ℹ": "information source",
  "✓": "check mark",
  "✗": "ballot X",
  "→": "right arrow",
  "↔": "left-right arrow",
  "▶": "play triangle",
  "⟳": "clockwise arrow",
};
const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힣]/;
// HTML entities for the same characters.
const FORBIDDEN_ENTITIES = /&(mdash|ndash|middot|harr|rarr|larr);/;

function assertHouseStyle(name, text) {
  for (const [ch, label] of Object.entries(FORBIDDEN)) {
    assert.ok(!text.includes(ch), `${name} contains a ${label} (U+${ch.codePointAt(0).toString(16).toUpperCase()})`);
  }
  const hangul = HANGUL.exec(text);
  assert.equal(hangul, null, `${name} contains Hangul near ${hangul ? JSON.stringify(text.slice(Math.max(0, hangul.index - 40), hangul.index + 40)) : ""}`);
  const entity = FORBIDDEN_ENTITIES.exec(text);
  assert.equal(entity, null, `${name} contains the entity ${entity && entity[0]}`);
}

const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));

/** A report that exercises every banner: incomplete, inconclusive, excluded, truncated. */
function richReport() {
  const raw = fixture("report-v2.json");
  raw.results = [
    ...raw.results,
    {
      file_a: "big.py", file_b: "big.py", name_similarity: 100, ratio: 0.5, additions: 1, deletions: 1,
      html_diff: "", error: null, binary: false,
      truncation: { truncated: true, reason: "max-diff-html-size", original_bytes: 10, omitted_bytes: 10 },
    },
    {
      file_a: "blob.bin", file_b: "blob.bin", name_similarity: 100, ratio: 1, additions: 0, deletions: 0,
      html_diff: "", error: null, binary: true, hash_match: true,
      truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
    },
    {
      file_a: "bad.py", file_b: "bad.py", name_similarity: 100, ratio: 0, additions: 0, deletions: 0,
      html_diff: "", error: "read failed", binary: false,
      truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
    },
  ];
  raw.deep_results = [{
    file_a: "a.py", fingerprint_count_a: 4,
    matches: [
      { file_b: "b.py", shared_hashes: 3, jaccard: 0.75, containment_a_in_b: 0.8, containment_b_in_a: 0.9, inconclusive: false },
      { file_b: "c.py", shared_hashes: 1, jaccard: 0.5, containment_a_in_b: null, containment_b_in_a: null, inconclusive: true },
    ],
  }];
  raw.analysis_status = {
    ...raw.analysis_status,
    state: "incomplete",
    reasons: ["worker-failure"],
    diff: {
      ...(raw.analysis_status && raw.analysis_status.diff),
      failed_pairs: [{ file_a: "x.py", file_b: "x.py", reason: "boom" }],
      excluded_pairs: [{ file_a: "asset.dat", file_b: "asset.dat", reason: "binary-excluded" }],
    },
  };
  return model.parseReport(raw);
}

function views() {
  const report = richReport();
  const opts = model.defaultAnalysisOptions();
  return {
    report,
    treeHtml: tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N"),
    resultHtml: results.buildResultHtml(report, opts, "N", ["The selection changed."]),
  };
}

test("review and result webviews use house style", () => {
  const { report, treeHtml, resultHtml } = views();
  assertHouseStyle("Tree Viewer", treeHtml);
  assertHouseStyle("Result Viewer", resultHtml);
  const view = model.buildReportViewModel(report);
  for (const banner of view.banners) {
    assertHouseStyle(`banner ${banner.title}`, `${banner.title} ${banner.message}`);
  }
  for (const row of view.deepRows) { assertHouseStyle("Deep Compare label", row.label); }
  const summary = buildReviewSummary(report);
  for (const fact of summary.facts) { assertHouseStyle(`fact ${fact.label}`, `${fact.label} ${fact.value}`); }
  for (const setting of summary.settings) { assertHouseStyle("setting", setting); }
});

test("review and result webviews state the scope and short-code notices", () => {
  const { treeHtml, resultHtml } = views();
  for (const [name, html] of [["Tree Viewer", treeHtml], ["Result Viewer", resultHtml]]) {
    assert.ok(html.includes(notices.SCOPE_NOTICE), `${name} lacks the scope notice`);
    assert.ok(html.includes(notices.SHORT_CODE_NOTICE), `${name} lacks the short-code notice`);
  }
  assert.match(notices.SCOPE_NOTICE, /do not establish copying, derivation or infringement/);
  assert.match(notices.SHORT_CODE_NOTICE, /written independently/);
});

test("notices match the Python report wording", () => {
  const py = fs.readFileSync(path.join(__dirname, "..", "..", "src", "diffinite", "notices.py"), "utf8");
  const flat = py.replace(/"\s*\n\s*"/g, "");
  assert.ok(flat.includes(notices.SHORT_CODE_NOTICE), "short-code notice differs from notices.py");
  assert.ok(flat.includes(notices.SCOPE_NOTICE.replace("Similarity figures measure", "Similarity figures in this report measure")),
    "scope notice differs from notices.py");
});

test("options panel and help use house style", () => {
  capturedHtml = [];
  const context = {
    globalState: { get: () => undefined, update: async () => undefined },
    subscriptions: [],
  };
  options.showOptionsPanel(context, async () => undefined);
  help.showHelp(context);
  assert.equal(capturedHtml.length, 2);
  assertHouseStyle("Options panel", capturedHtml[0].webview.html);
  assertHouseStyle("Help", capturedHtml[1].webview.html);
  assert.ok(capturedHtml[1].webview.html.includes(notices.SHORT_CODE_NOTICE), "Help lacks the short-code notice");
});

test("export descriptions and package.json strings use house style", () => {
  const opts = { ...model.defaultAnalysisOptions(), batesNumber: true, batesPrefix: "CASE-", batesStart: 7 };
  for (const preset of presets.REPORT_PRESETS) {
    assertHouseStyle(`preset ${preset.id}`, `${preset.label} ${preset.audience}`);
    for (const format of ["pdf", "html", "md"]) {
      for (const line of presets.describeReportOutput(presets.applyReportPreset(opts, preset.id), format, { selectedPairs: 3 })) {
        assertHouseStyle(`${preset.id}/${format}`, line);
      }
    }
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
  const strings = [pkg.displayName, pkg.description];
  for (const cmd of pkg.contributes.commands) { strings.push(cmd.title); }
  const walk = (node) => {
    if (!node || typeof node !== "object") { return; }
    for (const [key, value] of Object.entries(node)) {
      if ((key === "description" || key === "markdownDescription") && typeof value === "string") { strings.push(value); }
      else { walk(value); }
    }
  };
  walk(pkg.contributes.configuration);
  for (const s of strings) { assertHouseStyle("package.json", s); }
});
