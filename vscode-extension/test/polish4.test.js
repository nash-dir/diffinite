/**
 * Fourth polish pass: the Results view draws diffs as the reports do.
 *
 * - Changed whitespace ("ws" spans) is a light tint, never struck or underlined.
 * - A wrapped code line continues from the line's own indentation plus two
 *   characters, with the constants of pdf_gen._hanging_indent_style.
 * - When Deep Compare ran and reported 0 pairs, one sentence says so; when it
 *   did not run, nothing is said.
 * - Word-level changed lines (.chg) have their own neutral tint, not the
 *   "added" tint, and a bar in High Contrast.
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

const model = require("../out/analysisModel.js");
const results = require("../out/resultViewer.js");
const { THEME_CSS } = require("../out/webviewUtils.js");

const ROOT = path.join(__dirname, "..");
const PY_SRC = path.join(ROOT, "..", "src", "diffinite");
const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));

/** A Deep Compare report; `reported` is analysis_status.deep.reported_pair_count. */
function report({ reported, matches = [], htmlDiff = "<table class=\"difftbl\"></table>" } = {}) {
  const raw = fixture("report-v2.json");
  raw.metadata = { ...raw.metadata, exec_mode: "deep", threshold: 5 };
  raw.results = [{
    file_a: "A.java", file_b: "B.java", name_similarity: 100, ratio: 0.5, additions: 1, deletions: 1,
    html_diff: htmlDiff, error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
  }];
  raw.deep_results = matches.length ? [{ file_a: "A.java", fingerprint_count_a: 40, matches }] : [];
  raw.analysis_status = { ...raw.analysis_status, deep: { ...(raw.analysis_status || {}).deep } };
  if (reported === undefined) { delete raw.analysis_status.deep.reported_pair_count; }
  else { raw.analysis_status.deep.reported_pair_count = reported; }
  return model.parseReport(raw);
}
const resultHtml = (r) => results.buildResultHtml(r, model.defaultAnalysisOptions(), "N");
const css = (html) => (/<style>([^]*?)<\/style>/.exec(html) || ["", ""])[1];
const count = (text, part) => text.split(part).length - 1;

/* ---------- #2: changed whitespace ---------- */

test("differ.py marks whitespace-only changes with the ws class", () => {
  const differ = fs.readFileSync(path.join(PY_SRC, "differ.py"), "utf8");
  assert.match(differ, /_span\("word-del ws"/);
  assert.match(differ, /_span\("word-add ws"/);
});

test("ws spans are a light tint with no strike or underline", () => {
  const style = css(resultHtml(report()));
  const rule = /\.word-del\.ws, \.word-add\.ws \{([^}]*)\}/.exec(style);
  assert.ok(rule, "no rule for .ws spans");
  assert.match(rule[1], /text-decoration: none/);
  assert.match(rule[1], /background: var\(--diff-ws-text\)/);
  assert.match(THEME_CSS, /--diff-ws-text: rgba\(128,128,128,\.25\)/);
  // The ws rule comes after the word-del/word-add rules, so it wins.
  assert.ok(style.indexOf(".word-del.ws") > style.indexOf(".word-add {"));
});

/* ---------- #3: hanging indent from the line's own indentation ---------- */

test("hanging-indent constants match pdf_gen.py", () => {
  const py = fs.readFileSync(path.join(PY_SRC, "pdf_gen.py"), "utf8");
  const ts = fs.readFileSync(path.join(ROOT, "src", "resultViewer.ts"), "utf8");
  for (const [pyName, tsName] of [["_HANG_EXTRA_CHARS", "HANG_EXTRA_CHARS"], ["_HANG_MAX_INDENT", "HANG_MAX_INDENT"], ["_TAB_SIZE", "TAB_SIZE"]]) {
    const p = new RegExp(`^${pyName} = (\\d+)$`, "m").exec(py);
    const t = new RegExp(`^const ${tsName} = (\\d+);$`, "m").exec(ts);
    assert.ok(p && t, pyName);
    assert.equal(t[1], p[1], pyName);
  }
});

test("leadingColumns counts spaces, NBSP entities and tabs to 8-column stops", () => {
  assert.equal(results.leadingColumns("foo"), 0);
  assert.equal(results.leadingColumns("    foo"), 4);
  assert.equal(results.leadingColumns("<span class=\"w\">  </span>  x"), 4);
  assert.equal(results.leadingColumns("&nbsp;&#160; x"), 3);
  assert.equal(results.leadingColumns("\tx"), 8);
  assert.equal(results.leadingColumns("  \tx"), 8);
  assert.equal(results.leadingColumns("&#9;&#x9;x"), 16);
  assert.equal(results.leadingColumns("&lt;x"), 0);
  assert.equal(results.leadingColumns("   "), 3);
});

test("each indented code line gets its own hanging indent in ch", () => {
  const row = (inner) => `<td class="code add"><pre>${inner}</pre></td>`;
  const out = results.hangingIndentDiff(row("        throw x;") + row("plain();") + row("\t\t\t\t\t\tdeep();"));
  assert.match(out, /<pre style="padding-left: 10ch; text-indent: -10ch;">        throw x;<\/pre>/);
  assert.match(out, /<pre>plain\(\);<\/pre>/);
  // Indentation beyond 32 columns is not followed further.
  assert.match(out, /<pre style="padding-left: 34ch; text-indent: -34ch;">\t{6}deep\(\);<\/pre>/);
});

test("the Results view applies the hanging indent to the diff table", () => {
  const html = resultHtml(report({ htmlDiff: "<table class=\"difftbl\"><tr><td class=\"code chg\"><pre>    x();</pre></td></tr></table>" }));
  assert.match(html, /<pre style="padding-left: 6ch; text-indent: -6ch;">    x\(\);<\/pre>/);
  assert.match(css(html), /\.difftbl td\.code pre \{ padding-left: 2ch; text-indent: -2ch; \}/);
  assert.match(css(html), /\.difftbl \.code pre \{[^}]*tab-size: 8; \}/);
});

