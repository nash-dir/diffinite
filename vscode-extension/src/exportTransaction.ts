/** Same-volume staging and rollback-safe publication for report exports. */
import { createHash } from "crypto";
import * as fs from "fs";
import * as path from "path";

export type ExportFormat = "pdf" | "html" | "md";

export interface ExportTransactionOptions {
  dirA: string;
  dirB: string;
  outputPath: string;
  format: ExportFormat;
  noMerge: boolean;
  uncomparedFiles: "inline" | "separate" | "none";
  batesNumber: boolean;
}

export interface PublicationOptions {
  renameSync?(source: string, destination: string): void;
  isCancellationRequested?(): boolean;
}

interface RenameOperations {
  renameSync(source: string, destination: string): void;
}

interface ArtifactPlan {
  requiredNames: Set<string>;
  optionalNames: Set<string>;
  removalNames: Set<string>;
  conditionalRemovalNames: Set<string>;
  publicationNames: Map<string, string>;
  splitTreeName?: string;
  /** Report-specific manifests that may own an existing `<stem>_files` tree. */
  splitTreeOwnerManifests: string[];
  /** Merged export: an earlier split tree of the same report, removed only when owned. */
  staleSplitTreeName?: string;
  finalManifestName: string;
  /** Names written by older extension versions; removed only with ownership proof. */
  legacyManifestName: string;
  legacyUncomparedName: string;
}

interface ManifestReportEntry {
  path: string;
  sha256: string;
  size_bytes: number;
}

class ExportRollbackError extends Error {}

class ExportCancelledError extends Error {
  public constructor() {
    super("Export canceled before publication; existing output was preserved");
  }
}

function throwIfCancellationRequested(predicate?: () => boolean): void {
  if (predicate?.()) { throw new ExportCancelledError(); }
}

async function yieldBeforePublication(predicate?: () => boolean): Promise<void> {
  // Give the extension host one event-loop turn to deliver a cancellation that
  // arrived while staged artifact validation was in progress.
  await new Promise<void>((resolve) => setImmediate(resolve));
  throwIfCancellationRequested(predicate);
}

function lstat(pathname: string): fs.Stats | undefined {
  try { return fs.lstatSync(pathname); } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") { return undefined; }
    throw err;
  }
}

function canonicalProspectivePath(pathname: string): string {
  let cursor = path.resolve(pathname);
  const missingParts: string[] = [];
  while (!lstat(cursor)) {
    const parent = path.dirname(cursor);
    if (parent === cursor) {
      throw new Error(`Cannot resolve output boundary for ${pathname}`);
    }
    missingParts.unshift(path.basename(cursor));
    cursor = parent;
  }
  const canonicalExisting = fs.realpathSync.native(cursor);
  return path.resolve(canonicalExisting, ...missingParts);
}

