const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createExportTransaction } = require("../out/exportTransaction.js");

function tempRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "diffinite-export-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function makeDirs(root) {
  const dirA = path.join(root, "source-a");
  const dirB = path.join(root, "source-b");
  const outputDir = path.join(root, "output");
  fs.mkdirSync(dirA);
  fs.mkdirSync(dirB);
  fs.mkdirSync(outputDir);
  return { dirA, dirB, outputDir };
}

function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

function writeFile(root, relative, data) {
  const destination = path.join(root, ...relative.split("/"));
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination, data);
  return destination;
}

function writeManifest(stagingDirectory, artifacts) {
  const reports = Object.entries(artifacts).map(([relative, data]) => ({
    path: relative,
    sha256: sha256(data),
    size_bytes: Buffer.byteLength(data),
  }));
  writeFile(stagingDirectory, "manifest.sha256.json", JSON.stringify({ reports }));
}

function addManifestArtifact(stagingDirectory, relative, data) {
  writeFile(stagingDirectory, relative, data);
  const manifestPath = path.join(stagingDirectory, "manifest.sha256.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.reports.push({
    path: relative,
    sha256: sha256(data),
    size_bytes: Buffer.byteLength(data),
  });
  fs.writeFileSync(manifestPath, JSON.stringify(manifest));
}

function finalManifestPath(outputPath) {
  return path.join(
    path.dirname(outputPath),
    `${path.basename(outputPath)}.manifest.sha256.json`,
  );
}

function assertManifestMatches(outputDir, manifestPath) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  for (const entry of manifest.reports) {
    const artifact = path.join(outputDir, ...entry.path.split("/"));
    const data = fs.readFileSync(artifact);
    assert.equal(data.length, entry.size_bytes);
    assert.equal(sha256(data), entry.sha256);
  }
  return manifest;
}

function listFiles(root, base = root) {
  if (!fs.existsSync(root)) { return []; }
  return fs.readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(root, entry.name);
    return entry.isDirectory()
      ? listFiles(absolute, base)
      : [path.relative(base, absolute).split(path.sep).join("/")];
  }).sort();
}

function stageMergedPdf(transaction, marker = "new") {
  const pdf = `%PDF-${marker}`;
  const csv = `csv-${marker}`;
  const digest = sha256(pdf);
  const artifacts = {
    "report.pdf": pdf,
    "report.csv": csv,
    "report.pdf.sha256": `${digest}  report.pdf\n`,
    "report.pdf.sig": `SHA-256: ${digest}\nReport: report.pdf\n`,
  };
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeManifest(transaction.stagingDirectory, artifacts);
}

function stageMergedHtml(transaction, marker = "new") {
  const html = `<html>${marker}</html>`;
  const digest = sha256(html);
  const artifacts = {
    "report.html": html,
    "report.html.sha256": `${digest}  report.html\n`,
    "report.html.sig": `SHA-256: ${digest}\nReport: report.html\n`,
  };
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeManifest(transaction.stagingDirectory, artifacts);
}