/* ---------- #4: Deep Compare reported 0 pairs ---------- */

test("reported_pair_count is read from analysis_status.deep", () => {
  assert.equal(report({ reported: 0 }).analysis_status.deep.reported_pair_count, 0);
  assert.equal(report({ reported: 3 }).analysis_status.deep.reported_pair_count, 3);
  assert.equal(report({ reported: null }).analysis_status.deep.reported_pair_count, null);
  assert.equal(report().analysis_status.deep.reported_pair_count, null);
});

test("one sentence states that no pair reached the threshold when Deep Compare reported 0 pairs", () => {
  const html = resultHtml(report({ reported: 0 }));
  assert.equal(results.NO_DEEP_PAIR_SENTENCE, "No file pair reached the Jaccard threshold.");
  assert.equal(count(html, results.NO_DEEP_PAIR_SENTENCE), 1);
  assert.match(html, /<h2>Deep Compare: Cross-Match Results<\/h2>\s*<p class="deep-empty">No file pair reached the Jaccard threshold\.<\/p>/);
  assert.doesNotMatch(html, /class="deep-table"/);
});

test("nothing is said about Deep Compare when it did not run", () => {
  for (const r of [report({ reported: null }), report()]) {
    const html = resultHtml(r);
    assert.equal(count(html, results.NO_DEEP_PAIR_SENTENCE), 0);
    assert.doesNotMatch(html, /id="block-deep"/);
  }
});

test("a reported pair shows the table and not the empty sentence", () => {
  const match = { file_b: "B.java", shared_hashes: 10, jaccard: 0.5, containment_a_in_b: 0.5, containment_b_in_a: 0.5, inconclusive: false };
  const html = resultHtml(report({ reported: 1, matches: [match] }));
  assert.match(html, /class="deep-table"/);
  assert.equal(count(html, results.NO_DEEP_PAIR_SENTENCE), 0);
});

/* ---------- #5: changed-line tint ---------- */

test("word-level changed lines use their own tint, not the added tint", () => {
  const style = css(resultHtml(report()));
  assert.match(style, /\.difftbl \.chg \{ background: var\(--diff-chg-line\); \}/);
  assert.doesNotMatch(style, /\.chg \{ background: var\(--diff-add-line\)/);
  assert.match(THEME_CSS, /--diff-chg-line: rgba\(190,160,60,\.16\)/);
});

test("High Contrast marks changed lines with a bar at the line number", () => {
  const style = css(resultHtml(report()));
  for (const theme of ["vscode-high-contrast", "vscode-high-contrast-light"]) {
    assert.ok(style.includes(`body.${theme} .difftbl td.ln.chg`), theme);
  }
  assert.match(style, /td\.ln\.chg \{ box-shadow: inset 3px 0 0 var\(--fg\); \}/);
});
