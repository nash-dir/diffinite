/**
 * Regressions for the 2026-11-10 code audit (extension group).
 * Finding numbers refer to tmp/code-audit-index.txt.
 */
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const Module = require("node:module");
const os = require("node:os");
const path = require("node:path");
const { PassThrough } = require("node:stream");
const test = require("node:test");

// ---------------------------------------------------------------------------
// A minimal "vscode" stub. Webview builders never touch it; the Results-panel
// test below drives showResults() through it.
// ---------------------------------------------------------------------------
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

// resultViewer imports runExport; replace the runner so the panel test does
// not spawn Python. Nothing else in this file needs the real runner.
const exportCalls = [];
const runnerPath = require.resolve("../out/runner.js");
require.cache[runnerPath] = {
  id: runnerPath, filename: runnerPath, loaded: true,
  exports: { runExport: async (...args) => { exportCalls.push(args); } },
};

const model = require("../out/analysisModel.js");
const { createExportTransaction } = require("../out/exportTransaction.js");
const freeze = require("../out/inputFreeze.js");
const tree = require("../out/treeViewer.js");
const results = require("../out/resultViewer.js");
const { buildReviewSummary } = require("../out/reviewSummary.js");
const { classifyFailure } = require("../out/failureClassifier.js");
const { ActiveProcessRegistry, waitForProcessClose } = require("../out/processRegistry.js");
const { LineBuffer, pipelineStepMessage } = require("../out/lineBuffer.js");
const scanner = require("../out/dirScanner.js");
const ignoreList = require("../out/ignoreList.js");
const presets = require("../out/reportPresets.js");

const root = path.join(__dirname, "..");
const source = (rel) => fs.readFileSync(path.join(root, "src", rel), "utf8");
const fixture = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");

function tempRoot(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "diffinite-audit2-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function writeFile(base, relative, data) {
  const destination = path.join(base, ...relative.split("/"));
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination, data);
  return destination;
}

function manifestFor(artifacts) {
  return JSON.stringify({
    reports: Object.entries(artifacts).map(([relative, data]) => ({
      path: relative, sha256: sha256(data), size_bytes: Buffer.byteLength(data),
    })),
  });
}

function makeDirs(base) {
  const dirs = { dirA: path.join(base, "A"), dirB: path.join(base, "B"), outputDir: path.join(base, "out") };
  Object.values(dirs).forEach((dir) => fs.mkdirSync(dir));
  return dirs;
}

function stageSplitPdf(transaction, artifacts) {
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeFile(transaction.stagingDirectory, "manifest.sha256.json", manifestFor(artifacts));
}

function stageMergedPdf(transaction, marker = "new") {
  const pdf = `%PDF-${marker}`;
  const digest = sha256(pdf);
  const artifacts = {
    "report.pdf": pdf,
    "report.csv": `csv-${marker}`,
    "report.pdf.sha256": `${digest}  report.pdf\n`,
    "report.pdf.sig": `SHA-256: ${digest}\nReport: report.pdf\n`,
  };
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeFile(transaction.stagingDirectory, "manifest.sha256.json", manifestFor(artifacts));
}

function listFiles(dir, base = dir) {
  if (!fs.existsSync(dir)) { return []; }
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(dir, entry.name);
    return entry.isDirectory() ? listFiles(absolute, base)
      : [path.relative(base, absolute).split(path.sep).join("/")];
  }).sort();
}

function result(overrides = {}) {
  return {
    file_a: "a.py", file_b: "b.py", name_similarity: 100, ratio: 0.5,
    additions: 1, deletions: 1, html_diff: "", error: null, binary: false,
    truncation: { truncated: false, reason: null, original_bytes: null, omitted_bytes: null },
    ...overrides,
  };
}

/* ------------------------------------------------------------------ */
/* #7 Deep Compare skipped binary files                               */
/* ------------------------------------------------------------------ */

function deepReportWithSkippedBinary(overrides = {}) {
  const raw = fixture("report-v2.json");
  raw.analysis_status.deep = {
    requested_file_count: 4, successful_file_count: 2, failed_file_count: 0, failed_files: [],
    skipped_binary_file_count: 2,
    skipped_binary_files: [
      { side: "A", path: "logo.png", reason: "binary" },
      { side: "B", path: "logo.png", reason: "binary" },
    ],
    ...overrides,
  };
  return raw;
}

