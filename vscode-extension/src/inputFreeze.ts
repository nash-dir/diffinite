/**
 * Freeze the inputs of a reviewed analysis.
 *
 * Phase 1 reads ~/.diffignore once. Phase 2 and every export receive those
 * exact bytes as their --ignore-file, and the input SHA-256 values Python
 * records in manifest.sha256.json are compared between runs, so a report
 * cannot silently cover different files than the ones the user reviewed.
 * Pure Node module (no VS Code API) so it can be unit-tested.
 */
import { createHash } from "crypto";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import type { DiffiniteReport, IgnoreSnapshot, InputManifest } from "./analysisModel";
import { createTempJsonFile, TempJsonFile } from "./tempFiles";
import { plural } from "./labels";

export function defaultIgnoreFilePath(): string {
  return path.join(os.homedir(), ".diffignore");
}

/** The rules Python applies: non-empty lines not starting with "#" (pipeline.py). */
export function ignoreRules(text: string): string[] {
  return text.split(/\r\n|\r|\n/).map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#"));
}

/** Read the exclusion list once. null when the file does not exist. */
export function readIgnoreSnapshot(ignorePath = defaultIgnoreFilePath()): IgnoreSnapshot | null {
  let bytes: Buffer;
  try {
    bytes = fs.readFileSync(ignorePath);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") { return null; }
    throw new Error(`Cannot read the exclusion list ${ignorePath}: ${err}`);
  }
  return {
    sourcePath: ignorePath,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    base64: bytes.toString("base64"),
    ruleCount: ignoreRules(bytes.toString("utf8")).length,
  };
}

export function snapshotRules(snapshot: IgnoreSnapshot | null): string[] {
  return snapshot ? ignoreRules(Buffer.from(snapshot.base64, "base64").toString("utf8")) : [];
}

/** Write the frozen bytes to a private temp file for one CLI run. */
export function writeIgnoreSnapshot(snapshot: IgnoreSnapshot): TempJsonFile {
  const temporary = createTempJsonFile("diffinite-ignore-");
  try {
    fs.writeFileSync(temporary.filePath, Buffer.from(snapshot.base64, "base64"));
  } catch (err) {
    temporary.cleanup();
    throw err;
  }
  return temporary;
}

function sideHashes(value: unknown, side: string): Record<string, string> {
  const files = value !== null && typeof value === "object"
    ? (value as { files?: unknown }).files : undefined;
  if (!Array.isArray(files)) {
    throw new Error(`Input manifest ${side}.files is missing`);
  }
  const hashes: Record<string, string> = {};
  for (const entry of files) {
    const { path: rel, sha256 } = (entry ?? {}) as { path?: unknown; sha256?: unknown };
    if (typeof rel !== "string" || typeof sha256 !== "string") {
      throw new Error(`Input manifest ${side} has an invalid file entry`);
    }
    hashes[rel] = sha256.toLowerCase();
  }
  return hashes;
}

/** Extract per-file input hashes from a parsed manifest.sha256.json. */
export function parseInputManifest(raw: unknown): InputManifest {
  const manifest = raw !== null && typeof raw === "object" ? raw as Record<string, unknown> : {};
  return { a: sideHashes(manifest.source_a, "source_a"), b: sideHashes(manifest.source_b, "source_b") };
}

/** Read a run's manifest; null when it is missing or unreadable. */
export async function readInputManifest(manifestPath: string): Promise<InputManifest | null> {
  try {
    return parseInputManifest(JSON.parse(await fs.promises.readFile(manifestPath, "utf8")));
  } catch {
    return null;
  }
}

// Display limit only: how many file names a warning lists before "and N more".
// It never changes which differences are detected or counted.
const LISTED_DIFFERENCES = 5;

/** Human-readable differences between two input sets (at most `limit` per side). */
export function diffInputManifests(
  before: InputManifest, after: InputManifest, limit = LISTED_DIFFERENCES,
): string[] {
  const differences: string[] = [];
  for (const side of ["a", "b"] as const) {
    const label = side.toUpperCase();
    const changed: string[] = [];
    const keys = new Set([...Object.keys(before[side]), ...Object.keys(after[side])]);
    for (const rel of [...keys].sort()) {
      const old = before[side][rel];
      const now = after[side][rel];
      if (old === now) { continue; }
      changed.push(old === undefined ? `${label}:${rel} (added)`
        : now === undefined ? `${label}:${rel} (removed or now excluded)`
        : `${label}:${rel} (content changed)`);
    }
    if (changed.length) {
      const shown = changed.slice(0, limit).join(", ");
      differences.push(changed.length > limit
        ? `${shown} and ${plural(changed.length - limit, "more input file change")}`
        : shown);
    }
  }
  return differences;
}

export interface ReviewedRun {
  report: DiffiniteReport;
  inputs: InputManifest | null;
}

function pairPartner(report: DiffiniteReport, fileA: string): string | null {
  return report.results.find((row) => row.file_a === fileA)?.file_b ?? null;
}

function deepPartners(report: DiffiniteReport, fileA: string): string {
  const entry = report.deep_results.find((row) => row.file_a === fileA);
  return entry ? entry.matches.map((match) => match.file_b).sort().join("\n") : "";
}

/**
 * Compare the Phase-2 run with the Phase-1 run the user reviewed. Returns a
 * list of discrepancies; empty when Phase 2 analysed the same inputs with the
 * same exclusion list and paired every selected A file as reviewed.
 */
export function compareReviewedRuns(
  reviewed: ReviewedRun,
  final: ReviewedRun,
  selectedFilesA: readonly string[],
  expectedIgnoreSha256: string | null,
): string[] {
  const problems: string[] = [];
  for (const [label, run] of [["Phase 1", reviewed], ["Phase 2", final]] as const) {
    if (run.report.metadata.ignore_file_sha256 !== expectedIgnoreSha256) {
      problems.push(`${label} did not use the exclusion list captured when the analysis started.`);
    }
  }
  if (!reviewed.inputs || !final.inputs) {
    problems.push("The input file hashes of one of the runs could not be read, so unchanged inputs cannot be confirmed.");
  } else {
    const changes = diffInputManifests(reviewed.inputs, final.inputs);
    if (changes.length) {
      problems.push(`Source files changed between the review and the report: ${changes.join("; ")}.`);
    }
  }
  const mismatched: string[] = [];
  for (const fileA of selectedFilesA) {
    const before = pairPartner(reviewed.report, fileA);
    const after = pairPartner(final.report, fileA);
    if (before !== after) {
      mismatched.push(`${fileA}: reviewed with ${before ?? "no 1:1 pair"}, report has ${after ?? "no 1:1 pair"}`);
    } else if (deepPartners(reviewed.report, fileA) !== deepPartners(final.report, fileA)) {
      mismatched.push(`${fileA}: Deep Compare matches differ from the reviewed ones`);
    }
  }
  if (mismatched.length) {
    const shown = mismatched.slice(0, LISTED_DIFFERENCES).join("; ");
    const more = mismatched.length - LISTED_DIFFERENCES;
    problems.push(`Pairing differs from the reviewed selection: ${shown}` +
      (more > 0 ? ` and ${more} more` : "") + ".");
  }
  return problems;
}
