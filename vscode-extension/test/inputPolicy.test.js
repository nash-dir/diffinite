/**
 * Collection policy in the extension: --sensitive-files and --include are
 * always sent as chosen, the report's exclusion list is read, and the review
 * summary states how many inputs were left out.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const test = require("node:test");

const originalLoad = Module._load;
Module._load = function load(request, ...rest) {
  if (request === "vscode") { return {}; }
  return originalLoad.call(this, request, ...rest);
};

const model = require("../out/analysisModel.js");
const { buildReviewSummary } = require("../out/reviewSummary.js");
const { classifyFailure } = require("../out/failureClassifier.js");

const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
const source = (name) => fs.readFileSync(path.join(__dirname, "..", "src", name), "utf8");

test("sensitive files are excluded by default and the choice is always sent", () => {
  const opts = model.defaultAnalysisOptions();
  assert.equal(opts.sensitiveFiles, "exclude");
  const args = model.buildCoreArgs(opts);
  assert.deepEqual(args.slice(args.indexOf("--sensitive-files"), args.indexOf("--sensitive-files") + 2),
    ["--sensitive-files", "exclude"]);
  const included = model.buildCoreArgs({ ...opts, sensitiveFiles: "include" });
  assert.ok(included.includes("include"));
});

test("include patterns are split on commas and sent as --include=PATTERN", () => {
  assert.deepEqual(model.parseIncludePatterns(" *.java, src/** ,,"), ["*.java", "src/**"]);
  assert.deepEqual(model.parseIncludePatterns(""), []);
  const args = model.buildCoreArgs({ ...model.defaultAnalysisOptions(), includePatterns: "*.java, -odd*" });
  assert.ok(args.includes("--include=*.java"));
  assert.ok(args.includes("--include=-odd*"));
  assert.ok(!model.buildCoreArgs(model.defaultAnalysisOptions()).some((a) => a.startsWith("--include")));
});

test("an unknown sensitive-files value is refused before Python runs", () => {
  const opts = { ...model.defaultAnalysisOptions(), sensitiveFiles: "maybe" };
  assert.match(model.validateRunOptions(opts), /Sensitive files/);
  assert.equal(model.validateRunOptions(model.defaultAnalysisOptions()), null);
});

test("the review summary counts excluded inputs and names the sensitive policy", () => {
  const raw = fixture("report-v2.json");
  raw.metadata.sensitive_files = "exclude";
  raw.metadata.include_patterns = ["src/**"];
  raw.analysis_status.exclusion = {
    excluded_count: 2,
    excluded: [
      { side: "A", path: ".env", kind: "file", source: "sensitive-preset", rule: ".env" },
      { side: "B", path: "docs/a.md", kind: "file", source: "include-filter", rule: "no --include pattern matches" },
    ],
  };
  const report = model.parseLiveReport(raw);
  const summary = buildReviewSummary(report);
  const excluded = summary.facts.find((f) => f.label === "Inputs excluded by policy");
  assert.equal(excluded.value, "2");
  assert.equal(excluded.attention, true);
  const sensitive = summary.facts.find((f) => /^Sensitive files/.test(f.label));
  assert.equal(sensitive.value, "Excluded (1 found)");
  assert.ok(summary.settings.includes("Include filter: src/**"));
});

test("a report without the exclusion block shows the count as unknown", () => {
  const raw = fixture("report-v2.json");
  delete raw.analysis_status.exclusion;
  const fact = buildReviewSummary(model.parseLiveReport(raw)).facts.find((f) => f.label === "Inputs excluded by policy");
  assert.equal(fact.value, "unknown");
});

test("the --sensitive-files error refusal is classified", () => {
  const failure = classifyFailure(new Error(
    "RuntimeError: Sensitive files found (2); nothing was written: A:.env, B:.env. Use --sensitive-files exclude",
  ));
  assert.equal(failure.kind, "sensitive-found");
});

test("the options panel saves and restores both controls", () => {
  const panel = source("optionsPanel.ts");
  assert.match(panel, /id="sensitiveFiles"/);
  assert.match(panel, /sensitiveFiles: document\.getElementById\('sensitiveFiles'\)\.value/);
  assert.match(panel, /includePatterns: document\.getElementById\('includePatterns'\)\.value/);
  assert.match(panel, /document\.getElementById\('sensitiveFiles'\)\.value = o\.sensitiveFiles \|\| 'exclude'/);
});

test("a malformed or inconsistent exclusion block is rejected in a live report", () => {
  const bad = fixture("report-v2.json");
  bad.analysis_status.exclusion = { excluded_count: 5, excluded: "oops" };
  assert.throws(() => model.parseLiveReport(bad), /analysis_status\.exclusion\.excluded/);
  const mismatch = fixture("report-v2.json");
  mismatch.analysis_status.exclusion = {
    excluded_count: 2,
    excluded: [{ side: "A", path: ".env", kind: "file", source: "sensitive-preset", rule: ".env" }],
  };
  assert.throws(() => model.parseLiveReport(mismatch), /excluded_count/);
});

test("the Results panel states excluded inputs and the collection policy", () => {
  const { buildResultHtml } = require("../out/resultViewer.js");
  const raw = fixture("report-v2.json");
  raw.metadata.sensitive_files = "exclude";
  raw.metadata.include_patterns = ["*.java"];
  raw.analysis_status.exclusion = {
    excluded_count: 1,
    excluded: [{ side: "A", path: ".env", kind: "file", source: "sensitive-preset", rule: ".env" }],
  };
  const html = buildResultHtml(model.parseLiveReport(raw), model.defaultAnalysisOptions(), "N");
  assert.match(html, /Inputs excluded by policy: 1/);
  assert.match(html, /Sensitive files: excluded/);
  assert.match(html, /Include filter: \*\.java/);
});
