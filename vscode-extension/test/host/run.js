#!/usr/bin/env node
/**
 * Launch the in-host smoke test (test/host/index.js) in an isolated VS Code.
 *
 *   node test/host/run.js                 # uses `code` on PATH, this folder as the extension
 *   node test/host/run.js --vsix x.vsix   # install a packaged VSIX into the isolated profile first
 *
 * Uses the locally installed VS Code (no download, no npm dependency) with a
 * throw-away --user-data-dir / --extensions-dir, so the user's profile and
 * extensions are untouched. Prints each check and the extension-host log path.
 * Exit code 1 if any check fails.
 */
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const extRoot = path.resolve(__dirname, "..", "..");
const repoRoot = path.resolve(extRoot, "..");
const args = process.argv.slice(2);
const vsix = args.includes("--vsix") ? path.resolve(args[args.indexOf("--vsix") + 1]) : null;

function codeCli() {
  for (const name of process.platform === "win32" ? ["code.cmd", "code"] : ["code"]) {
    const r = spawnSync(process.platform === "win32" ? "where" : "which", [name], { encoding: "utf8" });
    if (r.status === 0) { return r.stdout.split(/\r?\n/)[0].trim(); }
  }
  throw new Error("VS Code `code` CLI not found on PATH");
}

function prepareFixtures(dir) {
  const corpus = path.join(repoRoot, "tests", "validation", "behaviour_corpus",
    "cross-language-and-encoding", "c2_java_to_kotlin_csharp");
  fs.cpSync(corpus, path.join(dir, "port"), { recursive: true });
  for (const side of ["A", "B"]) {
    const d = path.join(dir, "binx", side);
    fs.mkdirSync(d, { recursive: true });
    fs.writeFileSync(path.join(d, "blob.bin"), Buffer.from([0, side === "A" ? 1 : 2, 255, 254, 0]));
    fs.writeFileSync(path.join(d, "a.py"), `x = ${side === "A" ? 1 : 2}\n`);
  }
}

const code = codeCli(); // before creating anything, so a missing CLI leaves nothing behind
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "diffinite-host-"));
const fixtures = path.join(tmp, "fixtures");
const userData = path.join(tmp, "ud");
const extDir = path.join(tmp, "ext");
const resultPath = path.join(tmp, "result.json");
prepareFixtures(fixtures);

const shell = process.platform === "win32";
// code.cmd needs a shell on Windows; quote every argument because paths contain spaces.
const q = (a) => (process.platform === "win32" && /[\s&()]/.test(a) ? `"${a}"` : a);
const exec = (argv, opts) => spawnSync(q(code), argv.map(q), { ...opts, shell });
const base = ["--user-data-dir", userData, "--extensions-dir", extDir];
let developmentPath = extRoot;
if (vsix) {
  const inst = exec([...base, "--install-extension", vsix, "--force"], { encoding: "utf8" });
  if (inst.status !== 0) { console.error(inst.stdout, inst.stderr); process.exit(1); }
  const installed = fs.readdirSync(extDir).find((d) => d.startsWith("nash-dir.diffinite-"));
  developmentPath = path.join(extDir, installed);
}

// The `code` launcher returns as soon as a window opens. Run the Electron binary
// itself (as @vscode/test-electron does) so this process waits for the test run.
function electronBinary() {
  if (process.platform === "win32") { return path.resolve(path.dirname(code), "..", "Code.exe"); }
  if (process.platform === "darwin") { return path.resolve(path.dirname(code), "..", "..", "..", "MacOS", "Electron"); }
  return path.resolve(path.dirname(fs.realpathSync(code)), "..", "code");
}
const electron = electronBinary();
const childEnv = { ...process.env, DIFFINITE_HOST_FIXTURES: fixtures, DIFFINITE_HOST_RESULT: resultPath };
delete childEnv.ELECTRON_RUN_AS_NODE;
const run = spawnSync(electron, [
  ...base,
  "--disable-extensions",
  "--disable-workspace-trust",
  "--skip-welcome", "--skip-release-notes",
  `--extensionDevelopmentPath=${developmentPath}`,
  `--extensionTestsPath=${path.join(__dirname, "index.js")}`,
  "--new-window",
], { encoding: "utf8", timeout: 10 * 60 * 1000, env: childEnv });

let failed = run.status !== 0;
if (fs.existsSync(resultPath)) {
  for (const r of JSON.parse(fs.readFileSync(resultPath, "utf8"))) {
    if (!r.ok) { failed = true; }
    console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name} (${r.ms} ms)${r.ok ? (r.detail ? " " + JSON.stringify(r.detail) : "") : "\n      " + r.error.split("\n").slice(0, 4).join("\n      ")}`);
  }
} else {
  console.log("FAIL  host produced no result file");
  console.log((run.stdout || "").slice(-2000), (run.stderr || "").slice(-2000));
  failed = true;
}
const logs = path.join(userData, "logs");
console.log(`\nExtension under test: ${developmentPath}`);
console.log(`Host logs: ${fs.existsSync(logs) ? logs : "(none)"}  (exthost/exthost.log)`);
if (!failed && !process.env.DIFFINITE_HOST_KEEP) {
  // Files under ud/ can stay locked briefly after Code.exe exits on Windows.
  try { fs.rmSync(tmp, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); }
  catch (e) { console.log(`(could not remove ${tmp}: ${e.message})`); }
} else {
  console.log(`Kept for inspection: ${tmp} (set DIFFINITE_HOST_KEEP=1 to keep passing runs too)`);
}
console.log(failed ? "FAILED" : "OK");
process.exit(failed ? 1 : 0);