test("merged export publishes the complete staged set only after validation", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  fs.writeFileSync(outputPath, "old-report");
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), "old-manifest");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false,
    uncomparedFiles: "inline", batesNumber: true,
  });
  stageMergedPdf(transaction);
  await transaction.publish();

  assert.equal(fs.readFileSync(outputPath, "utf8"), "%PDF-new");
  assert.equal(fs.readFileSync(path.join(outputDir, "report.csv"), "utf8"), "csv-new");
  assertManifestMatches(outputDir, finalManifestPath(outputPath));
  // A bare manifest that cannot be shown to describe this report (here: not
  // even JSON) may belong to a CLI run, so it is preserved (audit #6).
  assert.equal(fs.readFileSync(path.join(outputDir, "manifest.sha256.json"), "utf8"), "old-manifest");
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("publish failure restores every prior final artifact byte-for-byte", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  const prior = {
    "report.pdf": "old-report",
    "report.csv": "old-csv",
    "report.pdf.sha256": "old-sha",
    "report.pdf.sig": "old-sig",
    "manifest.sha256.json": "old-manifest",
    "report.pdf.manifest.sha256.json": "old-specific-manifest",
  };
  for (const [name, data] of Object.entries(prior)) {
    fs.writeFileSync(path.join(outputDir, name), data);
  }

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false,
    uncomparedFiles: "inline", batesNumber: true,
  });
  stageMergedPdf(transaction);
  let injected = false;
  await assert.rejects(
    transaction.publish({
      renameSync(source, destination) {
        if (!injected && path.basename(source) === "report.pdf" && path.dirname(source) === transaction.stagingDirectory) {
          injected = true;
          throw new Error("injected publish failure");
        }
        fs.renameSync(source, destination);
      },
    }),
    /injected publish failure/,
  );

  for (const [name, data] of Object.entries(prior)) {
    assert.equal(fs.readFileSync(path.join(outputDir, name), "utf8"), data);
  }
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("aborting a partial stage leaves prior outputs untouched", (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.html");
  fs.writeFileSync(outputPath, "old-html");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "html", noMerge: false,
    uncomparedFiles: "inline", batesNumber: false,
  });
  fs.writeFileSync(transaction.stagedOutputPath, "partial-html");
  transaction.abort();

  assert.equal(fs.readFileSync(outputPath, "utf8"), "old-html");
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("cancellation observed during staged validation prevents publication", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  fs.writeFileSync(outputPath, "old-report");
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), "old-manifest");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false,
    uncomparedFiles: "inline", batesNumber: true,
  });
  stageMergedPdf(transaction);
  let cancelled = false;
  setImmediate(() => { cancelled = true; });

  await assert.rejects(
    transaction.publish({ isCancellationRequested: () => cancelled }),
    /cancel/i,
  );

  assert.equal(fs.readFileSync(outputPath, "utf8"), "old-report");
  assert.equal(fs.readFileSync(path.join(outputDir, "manifest.sha256.json"), "utf8"), "old-manifest");
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("invalid or incomplete staged evidence never replaces prior outputs", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.html");
  fs.writeFileSync(outputPath, "old-html");
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), "old-manifest");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "html", noMerge: false,
    uncomparedFiles: "inline", batesNumber: false,
  });
  fs.writeFileSync(transaction.stagedOutputPath, "new-html-without-sidecars");
  await assert.rejects(transaction.publish(), /missing|required|manifest/i);

  assert.equal(fs.readFileSync(outputPath, "utf8"), "old-html");
  assert.equal(fs.readFileSync(path.join(outputDir, "manifest.sha256.json"), "utf8"), "old-manifest");
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("manifest hash mismatch preserves the prior complete artifact set", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  fs.writeFileSync(outputPath, "old-report");
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), "old-manifest");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: false,
    uncomparedFiles: "inline", batesNumber: false,
  });
  stageMergedPdf(transaction);
  fs.writeFileSync(transaction.stagedOutputPath, "%PDF-tampered-after-manifest");
  await assert.rejects(transaction.publish(), /hash mismatch|size mismatch/i);

  assert.equal(fs.readFileSync(outputPath, "utf8"), "old-report");
  assert.equal(fs.readFileSync(path.join(outputDir, "manifest.sha256.json"), "utf8"), "old-manifest");
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("no-merge publishes the exact current split tree and removes stale merged artifacts", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  const finalTree = path.join(outputDir, "report_files");
  writeFile(finalTree, "index.html", "old-index-html");
  writeFile(finalTree, "001_old.py.html", "old-flat-html-entry");
  writeFile(finalTree, "entries/a.py.html", "old-html-entry");
  writeFile(finalTree, "entries/stale.py.pdf", "stale-pdf");
  // Ownership proof required before the tree may be replaced (audit #5).
  writeManifest(outputDir, {
    "report_files/index.html": "old-index-html",
    "report_files/001_old.py.html": "old-flat-html-entry",
    "report_files/entries/a.py.html": "old-html-entry",
    "report_files/entries/stale.py.pdf": "stale-pdf",
  });
  fs.renameSync(path.join(outputDir, "manifest.sha256.json"), finalManifestPath(outputPath));
  fs.writeFileSync(outputPath, "%PDF-old-merged");
  fs.writeFileSync(`${outputPath}.sha256`, "old-sha");
  fs.writeFileSync(`${outputPath}.sig`, "old-sig");
  fs.writeFileSync(path.join(outputDir, "report.csv"), "old-csv");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: true,
    uncomparedFiles: "inline", batesNumber: true,
  });
  const artifacts = {
    "report_files/000_cover.pdf": "%PDF-cover",
    "report_files/entries/new.py.pdf": "%PDF-new",
  };
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeManifest(transaction.stagingDirectory, artifacts);
  await transaction.publish();

  assert.deepEqual(listFiles(finalTree), ["000_cover.pdf", "entries/new.py.pdf"]);
  assert.equal(fs.readFileSync(path.join(finalTree, "entries/new.py.pdf"), "utf8"), "%PDF-new");
  assert.equal(fs.existsSync(outputPath), false);
  assert.equal(fs.existsSync(`${outputPath}.sha256`), false);
  assert.equal(fs.existsSync(`${outputPath}.sig`), false);
  assert.equal(fs.existsSync(path.join(outputDir, "report.csv")), false);

  const manifest = assertManifestMatches(outputDir, finalManifestPath(outputPath));
  assert.deepEqual(manifest.reports.map((entry) => entry.path).sort(), [
    "report_files/000_cover.pdf",
    "report_files/entries/new.py.pdf",
  ]);
  assert.equal(fs.existsSync(path.join(outputDir, "manifest.sha256.json")), false);
});