function normalized(pathname: string): string {
  const resolved = path.resolve(pathname);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function isWithin(candidate: string, root: string): boolean {
  const relative = path.relative(normalized(root), normalized(candidate));
  return relative === "" || (
    !path.isAbsolute(relative)
    && relative !== ".."
    && !relative.startsWith(`..${path.sep}`)
  );
}

function pathsOverlap(first: string, second: string): boolean {
  return isWithin(first, second) || isWithin(second, first);
}

function buildArtifactPlan(options: ExportTransactionOptions): ArtifactPlan {
  const outputName = path.basename(options.outputPath);
  const outputStem = path.parse(outputName).name;
  const expectedExtension = `.${options.format}`;
  if (path.extname(outputName).toLowerCase() !== expectedExtension) {
    throw new Error(
      `Export output filename must end with ${expectedExtension}: ${outputName}`,
    );
  }
  const finalManifestName = `${outputStem}.${options.format}.manifest.sha256.json`;
  const splitMode = options.noMerge && (options.format === "pdf" || options.format === "html");
  const requiredNames = new Set<string>();
  const optionalNames = new Set<string>();
  const removalNames = new Set<string>();
  const conditionalRemovalNames = new Set<string>();
  const publicationNames = new Map<string, string>();
  const claimedStagedNames = new Set<string>();
  const claimedFinalNames = new Set<string>();
  let splitTreeName: string | undefined;
  const claimName = (
    collection: Set<string>, stagedName: string, finalName = stagedName,
  ): void => {
    // Treat case-only variants as collisions on every platform so a report
    // prepared on one filesystem remains safe when moved to another.
    const stagedKey = stagedName.toLowerCase();
    const finalKey = finalName.toLowerCase();
    if (claimedStagedNames.has(stagedKey) || claimedFinalNames.has(finalKey)) {
      throw new Error(`Unsafe export artifact collision: ${stagedName}`);
    }
    claimedStagedNames.add(stagedKey);
    claimedFinalNames.add(finalKey);
    collection.add(stagedName);
    publicationNames.set(stagedName, finalName);
  };

  // Python always writes this canonical staged name. Publish it under a
  // report-specific final name so sequential exports cannot overwrite one
  // another's evidence manifest.
  claimName(requiredNames, "manifest.sha256.json", finalManifestName);
  // The bare "manifest.sha256.json" is also what the Python CLI writes next to
  // its own reports, so it is removed only after proving it describes this
  // report (see legacyOwnedArtifacts), never by name alone.
  const siblingFormat = options.format === "pdf" ? "html" : "pdf";
  const splitTreeOwnerManifests = [finalManifestName];
  let staleSplitTreeName: string | undefined;

  if (splitMode) {
    splitTreeName = `${outputStem}_files`;
    claimName(requiredNames, splitTreeName);

    // A split export replaces the complete split publication.
    // Remove a previous merged publication in the same transaction so the
    // save-dialog path can never keep pointing at stale evidence.
    removalNames.add(outputName);
    removalNames.add(`${outputName}.sha256`);
    removalNames.add(`${outputName}.sig`);
    if (options.format === "pdf") {
      removalNames.add(`${outputStem}.csv`);
    }
    conditionalRemovalNames.add(
      `${outputStem}.${siblingFormat}.manifest.sha256.json`,
    );
    splitTreeOwnerManifests.push(`${outputStem}.${siblingFormat}.manifest.sha256.json`);
  } else {
    claimName(requiredNames, outputName);
    if (options.format === "pdf" || options.format === "html") {
      // A merged export replaces this report's manifest. If that manifest is
      // the one covering an earlier split tree, the tree would be left with no
      // hash record, so it is removed in the same transaction (when owned).
      staleSplitTreeName = `${outputStem}_files`;
    }
  }

  if (!options.noMerge && (options.format === "pdf" || options.format === "html")) {
    claimName(requiredNames, `${outputName}.sha256`);
    claimName(requiredNames, `${outputName}.sig`);
  }
  if (!options.noMerge && options.format === "pdf") {
    claimName(requiredNames, `${outputStem}.csv`);
  }
  const stagedUncomparedName = `${outputStem}_uncompared.txt`;
  const finalUncomparedName = `${outputStem}.${options.format}_uncompared.txt`;
  // Remove the report-specific prior output. The legacy shared name
  // `<stem>_uncompared.txt` is also written by CLI runs, so it is removed only
  // when an owned legacy manifest lists it (see legacyOwnedArtifacts).
  removalNames.add(finalUncomparedName);
  if (options.uncomparedFiles === "separate") {
    claimName(optionalNames, stagedUncomparedName, finalUncomparedName);
  }
  if (!options.noMerge && options.format === "pdf" && options.batesNumber) {
    removalNames.add(`${outputStem}.bates_tmp.pdf`);
  }

  return {
    requiredNames,
    optionalNames,
    removalNames,
    conditionalRemovalNames,
    publicationNames,
    splitTreeName,
    splitTreeOwnerManifests,
    staleSplitTreeName,
    finalManifestName,
    legacyManifestName: "manifest.sha256.json",
    legacyUncomparedName: stagedUncomparedName,
  };
}

function publicationName(plan: ArtifactPlan, stagedName: string): string {
  const finalName = plan.publicationNames.get(stagedName);
  if (!finalName) {
    throw new Error(`Missing publication mapping for staged artifact: ${stagedName}`);
  }
  return finalName;
}

function sourceRootsOf(options: ExportTransactionOptions): Array<{ canonical: string; lexical: string }> {
  return [options.dirA, options.dirB].map((source) => {
    const canonical = canonicalProspectivePath(source);
    const stat = fs.statSync(canonical);
    if (!stat.isDirectory()) { throw new Error(`Source path is not a directory: ${source}`); }
    return { canonical, lexical: path.resolve(source) };
  });
}

function assertTreeOutsideSources(options: ExportTransactionOptions, treeRoot: string): void {
  const canonicalTree = canonicalProspectivePath(treeRoot);
  if (sourceRootsOf(options).some((root) =>
    pathsOverlap(treeRoot, root.lexical) || pathsOverlap(canonicalTree, root.canonical))) {
    throw new Error(`Unsafe split-report tree overlaps a source directory: ${treeRoot}`);
  }
}

function validateOutputBoundaries(
  options: ExportTransactionOptions,
  plan: ArtifactPlan,
): void {
  const sourceRoots = sourceRootsOf(options);
  const finalParent = path.dirname(path.resolve(options.outputPath));
  const parentStat = fs.statSync(finalParent);
  if (!parentStat.isDirectory()) {
    throw new Error(`Export parent is not a directory: ${finalParent}`);
  }

  const finalArtifactNames = new Set([
    ...[...plan.requiredNames].map((name) => publicationName(plan, name)),
    ...[...plan.optionalNames].map((name) => publicationName(plan, name)),
    ...plan.removalNames,
    ...plan.conditionalRemovalNames,
  ]);
  for (const artifactName of finalArtifactNames) {
    const lexicalCandidate = path.resolve(finalParent, artifactName);
    const canonicalCandidate = canonicalProspectivePath(lexicalCandidate);
    if (sourceRoots.some((root) =>
      isWithin(lexicalCandidate, root.lexical) || isWithin(canonicalCandidate, root.canonical))) {
      throw new Error(`Unsafe export output overlaps a source directory: ${lexicalCandidate}`);
    }
    const existing = lstat(lexicalCandidate);
    if (existing) {
      const expectsDirectory = artifactName === plan.splitTreeName;
      const hasExpectedType = expectsDirectory
        ? existing.isDirectory() && !existing.isSymbolicLink()
        : existing.isFile() && !existing.isSymbolicLink();
      if (!hasExpectedType) {
        throw new Error(
          `Unsafe existing ${expectsDirectory ? "directory" : "file"} artifact target: ${lexicalCandidate}`,
        );
      }
    }
  }
  if (plan.splitTreeName) {
    const lexicalSplitTree = path.resolve(finalParent, plan.splitTreeName);
    const canonicalSplitTree = canonicalProspectivePath(lexicalSplitTree);
    if (sourceRoots.some((root) =>
      pathsOverlap(lexicalSplitTree, root.lexical)
      || pathsOverlap(canonicalSplitTree, root.canonical))) {
      throw new Error(`Unsafe split-report tree overlaps a source directory: ${lexicalSplitTree}`);
    }
  }
}

/**
 * List an existing split tree's files (POSIX paths relative to the tree) after
 * checking that every entry is a name a split-report generator can create.
 * Mirrors pipeline._verify_replaceable_split_tree's structural checks.
 */
function listExistingSplitTree(splitRoot: string): string[] {
  const files: string[] = [];
  const directories: string[] = [];
  const inspectDirectory = (directory: string, underEntries: boolean): void => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      const stat = fs.lstatSync(absolute);
      if (stat.isSymbolicLink()) {
        throw new Error(`Refusing split-report tree containing symlink: ${absolute}`);
      }
      if (stat.isDirectory()) {
        if (!underEntries && entry.name !== "entries") {
          throw new Error(
            `Existing split-report tree contains an unknown directory; preserving it: ${absolute}`,
          );
        }
        directories.push(path.relative(splitRoot, absolute).split(path.sep).join("/"));
        inspectDirectory(absolute, underEntries || entry.name === "entries");
        continue;
      }
      if (!stat.isFile()) {
        throw new Error(`Unsupported existing split-report artifact: ${absolute}`);
      }
      const extension = path.extname(entry.name).toLowerCase();
      const knownRootFile = !underEntries
        && (entry.name === "000_cover.pdf" || entry.name === "index.html");
      // Same rule as pipeline._is_generated_split_artifact: idx:03d or wider.
      const knownFlatFile = !underEntries
        && /^[0-9]{3,}_.+\.(pdf|html)$/i.test(entry.name);
      const knownEntryFile = underEntries && (extension === ".pdf" || extension === ".html");
      if (!knownRootFile && !knownFlatFile && !knownEntryFile) {
        throw new Error(
          `Existing split-report tree contains an unknown file; preserving it: ${absolute}`,
        );
      }
      files.push(path.relative(splitRoot, absolute).split(path.sep).join("/"));
    }
  };
  inspectDirectory(splitRoot, false);
  const unowned = directories.filter((directory) =>
    !files.some((file) => file.startsWith(`${directory}/`)));
  if (unowned.length) {
    throw new Error(
      `Existing split-report tree contains directories with no report files; preserving it: ${unowned.join(", ")}`,
    );
  }
  return files;
}

