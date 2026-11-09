/**
 * In-host smoke test: runs INSIDE a real VS Code Extension Host.
 *
 * Launched by test/host/run.js (or the vsce-debug skill) through VS Code's own
 * `--extensionTestsPath`, so it needs no extra npm dependency. It exercises the
 * paths unit tests cannot reach: activation, command registration, the bundled
 * analyzer through runner.ts, the Tree/Result webview panels, and a real export.
 *
 * Inputs come from DIFFINITE_HOST_FIXTURES (a directory prepared by run.js);
 * results are written to DIFFINITE_HOST_RESULT as JSON.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");

const EXT_ID = "nash-dir.diffinite";
const noProgress = { report() {} };
const neverCancelled = new vscode.CancellationTokenSource().token;

async function step(results, name, fn) {
  const started = Date.now();
  // Record "started" first so a hang or host crash still shows where it stopped.
  results.push({ name, ok: false, ms: 0, error: "started, did not finish" });
  flush(results);
  const entry = results[results.length - 1];
  try {
    const detail = await fn();
    Object.assign(entry, { ok: true, ms: Date.now() - started, detail: detail ?? null, error: undefined });
  } catch (err) {
    Object.assign(entry, { ok: false, ms: Date.now() - started, error: String(err && err.stack || err) });
  }
  flush(results);
}

function flush(results) {
  if (process.env.DIFFINITE_HOST_RESULT) {
    fs.writeFileSync(process.env.DIFFINITE_HOST_RESULT, JSON.stringify(results, null, 2), "utf8");
  }
}

async function run() {
  const fixtures = process.env.DIFFINITE_HOST_FIXTURES;
  const results = [];
  const ext = vscode.extensions.getExtension(EXT_ID);
  const mod = (name) => require(path.join(ext.extensionPath, "out", name));

  await step(results, "activate extension", async () => {
    await ext.activate();
    assert.equal(ext.isActive, true);
    return { version: ext.packageJSON.version, path: ext.extensionPath };
  });

  await step(results, "commands registered", async () => {
    const all = await vscode.commands.getCommands(true);
    for (const id of ["diffinite.compare", "diffinite.help", "diffinite.editIgnoreList"]) {
      assert.ok(all.includes(id), `${id} missing`);
    }
  });

  await step(results, "help and options panels open", async () => {
    await vscode.commands.executeCommand("diffinite.help");
    await vscode.commands.executeCommand("diffinite.compare");
    // Webview tabs register asynchronously after the command returns; poll briefly
    // (50 x 100 ms = 5 s upper bound, generous for a local UI event).
    let tabs = [];
    for (let i = 0; i < 50; i++) {
      tabs = vscode.window.tabGroups.all.flatMap((g) => g.tabs.map((t) => t.label));
      if (tabs.some((t) => /Help|Manual/i.test(t)) && tabs.some((t) => /Diffinite — Analysis/.test(t))) { break; }
      await new Promise((r) => setTimeout(r, 100));
    }
    assert.ok(tabs.some((t) => /Help|Manual/i.test(t)), `help tab missing: ${tabs}`);
    assert.ok(tabs.some((t) => /Diffinite — Analysis/.test(t)), `options tab missing: ${tabs}`);
    return { tabs };
  });

  const model = mod("analysisModel.js");
  const runner = mod("runner.js");
  const dirA = path.join(fixtures, "port", "left");
  const dirB = path.join(fixtures, "port", "right");
  let phase1;

  await step(results, "phase 1 analysis through bundled analyzer", async () => {
    const opts = { ...model.defaultAnalysisOptions(), metricsOnly: true, workers: 1 };
    phase1 = await runner.runAnalysis(dirA, dirB, opts, noProgress, neverCancelled);
    assert.equal(phase1.schema_version, 2);
    assert.ok(phase1.results.length >= 1);
    return { pairs: phase1.results.length, deep: phase1.deep_results.length, state: phase1.analysis_status.state };
  });

  await step(results, "review (tree viewer) panel builds", async () => {
    const { TreeViewerPanel } = mod("treeViewer.js");
    TreeViewerPanel.createOrShow(phase1, { dirA, dirB }, async () => {});
    assert.ok(TreeViewerPanel.currentPanel, "tree viewer did not open");
    TreeViewerPanel.currentPanel.dispose();
  });

  let phase2;
  const selected = () => phase1.results.map((r) => r.file_a);
  await step(results, "phase 2 selective analysis + result viewer", async () => {
    const tmp = fs.mkdtempSync(path.join(fixtures, "filter-"));
    const filter = path.join(tmp, "f.json");
    fs.writeFileSync(filter, JSON.stringify(selected()), "utf8");
    const opts = { ...model.defaultAnalysisOptions(), filterJson: filter, workers: 1 };
    phase2 = await runner.runAnalysis(dirA, dirB, opts, noProgress, neverCancelled);
    assert.ok(phase2.results.every((r) => typeof r.html_diff === "string"));
    const context = { subscriptions: [], extensionPath: ext.extensionPath };
    mod("resultViewer.js").showResults(context, phase2, { ...opts, selectedFiles: selected() }, { dirA, dirB });
    return { pairs: phase2.results.length };
  });

  for (const preset of ["technical", "evidence"]) {
    await step(results, `export PDF with ${preset} preset`, async () => {
      const presets = mod("reportPresets.js");
      const out = path.join(fixtures, `export-${preset}`, "report.pdf");
      fs.mkdirSync(path.dirname(out), { recursive: true });
      const opts = presets.applyReportPreset(
        { ...model.defaultAnalysisOptions(), workers: 1, selectedFiles: selected(), batesSuffix: "-CONFIDENTIAL" },
        preset,
      );
      await runner.runExport(dirA, dirB, opts, "pdf", out, noProgress, neverCancelled);
      const files = fs.readdirSync(path.dirname(out));
      assert.ok(files.includes("report.pdf"), `no pdf: ${files}`);
      assert.ok(files.some((f) => f.endsWith(".manifest.sha256.json")), `no manifest: ${files}`);
      return { files, pdfBytes: fs.statSync(out).size };
    });
  }

  await step(results, "binary-exclude analysis is accepted (regression)", async () => {
    const opts = { ...model.defaultAnalysisOptions(), metricsOnly: true, workers: 1, binaryHandling: "exclude", mode: "simple" };
    const r = await runner.runAnalysis(path.join(fixtures, "binx", "A"), path.join(fixtures, "binx", "B"), opts, noProgress, neverCancelled);
    return { rows: r.results.length, requested: r.analysis_status.diff.requested_pair_count };
  });

  await step(results, "cancellation is reported as cancelled", async () => {
    const source = new vscode.CancellationTokenSource();
    const opts = { ...model.defaultAnalysisOptions(), metricsOnly: true, workers: 1 };
    const pending = runner.runAnalysis(dirA, dirB, opts, noProgress, source.token);
    source.cancel();
    let err = null;
    try {
      await pending;
    } catch (e) {
      err = e;
    }
    // Cancelled synchronously after start: resolving would mean the cancel was ignored,
    // and "cancelled-incomplete" would mean the analyzer was not confirmed dead.
    assert.ok(err, "analysis resolved although cancellation was requested right after start");
    const kind = mod("failureClassifier.js").classifyFailure(err).kind;
    assert.equal(kind, "cancelled", `classified as ${kind}: ${err.message}`);
    return { kind };
  });

  flush(results);
  const failed = results.filter((r) => !r.ok);
  if (failed.length) {
    throw new Error(`${failed.length} host check(s) failed: ${failed.map((f) => f.name).join(", ")}`);
  }
}

module.exports = { run };