test("#7 a complete Deep report with skipped binary files is accepted and disclosed", () => {
  const report = model.parseLiveReport(deepReportWithSkippedBinary());
  assert.equal(report.analysis_status.deep.skipped_binary_file_count, 2);
  const banner = model.buildReportViewModel(report).banners
    .find((b) => /skipped files \(binary or not decodable as text\)/i.test(b.title));
  assert.ok(banner, "skipped binary files must be disclosed");
  assert.match(banner.message, /A:logo\.png \(binary\); B:logo\.png \(binary\)/);
  const fact = buildReviewSummary(report).facts.find((f) => /binary or not decodable as text/.test(f.label));
  assert.equal(fact.value, "2");
  assert.equal(fact.attention, true);
});

test("#7 skipped-binary counts must still add up", () => {
  assert.throws(
    () => model.parseLiveReport(deepReportWithSkippedBinary({ successful_file_count: 3 })),
    /skipped-binary/,
  );
  assert.throws(
    () => model.parseLiveReport(deepReportWithSkippedBinary({ skipped_binary_file_count: 1 })),
    /skipped_binary_file_count must equal/,
  );
  // Older v2 writers omit the fields: still requested == successful + failed.
  const legacy = fixture("report-v2.json");
  assert.doesNotThrow(() => model.parseLiveReport(legacy));
});

/* ------------------------------------------------------------------ */
/* #5 / #6 / #65 / #39 export publication                              */
/* ------------------------------------------------------------------ */

test("#5 a <stem>_files folder without a prior manifest is never replaced", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  const userFile = writeFile(outputDir, "Case_files/2023_signed_contract.pdf", "USER ORIGINAL");
  const outputPath = path.join(outputDir, "Case.pdf");
  assert.throws(
    () => createExportTransaction({
      dirA, dirB, outputPath, format: "pdf", noMerge: true, uncomparedFiles: "inline", batesNumber: false,
    }),
    /not exactly covered by a prior Diffinite report manifest/,
  );
  assert.equal(fs.readFileSync(userFile, "utf8"), "USER ORIGINAL");
  assert.deepEqual(fs.readdirSync(outputDir).filter((n) => n.startsWith(".diffinite-export-")), []);
});

test("#5 a prior split tree modified after export is preserved", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  const outputPath = path.join(outputDir, "report.pdf");
  const prior = { "report_files/000_cover.pdf": "%PDF-cover", "report_files/entries/a.py.pdf": "%PDF-a" };
  for (const [rel, data] of Object.entries(prior)) { writeFile(outputDir, rel, data); }
  fs.writeFileSync(path.join(outputDir, "report.pdf.manifest.sha256.json"), manifestFor(prior));
  const annotated = writeFile(outputDir, "report_files/entries/a.py.pdf", "%PDF-a with lawyer notes");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: true, uncomparedFiles: "inline", batesNumber: false,
  });
  await assert.rejects(transaction.verifyExistingOutputs(), /modified report file/);
  stageSplitPdf(transaction, { "report_files/000_cover.pdf": "%PDF-new" });
  await assert.rejects(transaction.publish(), /modified report file/);
  assert.equal(fs.readFileSync(annotated, "utf8"), "%PDF-a with lawyer notes");
});

test("#5 an unmodified prior split tree owned by its manifest is replaced", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  const outputPath = path.join(outputDir, "report.pdf");
  const prior = { "report_files/000_cover.pdf": "%PDF-old", "report_files/entries/old.py.pdf": "%PDF-o" };
  for (const [rel, data] of Object.entries(prior)) { writeFile(outputDir, rel, data); }
  fs.writeFileSync(path.join(outputDir, "report.pdf.manifest.sha256.json"), manifestFor(prior));

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: true, uncomparedFiles: "inline", batesNumber: false,
  });
  await transaction.verifyExistingOutputs();
  stageSplitPdf(transaction, { "report_files/000_cover.pdf": "%PDF-new" });
  await transaction.publish();
  assert.deepEqual(listFiles(path.join(outputDir, "report_files")), ["000_cover.pdf"]);
});