/**
 * Report entries a prior manifest records under `<treeName>/`, keyed by
 * logical path. Undefined when the manifest is absent or lists no such entry.
 */
function manifestTreeEntries(
  finalParent: string,
  manifestName: string,
  treeName: string,
): Map<string, string> | undefined {
  const manifestPath = path.join(finalParent, manifestName);
  const manifestStat = lstat(manifestPath);
  if (!manifestStat) { return undefined; }
  if (!manifestStat.isFile() || manifestStat.isSymbolicLink() || manifestStat.nlink > 1) {
    throw new Error(`Unsafe existing split manifest target: ${manifestPath}`);
  }
  let parsed: { reports?: unknown };
  try {
    parsed = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as { reports?: unknown };
  } catch (err) {
    throw new Error(`Cannot verify ownership of existing split manifest ${manifestPath}: ${err}`);
  }
  if (parsed === null || typeof parsed !== "object" || !Array.isArray(parsed.reports)) {
    throw new Error(`Cannot verify ownership of existing split manifest: ${manifestPath}`);
  }
  const prefix = `${treeName}/`;
  const entries = new Map<string, string>();
  for (const rawEntry of parsed.reports) {
    if (rawEntry === null || typeof rawEntry !== "object" || Array.isArray(rawEntry)) { continue; }
    const { path: logicalPath, sha256 } = rawEntry as { path?: unknown; sha256?: unknown };
    if (typeof logicalPath !== "string" || !logicalPath.startsWith(prefix)) { continue; }
    if (typeof sha256 !== "string" || entries.has(logicalPath)) {
      throw new Error(`Existing split manifest has ambiguous hashes for ${treeName}: ${manifestPath}`);
    }
    entries.set(logicalPath, sha256.toLowerCase());
  }
  return entries.size ? entries : undefined;
}