test("no-merge HTML removes its stale merged anchor and integrity sidecars", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.html");
  fs.writeFileSync(outputPath, "old-merged-html");
  fs.writeFileSync(`${outputPath}.sha256`, "old-sha");
  fs.writeFileSync(`${outputPath}.sig`, "old-sig");

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "html", noMerge: true,
    uncomparedFiles: "inline", batesNumber: false,
  });
  const artifacts = {
    "report_files/index.html": "new-index-html",
    "report_files/entries/new.py.html": "new-entry-html",
  };
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeManifest(transaction.stagingDirectory, artifacts);
  await transaction.publish();

  assert.deepEqual(listFiles(path.join(outputDir, "report_files")), [
    "entries/new.py.html",
    "index.html",
  ]);
  assert.equal(fs.existsSync(outputPath), false);
  assert.equal(fs.existsSync(`${outputPath}.sha256`), false);
  assert.equal(fs.existsSync(`${outputPath}.sig`), false);
  assertManifestMatches(outputDir, finalManifestPath(outputPath));
});

test("sequential merged PDF and HTML exports keep independent valid manifests", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const pdfPath = path.join(outputDir, "report.pdf");
  const htmlPath = path.join(outputDir, "report.html");

  const pdfTransaction = createExportTransaction({
    dirA, dirB, outputPath: pdfPath, format: "pdf", noMerge: false,
    uncomparedFiles: "separate", batesNumber: false,
  });
  stageMergedPdf(pdfTransaction, "pdf-sequential");
  addManifestArtifact(
    pdfTransaction.stagingDirectory, "report_uncompared.txt", "pdf-uncompared",
  );
  await pdfTransaction.publish();

  const htmlTransaction = createExportTransaction({
    dirA, dirB, outputPath: htmlPath, format: "html", noMerge: false,
    uncomparedFiles: "separate", batesNumber: false,
  });
  stageMergedHtml(htmlTransaction, "html-sequential");
  addManifestArtifact(
    htmlTransaction.stagingDirectory, "report_uncompared.txt", "html-uncompared",
  );
  await htmlTransaction.publish();

  assert.equal(fs.readFileSync(pdfPath, "utf8"), "%PDF-pdf-sequential");
  assert.equal(fs.readFileSync(htmlPath, "utf8"), "<html>html-sequential</html>");
  assert.equal(
    fs.readFileSync(path.join(outputDir, "report.pdf_uncompared.txt"), "utf8"),
    "pdf-uncompared",
  );
  assert.equal(
    fs.readFileSync(path.join(outputDir, "report.html_uncompared.txt"), "utf8"),
    "html-uncompared",
  );
  assert.equal(fs.existsSync(path.join(outputDir, "report_uncompared.txt")), false);
  assertManifestMatches(outputDir, finalManifestPath(pdfPath));
  assertManifestMatches(outputDir, finalManifestPath(htmlPath));
  assert.equal(fs.existsSync(path.join(outputDir, "manifest.sha256.json")), false);
});