test("#6 another run's bare manifest and uncompared list survive an export", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  const cliManifest = JSON.stringify({ reports: [{ path: "cli_report.pdf", sha256: "0".repeat(64), size_bytes: 1 }] });
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), cliManifest);
  fs.writeFileSync(path.join(outputDir, "cli_report.pdf"), "cli");
  fs.writeFileSync(path.join(outputDir, "report_uncompared.txt"), "cli list");

  const outputPath = path.join(outputDir, "report.pdf");
  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false, uncomparedFiles: "inline", batesNumber: false,
  });
  stageMergedPdf(transaction);
  await transaction.publish();
  assert.equal(fs.readFileSync(path.join(outputDir, "manifest.sha256.json"), "utf8"), cliManifest);
  assert.equal(fs.readFileSync(path.join(outputDir, "report_uncompared.txt"), "utf8"), "cli list");
});

test("#6 a legacy bare manifest describing only this report is removed with its uncompared list", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  fs.writeFileSync(path.join(outputDir, "report.pdf"), "%PDF-legacy");
  fs.writeFileSync(path.join(outputDir, "report_uncompared.txt"), "legacy list");
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), manifestFor({
    "report.pdf": "%PDF-legacy", "report_uncompared.txt": "legacy list",
  }));
  const outputPath = path.join(outputDir, "report.pdf");
  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false, uncomparedFiles: "inline", batesNumber: false,
  });
  stageMergedPdf(transaction);
  await transaction.publish();
  assert.equal(fs.existsSync(path.join(outputDir, "manifest.sha256.json")), false);
  assert.equal(fs.existsSync(path.join(outputDir, "report_uncompared.txt")), false);
  assert.equal(fs.readFileSync(outputPath, "utf8"), "%PDF-new");
});

test("#65 a merged export removes the earlier split tree its manifest owned", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  const prior = { "report_files/000_cover.pdf": "%PDF-cover", "report_files/entries/a.py.pdf": "%PDF-a" };
  for (const [rel, data] of Object.entries(prior)) { writeFile(outputDir, rel, data); }
  fs.writeFileSync(path.join(outputDir, "report.pdf.manifest.sha256.json"), manifestFor(prior));

  const outputPath = path.join(outputDir, "report.pdf");
  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false, uncomparedFiles: "inline", batesNumber: false,
  });
  stageMergedPdf(transaction);
  await transaction.publish();
  assert.equal(fs.existsSync(path.join(outputDir, "report_files")), false);
  const manifest = JSON.parse(fs.readFileSync(path.join(outputDir, "report.pdf.manifest.sha256.json"), "utf8"));
  assert.ok(manifest.reports.every((entry) => !entry.path.startsWith("report_files/")));
});

test("#65 a split tree owned by the sibling format's manifest is left alone", async (t) => {
  const { dirA, dirB, outputDir } = makeDirs(tempRoot(t));
  const htmlTree = { "report_files/index.html": "<html>", "report_files/entries/a.py.html": "<a>" };
  for (const [rel, data] of Object.entries(htmlTree)) { writeFile(outputDir, rel, data); }
  fs.writeFileSync(path.join(outputDir, "report.html.manifest.sha256.json"), manifestFor(htmlTree));

  const outputPath = path.join(outputDir, "report.pdf");
  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false, uncomparedFiles: "inline", batesNumber: false,
  });
  stageMergedPdf(transaction);
  await transaction.publish();
  assert.deepEqual(listFiles(path.join(outputDir, "report_files")), ["entries/a.py.html", "index.html"]);
});

