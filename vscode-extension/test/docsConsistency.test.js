const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const model = require("../out/analysisModel.js");

const root = path.join(__dirname, "..");
function read(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

function guiTableDefault(readme, option) {
  const row = readme.split(/\r?\n/).find((line) => line.startsWith(`| **${option}** |`));
  assert.ok(row, `README GUI options table has no row for ${option}`);
  return row.split("|")[2].trim();
}

test("README GUI options table defaults match defaultAnalysisOptions()", () => {
  const readme = read("README.md");
  const defaults = model.defaultAnalysisOptions();
  const onOff = (value) => (value ? "**on**" : "off");
  assert.equal(guiTableDefault(readme, "No Autojunk"), onOff(defaults.noAutojunk));
  assert.equal(guiTableDefault(readme, "Hash (SHA-256)"), onOff(defaults.hash));
  assert.equal(guiTableDefault(readme, "Strip Comments"), onOff(defaults.stripComments));
  assert.equal(guiTableDefault(readme, "Normalize"), onOff(defaults.normalize));
  assert.ok(defaults.pageNumber && defaults.fileNumber && defaults.batesNumber);
  assert.equal(guiTableDefault(readme, "Page / File / Bates Numbers"), "**on**");
  assert.equal(guiTableDefault(readme, "Threshold"), `\`${defaults.threshold}\``);
  assert.equal(guiTableDefault(readme, "K-gram"), `\`${defaults.kGram}\``);
  assert.equal(guiTableDefault(readme, "Window"), `\`${defaults.window}\``);
});

test("no Bates auto-update promise: nothing in src updates the preset after export", () => {
  const pkg = JSON.parse(read("package.json"));
  const desc = pkg.contributes.configuration.properties["diffinite.batesPresets"]
    .items.properties.nextBatesNumber.description;
  assert.doesNotMatch(desc, /auto-updated/i);
  assert.match(desc, /not updated automatically/i);
  assert.doesNotMatch(read("README.md"), /auto-continues/i);
  assert.doesNotMatch(read("src/config.ts"), /updateBatesPresetStart/);
});

test("extension text does not overstate hashes, estimates or legal effect", () => {
  const readme = read("README.md");
  assert.doesNotMatch(readme, /forensic chain-of-custody/i);
  assert.doesNotMatch(readme, /OOM Defense/);
  assert.doesNotMatch(readme, /Dynamic CPU Calibration/);
  assert.doesNotMatch(read("src/helpViewer.ts"), /legally sound|mathematically guaranteed/i);
  assert.doesNotMatch(read("src/compareCommand.ts"), /Calibrated/);
});

test("bundled runtime ships no pip console-script launchers", () => {
  const ignore = read(".vscodeignore").split(/\r?\n/);
  assert.ok(ignore.includes("bin/python/Lib/site-packages/bin/**"));
  const build = read("scripts/build_bundle.ps1");
  const prune = build.indexOf('Remove-Item "$sitePackages\\bin"');
  const step8 = build.indexOf("# 8. Post-prune");
  assert.ok(prune > 0 && prune < step8, "site-packages\\bin must be removed in the prune step");
});
