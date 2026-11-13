const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  ActiveProcessRegistry,
  waitForProcessClose,
} = require("../out/processRegistry.js");
const { RunGate } = require("../out/runGate.js");

const extensionRoot = path.join(__dirname, "..");

test("run gate permits exactly one Phase-1 owner until release", () => {
  const gate = new RunGate();
  assert.equal(gate.tryEnter(), true);
  assert.equal(gate.tryEnter(), false);
  gate.leave();
  assert.equal(gate.tryEnter(), true);
});

test("export gate rejects a second publication to the same manifest and releases after failure", async () => {
  const gate = new RunGate();
  const manifestWrites = [];
  let finishFirst;
  const first = (async () => {
    assert.equal(gate.tryEnter(), true);
    try {
      await new Promise((resolve) => { finishFirst = resolve; });
      manifestWrites.push("first");
    } finally {
      gate.leave();
    }
  })();

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(gate.tryEnter(), false);
  assert.deepEqual(manifestWrites, []);
  finishFirst();
  await first;

  assert.equal(gate.tryEnter(), true);
  try {
    throw new Error("simulated export failure or cancellation");
  } catch {
    // The production handler reports this error, then its finally block releases.
  } finally {
    gate.leave();
  }
  assert.equal(gate.tryEnter(), true);
  gate.leave();
  assert.deepEqual(manifestWrites, ["first"]);
});

test("active process registry releases closed children and terminates all remaining children", async () => {
  class FakeProcess extends EventEmitter {
    constructor() {
      super();
      this.exitCode = null;
      this.signalCode = null;
    }
  }
  const registry = new ActiveProcessRegistry();
  const first = new FakeProcess();
  const second = new FakeProcess();
  registry.track(first);
  registry.track(second);
  assert.equal(registry.size, 2);

  first.emit("close", 0);
  assert.equal(registry.size, 1);

  const terminated = [];
  await registry.terminateAll(async (proc) => { terminated.push(proc); });
  assert.deepEqual(terminated, [second]);
  assert.equal(registry.size, 0);
});

test("missing child close event times out, removes its listener, and releases registry state", async () => {
  class NeverClosingProcess extends EventEmitter {
    constructor() {
      super();
      this.exitCode = null;
      this.signalCode = null;
    }
  }
  const registry = new ActiveProcessRegistry();
  const child = new NeverClosingProcess();
  registry.track(child);

  await registry.terminateAll(async (proc) => {
    assert.equal(await waitForProcessClose(proc, 10), false);
  });

  assert.equal(child.listenerCount("close"), 0);
  assert.equal(registry.size, 0);
});

test("termination command failure still releases registry state", async () => {
  class FakeProcess extends EventEmitter {}
  const registry = new ActiveProcessRegistry();
  registry.track(new FakeProcess());

  await assert.rejects(
    registry.terminateAll(async () => { throw new Error("simulated kill failure"); }),
    /could not be terminated/,
  );
  assert.equal(registry.size, 0);
});

test("extension is disabled in untrusted workspaces", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(extensionRoot, "package.json"), "utf8"));
  assert.equal(pkg.capabilities?.untrustedWorkspaces?.supported, false);
  assert.equal(pkg.contributes.configuration.properties["diffinite.pythonPath"].scope, "machine");
});

test("options UI disables Run until the host reports completion", () => {
  const source = fs.readFileSync(path.join(extensionRoot, "src", "optionsPanel.ts"), "utf8");
  assert.match(source, /runComplete[\s\S]*?btnRun\.disabled\s*=\s*false/);
  assert.match(source, /btnRun\.disabled\s*=\s*true[\s\S]*?postMessage\(\{ command: 'run'/);
});

test("exports expose cancellation and forward the cancellation token", () => {
  const source = fs.readFileSync(path.join(extensionRoot, "src", "resultViewer.ts"), "utf8");
  assert.match(source, /cancellable:\s*true/);
  assert.match(source, /async \(progress, token\)[\s\S]*?runExport\([\s\S]*?progress, token/);
});

test("no-merge export opens the published split report instead of a stale file anchor", () => {
  const source = fs.readFileSync(path.join(extensionRoot, "src", "resultViewer.ts"), "utf8");
  assert.match(source, /splitMode[\s\S]*?000_cover\.pdf[\s\S]*?index\.html/);
  assert.match(source, /openExternal\(completedExport\.openUri\)/);
  assert.doesNotMatch(source, /openExternal\(uri\)/);
});

test("result UI blocks duplicate exports and the host gate releases in finally", () => {
  const source = fs.readFileSync(path.join(extensionRoot, "src", "resultViewer.ts"), "utf8");
  assert.match(source, /const exportRunGate = new RunGate\(\)/);
  assert.match(source, /if \(!exportRunGate\.tryEnter\(\)\)/);
  assert.match(source, /finally\s*\{[\s\S]*?exportRunGate\.leave\(\)[\s\S]*?exportComplete/);
  assert.match(source, /exportPending = true;\s*exportBtn\.disabled = true/);
  assert.match(source, /exportComplete[\s\S]*?exportBtn\.disabled = false/);
});

test("runner exports through same-parent staging before publishing", () => {
  const source = fs.readFileSync(path.join(extensionRoot, "src", "runner.ts"), "utf8");
  assert.match(source, /createExportTransaction\([\s\S]*?stagedOutputPath/);
  assert.match(source, /await exportTransaction\.publish\(\{[\s\S]*?isCancellationRequested/);
  assert.doesNotMatch(source, /const cliArgs = \[\s*formatFlag, outputPath/);
});

test("Phase-2 exports retain the exact selected file scope", () => {
  const compare = fs.readFileSync(path.join(extensionRoot, "src", "compareCommand.ts"), "utf8");
  const runner = fs.readFileSync(path.join(extensionRoot, "src", "runner.ts"), "utf8");
  assert.match(compare, /showResults\([\s\S]*?selectedFiles:\s*\[\.\.\.selectedFiles\]/);
  assert.match(runner, /opts\.selectedFiles[\s\S]*?diffinite-export-filter-/);
  assert.match(runner, /exportOptions\.filterJson\s*=\s*selectionFilter\.filePath/);
  assert.match(runner, /selectionFilter\?\.cleanup\(\)/);
});

test("runner strictly parses live reports and extension deactivation drains children", () => {
  const runner = fs.readFileSync(path.join(extensionRoot, "src", "runner.ts"), "utf8");
  const extension = fs.readFileSync(path.join(extensionRoot, "src", "extension.ts"), "utf8");
  assert.match(runner, /parseLiveReport\(JSON\.parse\(raw\)\)/);
  assert.match(extension, /terminateAllProcesses/);
  assert.match(runner, /PROCESS_TERMINATION_TIMEOUT_MS\s*=\s*4_000/);
  assert.match(runner, /terminateProcessTree\(proc\)\.then\([\s\S]*?rejectOnce/);
  assert.match(runner, /is still running[\s\S]*?operating system process manager/);
  assert.match(runner, /SystemRoot[\s\S]*?System32[\s\S]*?taskkill\.exe/);
  assert.doesNotMatch(runner, /spawn\("taskkill"/);
});

test("runner neither writes diagnostic logs into source workspaces nor buffers unbounded stderr", () => {
  const runner = fs.readFileSync(path.join(extensionRoot, "src", "runner.ts"), "utf8");
  assert.doesNotMatch(runner, /--unreadable-log/);
  assert.doesNotMatch(runner, /stderr(?:Data)?\s*\+=/);
});