test("#39 a staged manifest path outside the staging folder fails with a clear message", async (t) => {
  const base = tempRoot(t);
  const dirs = makeDirs(base);
  const outputDir = path.join(base, "Acme_files");
  fs.mkdirSync(outputDir);
  const outputPath = path.join(outputDir, "report.html");
  const transaction = createExportTransaction({
    dirA: dirs.dirA, dirB: dirs.dirB, outputPath, format: "html", noMerge: false,
    uncomparedFiles: "inline", batesNumber: false,
  });
  const html = "<html></html>";
  const digest = sha256(html);
  const staged = {
    "report.html": html,
    "report.html.sha256": `${digest}  report.html\n`,
    "report.html.sig": `SHA-256: ${digest}\nReport: report.html\n`,
  };
  for (const [rel, data] of Object.entries(staged)) { writeFile(transaction.stagingDirectory, rel, data); }
  // What the unfixed evidence._logical_report_paths writes for this layout.
  const legacyPaths = Object.fromEntries(Object.entries(staged).map(([rel, data]) =>
    [`Acme_files/${path.basename(transaction.stagingDirectory)}/${rel}`, data]));
  writeFile(transaction.stagingDirectory, "manifest.sha256.json", manifestFor(legacyPaths));
  await assert.rejects(transaction.publish(), /not relative to the export folder: Acme_files\//);
  assert.equal(fs.existsSync(outputPath), false);
});

/* ------------------------------------------------------------------ */
/* #9 Tree Viewer selection of files without a 1:1 pair               */
/* ------------------------------------------------------------------ */

function phase1Report() {
  return model.parseReport({
    ...fixture("report-v2.json"),
    results: [result({ file_a: "Common.java", file_b: "Common.java", ratio: 0 })],
    summary: { matched_pairs: 1, unmatched_a_count: 2, unmatched_b_count: 1 },
    deep_results: [
      { file_a: "Common.java", fingerprint_count_a: 9, matches: [{ file_b: "Other.java", shared_hashes: 3, jaccard: 0.5, inconclusive: false }] },
      { file_a: "Secret.java", fingerprint_count_a: 9, matches: [{ file_b: "zzqqxx.java", shared_hashes: 9, jaccard: 1, inconclusive: false }] },
    ],
    unmatched_a: ["Secret.java", "Lonely.java"],
    unmatched_b: ["zzqqxx.java"],
  });
}

test("#9 A files with only Deep Compare matches, and unmatched A files, are selectable", () => {
  const report = phase1Report();
  assert.deepEqual([...tree.selectableFilesA(report)].sort(), ["Common.java", "Lonely.java", "Secret.java"]);
  const unpaired = tree.buildUnpairedRows(report);
  assert.deepEqual(unpaired.map((row) => row.file_a), ["Secret.java", "Lonely.java"]);
  assert.equal(unpaired[0].hasCandidate, true);
  assert.equal(unpaired[0].best.file_b, "zzqqxx.java");

  const html = tree.buildTreeViewerHtml(report, tree.sortForReview(report), "N");
  const checked = [...html.matchAll(/class="file-cb" value="([^"]+)" checked/g)].map((m) => m[1]).sort();
  // Common.java has 0% line similarity but a Deep candidate; Secret.java has only a Deep match.
  assert.deepEqual(checked, ["Common.java", "Secret.java"]);
  assert.match(html, /value="Lonely\.java"/);
  assert.match(html, /of 3 A files selected/);
  assert.match(html, /Deep Compare matches of unchecked files are not in the report/);
});

/* ------------------------------------------------------------------ */
/* #40 / #73 frozen inputs and reviewed-run comparison                 */
/* ------------------------------------------------------------------ */

test("#40 the exclusion list is frozen byte for byte", (t) => {
  const dir = tempRoot(t);
  const file = path.join(dir, ".diffignore");
  const bytes = Buffer.from("# comment\n/build/\n\nnode_modules\n", "utf8");
  fs.writeFileSync(file, bytes);
  const snapshot = freeze.readIgnoreSnapshot(file);
  assert.equal(snapshot.sha256, sha256(bytes));
  assert.equal(snapshot.ruleCount, 2);
  fs.writeFileSync(file, "everything-changed\n");
  const temporary = freeze.writeIgnoreSnapshot(snapshot);
  t.after(temporary.cleanup);
  assert.deepEqual(fs.readFileSync(temporary.filePath), bytes);
  assert.deepEqual(freeze.snapshotRules(snapshot), ["/build/", "node_modules"]);
  assert.equal(freeze.readIgnoreSnapshot(path.join(dir, "missing")), null);
});

test("#40 runner passes the frozen snapshot, never a live ~/.diffignore, when one is given", () => {
  const runner = source("runner.ts");
  assert.doesNotMatch(runner, /fs\.existsSync\(defaultIgnoreFile\)/);
  assert.match(runner, /opts\.ignoreSnapshot !== undefined \? opts\.ignoreSnapshot : readIgnoreSnapshot\(\)/);
  assert.match(runner, /buildArgs\(exportOptions, ignoreFile\.filePath\)/);
  assert.match(runner, /no longer match the reviewed analysis/);
  const compare = source("compareCommand.ts");
  assert.match(compare, /ignoreSnapshot = readIgnoreSnapshot\(\)/);
  assert.match(compare, /phase2Opts = \{ \.\.\.options, filterJson: filterJsonPath, ignoreSnapshot \}/);
  assert.match(compare, /reviewedInputs: phase2\.inputs/);
});

test("#73 Phase 2 is compared with the reviewed Phase 1", () => {
  const reviewed = phase1Report();
  const inputs = { a: { "Common.java": "aa", "Secret.java": "bb" }, b: { "Common.java": "cc" } };
  const ignore = reviewed.metadata.ignore_file_sha256;
  const same = freeze.compareReviewedRuns(
    { report: reviewed, inputs }, { report: reviewed, inputs }, ["Common.java", "Secret.java"], ignore,
  );
  assert.deepEqual(same, []);

  const repaired = model.parseReport({
    ...fixture("report-v2.json"),
    metadata: { ...fixture("report-v2.json").metadata, ignore_file_sha256: "f".repeat(64) },
    results: [result({ file_a: "Common.java", file_b: "Moved.java" })],
    deep_results: [],
  });
  const changedInputs = { a: { ...inputs.a, "Secret.java": "XX" }, b: inputs.b };
  const problems = freeze.compareReviewedRuns(
    { report: reviewed, inputs }, { report: repaired, inputs: changedInputs }, ["Common.java", "Secret.java"], ignore,
  );
  const text = problems.join("\n");
  assert.match(text, /Phase 2 did not use the exclusion list/);
  assert.match(text, /A:Secret\.java \(content changed\)/);
  assert.match(text, /Common\.java: reviewed with Common\.java, report has Moved\.java/);
  assert.match(text, /Secret\.java: Deep Compare matches differ/);

  const unknown = freeze.compareReviewedRuns(
    { report: reviewed, inputs: null }, { report: reviewed, inputs }, ["Common.java"], ignore,
  );
  assert.match(unknown.join(" "), /could not be read/);
});

test("#73 input manifests are read from Python's manifest layout", () => {
  const inputs = freeze.parseInputManifest({
    source_a: { files: [{ path: "x.c", sha256: "AB" }] },
    source_b: { files: [{ path: "x.c", sha256: "cd" }, { path: "y.c", sha256: "ef" }] },
  });
  assert.deepEqual(inputs, { a: { "x.c": "ab" }, b: { "x.c": "cd", "y.c": "ef" } });
  assert.deepEqual(freeze.diffInputManifests(inputs, { a: {}, b: inputs.b }), ["A:x.c (removed or now excluded)"]);
});

test("#73 results show a banner when the report does not match the review", () => {
  const html = results.buildResultHtml(
    phase1Report(), model.defaultAnalysisOptions(), "N", ["Source files changed between the review and the report: A:x.c (content changed)."],
  );
  assert.match(html, /does not match the analysis you reviewed/);
  assert.match(html, /A:x\.c \(content changed\)/);
  assert.match(presets.describeReportOutput(model.defaultAnalysisOptions(), "pdf", { selectedPairs: 1 }).join(" "),
    /published only if every input file still has the SHA-256/);
});

/* ------------------------------------------------------------------ */
/* #41 default exclusion list and disclosure                           */
/* ------------------------------------------------------------------ */

test("#41 the default ~/.diffignore enables no rule", () => {
  assert.deepEqual(freeze.ignoreRules(ignoreList.DEFAULT_IGNORE_PATTERNS), []);
  const examples = ignoreList.DEFAULT_IGNORE_PATTERNS.split("\n")
    .filter((line) => /^# \/[^ ]+\/$/.test(line));
  assert.ok(examples.length > 0, "anchored examples are offered");
});

test("#41 active exclusion rules are disclosed in the summary and the results header", () => {
  const raw = fixture("report-v2.json");
  raw.metadata.ignore_patterns = ["build"];
  raw.metadata.ignore_file_sha256 = "a".repeat(64);
  const report = model.parseLiveReport(raw);
  const fact = buildReviewSummary(report).facts.find((f) => /Exclusion list/.test(f.label));
  assert.equal(fact.value, "1");
  assert.equal(fact.attention, true);
  assert.match(results.buildResultHtml(report, model.defaultAnalysisOptions(), "N"), /Exclusion list \(\.diffignore\): 1 rule, SHA-256 prefix a{12}/);
  assert.match(source("optionsPanel.ts"), /Exclusion list in use: ~\/\.diffignore has \$\{snapshot\.ruleCount === 1 \? "1 rule" : `\$\{snapshot\.ruleCount\} rules`\}/);
});

/* ------------------------------------------------------------------ */
/* #62 #63 #64 runner process handling                                 */
/* ------------------------------------------------------------------ */

test("#62 an exit code with open pipes is not treated as a closed process tree", async () => {
  class ExitedParent extends EventEmitter {
    constructor() {
      super();
      this.exitCode = 0;
      this.signalCode = null;
      this.stdout = { destroyed: false, readableEnded: false };
      this.stderr = { destroyed: false, readableEnded: false };
    }
  }
  const child = new ExitedParent();
  assert.equal(await waitForProcessClose(child, 10), false);
  child.stdout.destroyed = true;
  child.stderr.readableEnded = true;
  assert.equal(await waitForProcessClose(child, 10), true);

  const registry = new ActiveProcessRegistry();
  registry.track(child);
  assert.equal(registry.has(child), true);
  child.emit("close", 0);
  assert.equal(registry.has(child), false);

  const runner = source("runner.ts");
  assert.doesNotMatch(runner, /if \(proc\.exitCode !== null \|\| proc\.signalCode !== null\) \{\s*activeProcesses\.release/);
  assert.match(runner, /if \(!activeProcesses\.has\(proc\)\)/);
});

test("#63 pipeline step messages are parsed from stderr lines across chunks", () => {
  const lines = [];
  const buffer = new LineBuffer((line) => lines.push(line), 8192);
  buffer.push("2026-11-10 10:00:00,000 [INFO] Step 1: Coll");
  buffer.push("ecting files\r\n2026-11-10 10:00:01,000 [INFO] Loaded 3 ignore patterns\n[INFO] Step 4b: Deep");
  buffer.flush();
  assert.deepEqual(lines.map(pipelineStepMessage), ["Step 1: Collecting files", null, "Step 4b: Deep"]);
  const runner = source("runner.ts");
  assert.match(runner, /onOutputLines\(proc\.stderr, \(line\) => \{[\s\S]*?pipelineStepMessage\(line\)/);
  assert.doesNotMatch(runner, /line\.includes\("\[INFO\] Step"\)/);
});

test("#64 stdout/stderr are decoded as UTF-8 streams, not per chunk", async () => {
  assert.doesNotMatch(source("runner.ts"), /chunk\.toString\(\)/);
  assert.match(source("runner.ts"), /stream\.setEncoding\("utf8"\)/);
  // The same decode path: a Hangul character split across two reads survives.
  const stream = new PassThrough();
  stream.setEncoding("utf8");
  const lines = [];
  const buffer = new LineBuffer((line) => lines.push(line), 8192);
  stream.on("data", (chunk) => buffer.push(chunk));
  const bytes = Buffer.from("오류: 한글.py\n", "utf8");
  stream.write(bytes.subarray(0, 2));
  stream.end(bytes.subarray(2));
  await new Promise((resolve) => stream.on("end", resolve));
  assert.deepEqual(lines, ["오류: 한글.py"]);
});

/* ------------------------------------------------------------------ */
/* #66 #67 failure classification                                      */
/* ------------------------------------------------------------------ */

test("#66 an output-side PermissionError is not reported as unreadable input", () => {
  const locked = "diffinite exited with code 1:\nTraceback (most recent call last):\n" +
    "PermissionError: [Errno 13] Permission denied: 'C:\\\\out\\\\report.pdf'";
  assert.equal(classifyFailure(new Error(locked)).kind, "output-write");
  assert.equal(classifyFailure(new Error(
    "diffinite exited with code 1:\nRuntimeError: Input collection was incomplete: 1 file",
  )).kind, "unreadable-input");
  assert.equal(classifyFailure(new Error("x\nAccess Denied (PermissionError)")).kind, "unreadable-input");
  assert.equal(classifyFailure(new Error(
    "Export not published: the source folders no longer match the reviewed analysis (A:x.c (content changed)).",
  )).kind, "inputs-changed");
});

test("#67 only exit code 2 is an option error", () => {
  assert.equal(classifyFailure(new Error("diffinite exited with code 2:\nusage: diffinite")).kind, "invalid-argument");
  for (const code of [20, 25, 255, 2147483651]) {
    assert.notEqual(
      classifyFailure(new Error(`diffinite exited with code ${code}:\nFatal Python error: Segmentation fault`)).kind,
      "invalid-argument", String(code),
    );
  }
});

/* ------------------------------------------------------------------ */
/* #68 #69 #70 #71 #72 webviews                                        */
/* ------------------------------------------------------------------ */

test("#68 empty or out-of-range numbers are rejected before a run", () => {
  const ok = model.defaultAnalysisOptions();
  assert.equal(model.validateRunOptions(ok), null);
  assert.match(model.validateRunOptions({ ...ok, threshold: Number.NaN }), /File name matching threshold is empty/);
  assert.match(model.validateRunOptions({ ...ok, threshold: undefined }), /empty/);
  assert.match(model.validateRunOptions({ ...ok, threshold: 101 }), /between 0 and 100/);
  assert.match(model.validateRunOptions({ ...ok, kGram: 0 }), /at least 1/);
  assert.match(model.validateRunOptions({ ...ok, workers: 1.5 }), /whole number/);
  assert.equal(model.validateRunOptions({ ...ok, thresholdDeep: undefined }), null, "auto mode ignores it");
  assert.match(model.validateRunOptions({ ...ok, thresholdMode: "manual", thresholdDeep: undefined }), /Manual Jaccard/);
  assert.equal(model.validateRunOptions({ ...ok, threshold: 0 }), null, "0 typed by the user is valid");

  const panel = source("optionsPanel.ts");
  assert.doesNotMatch(panel, /threshold: Number\(document\.getElementById\('threshold'\)\.value\)/);
  assert.match(panel, /typeof o\.threshold === 'number' \? o\.threshold : 60/);
  assert.match(panel, /const invalid = validateRunOptions\(msg\.options\)/);
});

test("#69 Simple mode shows no fingerprint settings or threshold banners", () => {
  const raw = fixture("report-v2.json");
  raw.metadata = { ...raw.metadata, exec_mode: "simple", threshold: 5, threshold_provenance: "legacy-uncalibrated", calibration_disclosure: null };
  const report = model.parseReport(raw);
  const titles = model.buildReportViewModel(report).banners.map((b) => b.title);
  assert.ok(!titles.some((t) => /threshold|Metadata unavailable/i.test(t)), titles.join());
  const html = results.buildResultHtml(report, model.defaultAnalysisOptions(), "N");
  const meta = html.match(/<div class="meta-bar">[\s\S]*?<\/div>/)[0];
  assert.doesNotMatch(meta, /K=|W=|Jaccard|provenance/);

  raw.metadata.exec_mode = "deep";
  const deepTitles = model.buildReportViewModel(model.parseReport(raw)).banners.map((b) => b.title);
  assert.ok(deepTitles.includes("Default threshold"));
});

test("#70 Preserve folder tree follows the No Merge checkbox", () => {
  const panel = source("optionsPanel.ts");
  assert.match(panel, /noMergeCb\.addEventListener\('change', updatePreserveTree\)/);
  assert.match(panel, /preserveTreeCb\.disabled = !noMergeCb\.checked/);
  assert.match(panel, /updateBatesVisibility\(\);\s*updatePreserveTree\(\);/);
});

test("#71 closing the Results panel during an export keeps the saved notice", async () => {
  let disposed = false;
  const disposeListeners = [];
  let onMessage;
  const posted = [];
  const webview = {
    html: "",
    onDidReceiveMessage(fn) { onMessage = fn; return { dispose() {} }; },
    postMessage(message) { posted.push(message); return Promise.resolve(true); },
  };
  const panel = {
    get webview() { if (disposed) { throw new Error("Webview is disposed"); } return webview; },
    onDidDispose(fn) { disposeListeners.push(fn); return { dispose() {} }; },
    dispose() { disposed = true; disposeListeners.forEach((fn) => fn()); },
  };
  const infos = [];
  Object.assign(vscodeStub.window, {
    createWebviewPanel: () => panel,
    showSaveDialog: async () => ({ fsPath: path.join(os.tmpdir(), "r.html") }),
    withProgress: async (_options, task) => {
      const value = await task({ report() {} }, { isCancellationRequested: false, onCancellationRequested: () => ({ dispose() {} }) });
      panel.dispose(); // the user closed the tab while the export ran
      return value;
    },
    showInformationMessage: async (message) => { infos.push(message); return undefined; },
    showWarningMessage: async () => undefined,
  });
  results.showResults({ subscriptions: [] }, phase1Report(), model.defaultAnalysisOptions(), { dirA: "/x/A", dirB: "/x/B" });
  await onMessage({ command: "export", format: "html", preset: presets.REPORT_PRESETS[0].id });
  assert.equal(exportCalls.length, 1);
  assert.deepEqual(infos, ["HTML report saved."]);
  assert.deepEqual(posted, [], "no postMessage after dispose");
});

test("#72 the save dialog starts in a real folder, never the drive root", () => {
  const dirs = { dirA: path.resolve("/cases/A"), dirB: path.resolve("/cases/B") };
  assert.equal(
    results.defaultExportPath("r.pdf", path.resolve("/work"), dirs),
    path.join(path.resolve("/work"), "r.pdf"),
  );
  // A workspace that is (inside) a compared folder would be refused at export.
  assert.equal(
    results.defaultExportPath("r.pdf", path.join(dirs.dirA, "sub"), dirs),
    path.join(path.resolve("/cases"), "r.pdf"),
  );
  assert.equal(results.defaultExportPath("r.pdf", undefined, dirs), path.join(path.resolve("/cases"), "r.pdf"));
  assert.doesNotMatch(source("resultViewer.ts"), /defaultUri: vscode\.Uri\.file\(defaultFilename\)/);
});

/* ------------------------------------------------------------------ */
/* #74 pre-scan                                                        */
/* ------------------------------------------------------------------ */

test("#74 shouldIgnore follows collector.should_ignore", () => {
  const cases = [
    ["src/main/java/com/acme/build/Builder.java", ["build"], true],
    ["src/main/java/com/acme/build/Builder.java", ["/build/"], false],
    ["build/out.o", ["/build/"], true],
    ["a/node_modules/x.js", ["node_modules/"], true],
    ["a/node_modules", ["node_modules/"], false], // a file, not a directory
    ["src/a.py", ["src/*.py"], true],
    ["src/a/b.py", ["src/*.py"], false],
    ["x/y/z.gen.cs", ["**/*.gen.cs"], true],
    ["Build/x", ["build"], false],
    ["abc/def", ["abc/**"], true],
    ["abc", ["abc/**"], false],
    ["f1.txt", ["f[0-9].txt"], true],
    ["fa.txt", ["f[!a].txt"], false],
  ];
  for (const [rel, patterns, expected] of cases) {
    const isDir = rel === "abc";
    assert.equal(scanner.shouldIgnore(rel, patterns, isDir), expected, `${rel} ${patterns}`);
  }
});

test("#74 the pre-scan is asynchronous, honours exclusions and can be cancelled", async (t) => {
  const base = tempRoot(t);
  for (const side of ["A", "B"]) {
    writeFile(base, `${side}/keep.c`, "int x;");
    writeFile(base, `${side}/node_modules/dep/index.js`, "x");
  }
  const pending = scanner.scanAndEstimate(path.join(base, "A"), path.join(base, "B"), ["node_modules"]);
  assert.ok(pending instanceof Promise);
  const scan = await pending;
  assert.equal(scan.fileCountA, 1);
  assert.equal(scan.matchedPairsCount, 1);
  const cancelled = await scanner.scanAndEstimate(
    path.join(base, "A"), path.join(base, "B"), [], { isCancellationRequested: true },
  );
  assert.equal(cancelled, undefined);
  assert.doesNotMatch(source("dirScanner.ts"), /readdirSync|statSync\(fullPath\)/);
});