interface SplitTreeOwnership {
  treeName: string;
  manifestName: string;
  expected: Map<string, string>;
}

function sameLogicalSet(treeName: string, files: string[], expected: Map<string, string>): boolean {
  return files.length === expected.size
    && files.every((file) => expected.has(`${treeName}/${file}`));
}

/**
 * Decide, without hashing, whether an existing `<stem>_files` tree may be
 * replaced (split export) or must be removed with the manifest it belongs to
 * (merged export). Throws when replacing it would destroy files that a prior
 * Diffinite manifest does not account for exactly.
 */
function inspectExistingSplitTrees(
  finalParent: string,
  plan: ArtifactPlan,
  options: ExportTransactionOptions,
): SplitTreeOwnership[] {
  const owned: SplitTreeOwnership[] = [];
  if (plan.splitTreeName) {
    const splitRoot = path.join(finalParent, plan.splitTreeName);
    const rootStat = lstat(splitRoot);
    if (rootStat) {
      if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
        throw new Error(`Refusing unsafe existing split-report tree: ${splitRoot}`);
      }
      const files = listExistingSplitTree(splitRoot);
      if (files.length) {
        let owner: SplitTreeOwnership | undefined;
        for (const manifestName of plan.splitTreeOwnerManifests) {
          const expected = manifestTreeEntries(finalParent, manifestName, plan.splitTreeName);
          if (expected && sameLogicalSet(plan.splitTreeName, files, expected)) {
            owner = { treeName: plan.splitTreeName, manifestName, expected };
            break;
          }
        }
        if (!owner) {
          throw new Error(
            `Existing ${plan.splitTreeName} is not exactly covered by a prior Diffinite ` +
            `report manifest; preserving it. Move it or choose another file name: ${splitRoot}`,
          );
        }
        owned.push(owner);
      }
    }
  }
  if (plan.staleSplitTreeName) {
    const treeRoot = path.join(finalParent, plan.staleSplitTreeName);
    const rootStat = lstat(treeRoot);
    // Only an existing tree needs its (to-be-replaced) manifest consulted.
    const expected = rootStat
      ? manifestTreeEntries(finalParent, plan.finalManifestName, plan.staleSplitTreeName)
      : undefined;
    if (expected) {
      if (rootStat) {
        if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
          throw new Error(`Refusing unsafe existing split-report tree: ${treeRoot}`);
        }
        assertTreeOutsideSources(options, treeRoot);
        const files = listExistingSplitTree(treeRoot);
        if (!sameLogicalSet(plan.staleSplitTreeName, files, expected)) {
          throw new Error(
            `Existing ${plan.staleSplitTreeName} was listed by ${plan.finalManifestName} but has ` +
            `changed since; preserving both. Move them or choose another file name: ${treeRoot}`,
          );
        }
        owned.push({ treeName: plan.staleSplitTreeName, manifestName: plan.finalManifestName, expected });
      }
    }
  }
  return owned;
}