test("sequential split formats remove superseded split evidence and ancillary files", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const pdfPath = path.join(outputDir, "report.pdf");
  const htmlPath = path.join(outputDir, "report.html");

  const pdfTransaction = createExportTransaction({
    dirA, dirB, outputPath: pdfPath, format: "pdf", noMerge: true,
    uncomparedFiles: "separate", batesNumber: false,
  });
  const pdfArtifacts = {
    "report_files/000_cover.pdf": "%PDF-cover",
    "report_files/entries/a.py.pdf": "%PDF-entry",
  };
  for (const [relative, data] of Object.entries(pdfArtifacts)) {
    writeFile(pdfTransaction.stagingDirectory, relative, data);
  }
  writeManifest(pdfTransaction.stagingDirectory, pdfArtifacts);
  addManifestArtifact(
    pdfTransaction.stagingDirectory, "report_uncompared.txt", "pdf-uncompared",
  );
  await pdfTransaction.publish();

  const pdfManifest = finalManifestPath(pdfPath);
  assertManifestMatches(outputDir, pdfManifest);
  assert.equal(
    fs.readFileSync(path.join(outputDir, "report.pdf_uncompared.txt"), "utf8"),
    "pdf-uncompared",
  );

  const htmlTransaction = createExportTransaction({
    dirA, dirB, outputPath: htmlPath, format: "html", noMerge: true,
    uncomparedFiles: "separate", batesNumber: false,
  });
  const htmlArtifacts = {
    "report_files/index.html": "html-index",
    "report_files/entries/a.py.html": "html-entry",
  };
  for (const [relative, data] of Object.entries(htmlArtifacts)) {
    writeFile(htmlTransaction.stagingDirectory, relative, data);
  }
  writeManifest(htmlTransaction.stagingDirectory, htmlArtifacts);
  addManifestArtifact(
    htmlTransaction.stagingDirectory, "report_uncompared.txt", "html-uncompared",
  );
  await htmlTransaction.publish();

  assert.deepEqual(listFiles(path.join(outputDir, "report_files")), [
    "entries/a.py.html",
    "index.html",
  ]);
  assert.equal(fs.existsSync(pdfManifest), false);
  assert.equal(fs.existsSync(path.join(outputDir, "report.pdf_uncompared.txt")), false);
  assert.equal(
    fs.readFileSync(path.join(outputDir, "report.html_uncompared.txt"), "utf8"),
    "html-uncompared",
  );
  assertManifestMatches(outputDir, finalManifestPath(htmlPath));
});

test("unknown user files added before split publication are preserved and fail closed", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: true,
    uncomparedFiles: "inline", batesNumber: false,
  });
  const artifacts = {
    "report_files/000_cover.pdf": "%PDF-cover",
    "report_files/entries/new.py.pdf": "%PDF-new",
  };
  for (const [relative, data] of Object.entries(artifacts)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeManifest(transaction.stagingDirectory, artifacts);

  const notesPath = writeFile(path.join(outputDir, "report_files"), "notes.txt", "user notes");
  await assert.rejects(
    transaction.publish(),
    /unknown file|preserving/i,
  );

  assert.equal(fs.readFileSync(notesPath, "utf8"), "user notes");
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
  assert.deepEqual(
    fs.readdirSync(outputDir).filter((name) => name.startsWith(".diffinite-export-")),
    [],
  );
});