async function verifySplitTreeHashes(
  finalParent: string,
  ownership: SplitTreeOwnership,
): Promise<void> {
  // Sequential for the same file-descriptor reason as validateStagedArtifacts.
  for (const [logicalPath, digest] of ownership.expected) {
    const absolute = path.join(finalParent, ...logicalPath.split("/"));
    if (await sha256File(absolute) !== digest) {
      throw new Error(
        `Existing ${ownership.treeName} contains a modified report file (${logicalPath}) ` +
        `that no longer matches ${ownership.manifestName}; preserving it.`,
      );
    }
  }
}

/**
 * The bare `manifest.sha256.json` (and legacy `<stem>_uncompared.txt`) are
 * removed only when that manifest lists nothing but artifacts this export is
 * replacing anyway; a CLI run's manifest for other reports is left alone.
 */
function legacyOwnedArtifacts(
  finalParent: string,
  plan: ArtifactPlan,
  targetNames: ReadonlySet<string>,
): string[] {
  const manifestPath = path.join(finalParent, plan.legacyManifestName);
  const stat = lstat(manifestPath);
  if (!stat || !stat.isFile() || stat.isSymbolicLink()) { return []; }
  let parsed: { reports?: unknown };
  try {
    parsed = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as { reports?: unknown };
  } catch {
    return [];
  }
  if (parsed === null || typeof parsed !== "object"
      || !Array.isArray(parsed.reports) || parsed.reports.length === 0) {
    return [];
  }
  let listsLegacyUncompared = false;
  for (const rawEntry of parsed.reports) {
    const logicalPath = rawEntry !== null && typeof rawEntry === "object"
      ? (rawEntry as { path?: unknown }).path : undefined;
    if (typeof logicalPath !== "string") { return []; }
    if (logicalPath === plan.legacyUncomparedName) {
      listsLegacyUncompared = true;
      continue;
    }
    if (!targetNames.has(logicalPath) && !targetNames.has(logicalPath.split("/")[0])) {
      return [];
    }
  }
  const owned = [plan.legacyManifestName];
  if (listsLegacyUncompared) {
    const uncompared = lstat(path.join(finalParent, plan.legacyUncomparedName));
    if (uncompared?.isFile() && !uncompared.isSymbolicLink()) {
      owned.push(plan.legacyUncomparedName);
    }
  }
  return owned;
}

function splitManifestOwnedArtifacts(
  finalParent: string,
  manifestName: string,
  splitTreeName: string,
): string[] | undefined {
  const manifestPath = path.join(finalParent, manifestName);
  const manifestStat = lstat(manifestPath);
  if (!manifestStat) { return undefined; }
  if (!manifestStat.isFile() || manifestStat.isSymbolicLink()) {
    throw new Error(`Unsafe existing split manifest target: ${manifestPath}`);
  }
  let parsed: { reports?: unknown };
  try {
    parsed = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as { reports?: unknown };
  } catch (err) {
    throw new Error(`Cannot verify ownership of existing split manifest ${manifestPath}: ${err}`);
  }
  if (!Array.isArray(parsed.reports)) {
    throw new Error(`Cannot verify ownership of existing split manifest: ${manifestPath}`);
  }
  const prefix = `${splitTreeName}/`;
  const reportPaths = parsed.reports.map((rawEntry) => {
    if (rawEntry === null || typeof rawEntry !== "object" || Array.isArray(rawEntry)) {
      throw new Error(`Invalid report entry in existing split manifest: ${manifestPath}`);
    }
    const logicalPath = (rawEntry as { path?: unknown }).path;
    if (typeof logicalPath !== "string") {
      throw new Error(`Invalid report path in existing split manifest: ${manifestPath}`);
    }
    return logicalPath;
  });
  if (!reportPaths.some((logicalPath) => logicalPath.startsWith(prefix))) {
    return undefined;
  }

  const manifestSuffix = ".manifest.sha256.json";
  const reportIdentity = manifestName.slice(0, -manifestSuffix.length);
  const allowedAncillary = `${reportIdentity}_uncompared.txt`;
  const outsideTree = reportPaths.filter((logicalPath) => !logicalPath.startsWith(prefix));
  if (outsideTree.some((logicalPath) => logicalPath !== allowedAncillary)) {
    throw new Error(
      `Existing split manifest contains an unexpected external artifact: ${manifestPath}`,
    );
  }
  return [manifestName, ...outsideTree];
}

function walkFiles(root: string, base = root): string[] {
  const result: string[] = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const absolute = path.join(root, entry.name);
    const stat = fs.lstatSync(absolute);
    if (stat.isSymbolicLink()) {
      throw new Error(`Refusing staged or existing export tree containing symlink: ${absolute}`);
    }
    if (stat.isDirectory()) {
      result.push(...walkFiles(absolute, base));
    } else if (stat.isFile()) {
      result.push(path.relative(base, absolute).split(path.sep).join("/"));
    } else {
      throw new Error(`Unsupported export artifact type: ${absolute}`);
    }
  }
  return result;
}

async function sha256File(filename: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const digest = createHash("sha256");
    const stream = fs.createReadStream(filename);
    stream.on("data", (chunk) => digest.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(digest.digest("hex")));
  });
}

function manifestPathToFile(stagingDirectory: string, logicalPath: string): string {
  if (!logicalPath || logicalPath.includes("\\") || path.posix.isAbsolute(logicalPath)) {
    throw new Error(`Unsafe report path in staged manifest: ${logicalPath}`);
  }
  const parts = logicalPath.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error(`Unsafe report path in staged manifest: ${logicalPath}`);
  }
  const candidate = path.resolve(stagingDirectory, ...parts);
  if (!isWithin(candidate, stagingDirectory) || candidate === path.resolve(stagingDirectory)) {
    throw new Error(`Staged manifest path escapes the transaction: ${logicalPath}`);
  }
  return candidate;
}

async function validateStagedArtifacts(
  stagingDirectory: string,
  outputName: string,
  options: ExportTransactionOptions,
  plan: ArtifactPlan,
): Promise<void> {
  const topLevel = fs.readdirSync(stagingDirectory);
  const allowed = new Set([...plan.requiredNames, ...plan.optionalNames]);
  for (const name of topLevel) {
    if (!allowed.has(name)) {
      throw new Error(`Unexpected staged export artifact: ${name}`);
    }
  }
  for (const name of plan.requiredNames) {
    if (!lstat(path.join(stagingDirectory, name))) {
      throw new Error(`Missing required staged export artifact: ${name}`);
    }
  }

  const splitTree = plan.splitTreeName
    ? path.join(stagingDirectory, plan.splitTreeName)
    : undefined;
  if (splitTree) {
    const splitStat = fs.lstatSync(splitTree);
    if (!splitStat.isDirectory() || splitStat.isSymbolicLink()) {
      throw new Error(`Invalid staged split-report tree: ${splitTree}`);
    }
    const splitFiles = walkFiles(splitTree);
    if (options.format === "pdf" && !splitFiles.includes("000_cover.pdf")) {
      throw new Error("Incomplete staged PDF tree: 000_cover.pdf is missing");
    }
    if (options.format === "html" && !splitFiles.includes("index.html")) {
      throw new Error("Incomplete staged HTML tree: index.html is missing");
    }
    const currentSplitSuffix = `.${options.format}`;
    if (splitFiles.some((file) => path.extname(file).toLowerCase() !== currentSplitSuffix)) {
      throw new Error("Staged split-report tree contains an unexpected artifact format");
    }
  } else {
    const primary = path.join(stagingDirectory, outputName);
    const primaryStat = fs.lstatSync(primary);
    if (!primaryStat.isFile() || primaryStat.isSymbolicLink() || primaryStat.size === 0) {
      throw new Error("Staged primary report is missing or empty");
    }
  }

  const manifestName = "manifest.sha256.json";
  const manifestFile = path.join(stagingDirectory, manifestName);
  const manifestStat = fs.lstatSync(manifestFile);
  if (!manifestStat.isFile() || manifestStat.isSymbolicLink() || manifestStat.size === 0) {
    throw new Error("Staged manifest is missing or empty");
  }
  let manifest: { reports?: unknown };
  try {
    manifest = JSON.parse(await fs.promises.readFile(manifestFile, "utf8")) as { reports?: unknown };
  } catch (err) {
    throw new Error(`Invalid staged manifest JSON: ${err}`);
  }
  if (!Array.isArray(manifest.reports)) {
    throw new Error("Invalid staged manifest: reports must be an array");
  }

  const manifestPaths = new Set<string>();
  // Validate sequentially so a large no-merge report cannot exhaust the
  // extension host's file-descriptor limit by opening every artifact at once.
  for (const rawEntry of manifest.reports) {
    if (rawEntry === null || typeof rawEntry !== "object" || Array.isArray(rawEntry)) {
      throw new Error("Invalid staged manifest report entry");
    }
    const entry = rawEntry as Partial<ManifestReportEntry>;
    if (typeof entry.path !== "string" || typeof entry.sha256 !== "string"
        || typeof entry.size_bytes !== "number" || !Number.isSafeInteger(entry.size_bytes)
        || entry.size_bytes < 0) {
      throw new Error("Invalid staged manifest report entry fields");
    }
    if (manifestPaths.has(entry.path)) {
      throw new Error(`Duplicate staged manifest report path: ${entry.path}`);
    }
    manifestPaths.add(entry.path);
    // Report paths are logical names relative to the manifest's own folder
    // (the staging directory): `<report>` or `<stem>_files/...`, the same rule
    // as evidence._logical_report_paths with that folder as its base.
    const artifact = manifestPathToFile(stagingDirectory, entry.path);
    const artifactStat = lstat(artifact);
    if (!artifactStat) {
      throw new Error(
        `Staged manifest lists a report path that is not relative to the export folder: ${entry.path}`,
      );
    }
    if (!artifactStat.isFile() || artifactStat.isSymbolicLink()) {
      throw new Error(`Manifest report artifact is not a regular file: ${entry.path}`);
    }
    if (artifactStat.size !== entry.size_bytes) {
      throw new Error(`Manifest size mismatch for staged artifact: ${entry.path}`);
    }
    if (await sha256File(artifact) !== entry.sha256.toLowerCase()) {
      throw new Error(`Manifest hash mismatch for staged artifact: ${entry.path}`);
    }
  }

  const stagedFiles = new Set(
    walkFiles(stagingDirectory).filter((relative) => relative !== manifestName),
  );
  if (stagedFiles.size !== manifestPaths.size
      || [...stagedFiles].some((relative) => !manifestPaths.has(relative))) {
    throw new Error("Staged artifacts and manifest report entries do not match");
  }

  if (!options.noMerge && (options.format === "pdf" || options.format === "html")) {
    const digest = await sha256File(path.join(stagingDirectory, outputName));
    const shaText = await fs.promises.readFile(
      path.join(stagingDirectory, `${outputName}.sha256`), "utf8",
    );
    const sigText = await fs.promises.readFile(
      path.join(stagingDirectory, `${outputName}.sig`), "utf8",
    );
    if (!shaText.includes(digest) || !shaText.includes(outputName)
        || !sigText.includes(digest) || !sigText.includes(outputName)) {
      throw new Error("Staged checksum sidecars do not match the primary report");
    }
  }
}