test("no-merge publish failure restores the entire prior sibling tree", async (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const outputPath = path.join(outputDir, "report.pdf");
  const finalTree = path.join(outputDir, "report_files");
  const prior = {
    "000_cover.pdf": "%PDF-old-cover",
    "index.html": "old-index-html",
    "entries/old.py.pdf": "%PDF-old-entry",
    "entries/old.py.html": "old-html-entry",
  };
  for (const [relative, data] of Object.entries(prior)) {
    writeFile(finalTree, relative, data);
  }
  // Ownership proof required before the tree may be replaced (audit #5).
  const priorManifest = finalManifestPath(outputPath);
  writeManifest(outputDir, Object.fromEntries(
    Object.entries(prior).map(([relative, data]) => [`report_files/${relative}`, data]),
  ));
  fs.renameSync(path.join(outputDir, "manifest.sha256.json"), priorManifest);
  const priorManifestText = fs.readFileSync(priorManifest, "utf8");
  fs.writeFileSync(path.join(outputDir, "manifest.sha256.json"), "old-manifest");
  const oldMerged = {
    "report.pdf": "%PDF-old-merged",
    "report.pdf.sha256": "old-sha",
    "report.pdf.sig": "old-sig",
    "report.csv": "old-csv",
  };
  for (const [name, data] of Object.entries(oldMerged)) {
    fs.writeFileSync(path.join(outputDir, name), data);
  }

  const transaction = createExportTransaction({
    dirA, dirB, outputPath, format: "pdf", noMerge: true,
    uncomparedFiles: "inline", batesNumber: true,
  });
  const staged = {
    "report_files/000_cover.pdf": "%PDF-new-cover",
    "report_files/entries/new.py.pdf": "%PDF-new-entry",
  };
  for (const [relative, data] of Object.entries(staged)) {
    writeFile(transaction.stagingDirectory, relative, data);
  }
  writeManifest(transaction.stagingDirectory, staged);

  await assert.rejects(
    transaction.publish({
      renameSync(source, destination) {
        if (path.basename(source) === "report_files"
            && path.dirname(source) === transaction.stagingDirectory) {
          throw new Error("injected no-merge publish failure");
        }
        fs.renameSync(source, destination);
      },
    }),
    /injected no-merge publish failure/,
  );

  for (const [relative, data] of Object.entries(prior)) {
    assert.equal(fs.readFileSync(path.join(finalTree, ...relative.split("/")), "utf8"), data);
  }
  assert.equal(fs.existsSync(path.join(finalTree, "entries/new.py.pdf")), false);
  assert.equal(fs.readFileSync(path.join(outputDir, "manifest.sha256.json"), "utf8"), "old-manifest");
  assert.equal(fs.readFileSync(priorManifest, "utf8"), priorManifestText);
  for (const [name, data] of Object.entries(oldMerged)) {
    assert.equal(fs.readFileSync(path.join(outputDir, name), "utf8"), data);
  }
  assert.equal(fs.existsSync(transaction.stagingDirectory), false);
});

test("unsafe source-overlapping outputs are rejected before staging", (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);

  assert.throws(
    () => createExportTransaction({
      dirA, dirB, outputPath: path.join(dirA, "report.pdf"), format: "pdf",
      noMerge: false, uncomparedFiles: "inline", batesNumber: true,
    }),
    /source|unsafe|overlap/i,
  );

  const splitSource = path.join(outputDir, "report_files", "nested-source");
  fs.mkdirSync(splitSource, { recursive: true });
  assert.throws(
    () => createExportTransaction({
      dirA: splitSource, dirB, outputPath: path.join(outputDir, "report.pdf"), format: "pdf",
      noMerge: true, uncomparedFiles: "inline", batesNumber: true,
    }),
    /source|unsafe|overlap/i,
  );

  assert.deepEqual(
    fs.readdirSync(outputDir).filter((name) => name.startsWith(".diffinite-export-")),
    [],
  );
  assert.deepEqual(
    fs.readdirSync(dirA).filter((name) => name.startsWith(".diffinite-export-")),
    [],
  );
});

test("file artifact paths cannot replace existing directories", (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);
  const conflictingCsv = path.join(outputDir, "report.csv");
  writeFile(conflictingCsv, "important.txt", "must-survive");

  assert.throws(
    () => createExportTransaction({
      dirA, dirB, outputPath: path.join(outputDir, "report.pdf"), format: "pdf",
      noMerge: false, uncomparedFiles: "inline", batesNumber: true,
    }),
    /directory|artifact|unsafe/i,
  );

  assert.equal(fs.readFileSync(path.join(conflictingCsv, "important.txt"), "utf8"), "must-survive");
  assert.deepEqual(
    fs.readdirSync(outputDir).filter((name) => name.startsWith(".diffinite-export-")),
    [],
  );
});

test("derived export artifact names must be distinct", (t) => {
  const root = tempRoot(t);
  const { dirA, dirB, outputDir } = makeDirs(root);

  assert.throws(
    () => createExportTransaction({
      dirA, dirB, outputPath: path.join(outputDir, "manifest.sha256.json"), format: "md",
      noMerge: false, uncomparedFiles: "inline", batesNumber: false,
    }),
    /extension|filename|collision|artifact/i,
  );
  assert.throws(
    () => createExportTransaction({
      dirA, dirB, outputPath: path.join(outputDir, "report.csv"), format: "pdf",
      noMerge: false, uncomparedFiles: "inline", batesNumber: false,
    }),
    /extension|filename|collision|artifact/i,
  );

  assert.deepEqual(
    fs.readdirSync(outputDir).filter((name) => name.startsWith(".diffinite-export-")),
    [],
  );
});