function rewriteStagedManifestForPublication(
  stagingDirectory: string,
  plan: ArtifactPlan,
): void {
  const manifestPath = path.join(stagingDirectory, "manifest.sha256.json");
  const parsed = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as { reports: unknown[] };
  let changed = false;
  for (const rawEntry of parsed.reports) {
    const entry = rawEntry as { path: string };
    for (const [stagedName, finalName] of plan.publicationNames) {
      if (stagedName === "manifest.sha256.json" || stagedName === finalName) { continue; }
      if (entry.path === stagedName || entry.path.startsWith(`${stagedName}/`)) {
        entry.path = `${finalName}${entry.path.slice(stagedName.length)}`;
        changed = true;
        break;
      }
    }
  }
  if (changed) {
    fs.writeFileSync(manifestPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
  }
}

function removePath(pathname: string): void {
  const stat = lstat(pathname);
  if (!stat) { return; }
  if (stat.isDirectory() && !stat.isSymbolicLink()) {
    fs.rmSync(pathname, { recursive: true, force: true });
  } else {
    fs.unlinkSync(pathname);
  }
}

export class ExportTransaction {
  public readonly stagingDirectory: string;
  public readonly stagedOutputPath: string;
  private readonly finalParent: string;
  private readonly outputName: string;
  private readonly plan: ArtifactPlan;
  private active = true;
  private ownedSplitTrees: SplitTreeOwnership[] = [];

  public constructor(private readonly options: ExportTransactionOptions) {
    const finalOutputPath = path.resolve(options.outputPath);
    this.finalParent = path.dirname(finalOutputPath);
    this.outputName = path.basename(finalOutputPath);
    this.plan = buildArtifactPlan(options);
    validateOutputBoundaries(options, this.plan);
    inspectExistingSplitTrees(this.finalParent, this.plan, options);
    this.stagingDirectory = fs.mkdtempSync(
      path.join(this.finalParent, ".diffinite-export-"),
    );
    this.stagedOutputPath = path.join(this.stagingDirectory, this.outputName);
  }

  /** Python's manifest of the staged run (inputs and outputs), for callers' checks. */
  public get stagedManifestPath(): string {
    return path.join(this.stagingDirectory, "manifest.sha256.json");
  }

  /**
   * Prove that an existing `<stem>_files` tree this export would replace or
   * remove is an unmodified prior Diffinite output (names, exact coverage and
   * SHA-256 against its manifest). Call before the analyzer runs so a refusal
   * costs nothing; publish() repeats it immediately before renaming.
   */
  public async verifyExistingOutputs(): Promise<void> {
    const owned = inspectExistingSplitTrees(this.finalParent, this.plan, this.options);
    for (const ownership of owned) {
      await verifySplitTreeHashes(this.finalParent, ownership);
    }
    this.ownedSplitTrees = owned;
  }

  public abort(): void {
    if (!this.active) { return; }
    this.active = false;
    try {
      removePath(this.stagingDirectory);
    } catch {
      // Never mask the process/publish error or leave its Promise unsettled.
      // The directory is uniquely named and contains no published final path.
    }
  }

  public async publish(options: PublicationOptions = {}): Promise<void> {
    if (!this.active) { throw new Error("Export transaction is no longer active"); }
    const operations: RenameOperations = {
      renameSync: options.renameSync ?? fs.renameSync,
    };
    try {
      throwIfCancellationRequested(options.isCancellationRequested);
      validateOutputBoundaries(this.options, this.plan);
      await validateStagedArtifacts(
        this.stagingDirectory, this.outputName, this.options, this.plan,
      );
      rewriteStagedManifestForPublication(this.stagingDirectory, this.plan);
      throwIfCancellationRequested(options.isCancellationRequested);
      await yieldBeforePublication(options.isCancellationRequested);
      validateOutputBoundaries(this.options, this.plan);
      // Last await before the synchronous rename sequence: ownership and
      // hashes are checked against the final folder as it is now.
      await this.verifyExistingOutputs();
      throwIfCancellationRequested(options.isCancellationRequested);
      this.publishPreparedArtifacts(operations);
    } catch (err) {
      if (err instanceof ExportRollbackError) {
        // Backups are the only remaining recovery source; never delete them.
        this.active = false;
      } else {
        this.abort();
      }
      throw err;
    }
    this.abort();
  }

  private publishPreparedArtifacts(operations: RenameOperations): void {
    const stagedNames = fs.readdirSync(this.stagingDirectory).sort();
    const targetNames = new Set([
      ...stagedNames.map((name) => publicationName(this.plan, name)),
      ...this.plan.removalNames,
    ]);
    if (this.plan.splitTreeName) {
      for (const candidate of this.plan.conditionalRemovalNames) {
        const ownedArtifacts = splitManifestOwnedArtifacts(
          this.finalParent, candidate, this.plan.splitTreeName,
        );
        for (const ownedArtifact of ownedArtifacts ?? []) {
          targetNames.add(ownedArtifact);
        }
      }
    }
    for (const ownership of this.ownedSplitTrees) {
      // Split mode: the tree is already a target. Merged mode: the earlier
      // split tree whose only manifest is being replaced goes with it.
      targetNames.add(ownership.treeName);
    }
    for (const legacyArtifact of legacyOwnedArtifacts(this.finalParent, this.plan, targetNames)) {
      targetNames.add(legacyArtifact);
    }
    const backupDirectory = path.join(this.stagingDirectory, ".rollback");
    fs.mkdirSync(backupDirectory);
    const backups: Array<{ target: string; backup: string }> = [];
    const published: string[] = [];

    try {
      for (const name of [...targetNames].sort()) {
        const target = path.join(this.finalParent, name);
        if (!lstat(target)) { continue; }
        const backup = path.join(backupDirectory, `artifact-${backups.length}`);
        operations.renameSync(target, backup);
        backups.push({ target, backup });
      }
      for (const name of stagedNames) {
        const source = path.join(this.stagingDirectory, name);
        const target = path.join(this.finalParent, publicationName(this.plan, name));
        operations.renameSync(source, target);
        published.push(target);
      }
    } catch (publishError) {
      const rollbackErrors: string[] = [];
      for (const target of [...published].reverse()) {
        try { removePath(target); } catch (err) { rollbackErrors.push(String(err)); }
      }
      for (const { target, backup } of [...backups].reverse()) {
        try { operations.renameSync(backup, target); } catch (err) { rollbackErrors.push(String(err)); }
      }
      if (rollbackErrors.length) {
        throw new ExportRollbackError(
          `Export publication failed (${publishError}); rollback also failed. ` +
          `Recovery artifacts remain in ${backupDirectory}: ${rollbackErrors.join("; ")}`,
        );
      }
      throw publishError;
    }
  }
}

export function createExportTransaction(options: ExportTransactionOptions): ExportTransaction {
  return new ExportTransaction(options);
}
