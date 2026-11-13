import * as fs from "fs";
import * as path from "path";

export interface ScanResult {
  fileCountA: number;
  fileCountB: number;
  totalSizeA: number;
  totalSizeB: number;
  matchedPairsCount: number;
  complexityScore: number;
  simpleTimeSeconds: number;
  deepTimeSeconds: number;
  maxPairSizeMB: number;
  simplePhase1Secs: number;
  deepPhase1Secs: number;
}

/** Cooperative cancellation (structurally a vscode.CancellationToken). */
export interface ScanCancellation { readonly isCancellationRequested: boolean; }

/** fnmatch.fnmatchcase for one path component (no "/" inside a component). */
function componentRegExp(pattern: string): RegExp {
  let source = "";
  for (let i = 0; i < pattern.length; i++) {
    const ch = pattern[i];
    if (ch === "*") { source += ".*"; continue; }
    if (ch === "?") { source += "."; continue; }
    if (ch === "[") {
      // As fnmatch.translate: "[!" negates, and a "]" right after "[" or
      // "[!" is a literal member, not the closing bracket.
      let j = i + 1;
      if (pattern[j] === "!") { j++; }
      if (pattern[j] === "]") { j++; }
      const close = pattern.indexOf("]", j);
      if (close !== -1) {
        let body = pattern.slice(i + 1, close);
        const negate = body.startsWith("!");
        if (negate) { body = body.slice(1); }
        body = body.replace(/[\\\]^]/g, "\\$&");
        // "-" is left as is, so ranges such as [a-z] work as in fnmatch.
        source += `[${negate ? "^" : ""}${body}]`;
        i = close;
        continue;
      }
    }
    source += ch.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  }
  return new RegExp(`^${source}$`, "s");
}

function matchSegments(patternSegments: string[], pathSegments: string[]): boolean {
  if (!patternSegments.length) { return !pathSegments.length; }
  const [head, ...rest] = patternSegments;
  if (head === "**") {
    if (!rest.length) { return pathSegments.length >= 1; }
    for (let k = 0; k <= pathSegments.length; k++) {
      if (matchSegments(rest, pathSegments.slice(k))) { return true; }
    }
    return false;
  }
  return pathSegments.length > 0
    && componentRegExp(head).test(pathSegments[0])
    && matchSegments(rest, pathSegments.slice(1));
}

/**
 * Same exclusion rule as collector.should_ignore (gitignore subset, case
 * sensitive): a pattern without "/" matches a component name at any depth;
 * one with "/" is anchored at the root; a trailing "/" means directories only.
 */
export function shouldIgnore(relPath: string, patterns: readonly string[], isDir = false): boolean {
  const parts = relPath.split("/").filter((part) => part);
  if (!parts.length) { return false; }
  for (const raw of patterns) {
    let pattern = raw.trim();
    const dirOnly = pattern.endsWith("/");
    pattern = pattern.replace(/\/+$/, "");
    if (!pattern) { continue; }
    const anchored = pattern.includes("/");
    const segments = pattern.split("/").filter((segment) => segment);
    if (!segments.length) { continue; }
    for (let k = 1; k <= parts.length; k++) {
      const candidateIsDir = k < parts.length || isDir;
      if (dirOnly && !candidateIsDir) { continue; }
      if (anchored) {
        if (matchSegments(segments, parts.slice(0, k))) { return true; }
      } else if (componentRegExp(segments[0]).test(parts[k - 1])) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Asynchronous, cancellable walk that prunes excluded directories like the
 * analyzer does. Links are not followed (the analyzer does not collect them).
 * Returns undefined when canceled.
 */
async function walkDir(
  root: string,
  patterns: readonly string[],
  token?: ScanCancellation,
): Promise<Map<string, number> | undefined> {
  const result = new Map<string, number>();
  const pending: string[] = [""];
  while (pending.length) {
    if (token?.isCancellationRequested) { return undefined; }
    const relDir = pending.pop() as string;
    let entries: fs.Dirent[];
    try {
      entries = await fs.promises.readdir(path.join(root, relDir), { withFileTypes: true });
    } catch {
      continue; // Unreadable directory: the analyzer reports it; the estimate skips it.
    }
    for (const entry of entries) {
      const relPath = relDir ? `${relDir}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        if (!shouldIgnore(relPath, patterns, true)) { pending.push(relPath); }
      } else if (entry.isFile() && !shouldIgnore(relPath, patterns, false)) {
        try {
          result.set(relPath, (await fs.promises.stat(path.join(root, relPath))).size);
        } catch {
          // Unreadable file: skipped for the estimate only.
        }
      }
    }
  }
  return result;
}

/**
 * Rough pre-run estimate. Applies the same exclusion rules the analyzer will
 * get, yields to the extension host between directories, and returns
 * undefined if canceled.
 */
export async function scanAndEstimate(
  dirA: string,
  dirB: string,
  ignorePatterns: readonly string[] = [],
  token?: ScanCancellation,
): Promise<ScanResult | undefined> {
  const aMap = await walkDir(dirA, ignorePatterns, token);
  const bMap = aMap && await walkDir(dirB, ignorePatterns, token);
  if (!aMap || !bMap) { return undefined; }
  const aFiles = Object.fromEntries(aMap);
  const bFiles = Object.fromEntries(bMap);

  let totalSizeA = 0;
  let fileCountA = 0;
  for (const size of Object.values(aFiles)) {
    totalSizeA += size;
    fileCountA++;
  }

  let totalSizeB = 0;
  let fileCountB = 0;
  for (const size of Object.values(bFiles)) {
    totalSizeB += size;
    fileCountB++;
  }

  let matchedPairsCount = 0;
  let complexityScore = 0;
  let maxPairSizeMB = 0;

  for (const [relPath, sizeA] of Object.entries(aFiles)) {
    if (Object.prototype.hasOwnProperty.call(bFiles, relPath)) {
      const sizeB = bFiles[relPath];
      matchedPairsCount++;
      const mbA = sizeA / (1024 * 1024);
      const mbB = sizeB / (1024 * 1024);
      complexityScore += mbA * mbB;
      maxPairSizeMB = Math.max(maxPairSizeMB, Math.max(mbA, mbB));
    }
  }

  // Rough progress-message heuristics only. None of the constants below was
  // measured or benchmarked; they only size the "~N s" hint shown before a
  // run and never affect analysis results. Pairs are counted by identical
  // relative path only (Python's fuzzy pairing and N:M cost are not modelled).
  // Phase 1 (Metrics only)
  // Simple: 0.05 s per same-path pair — rough guess, not measured.
  let simplePhase1Secs = Math.max(1, Math.ceil(matchedPairsCount * 0.05));
  // Deep: Simple + token hashing at an assumed 20 MB/s — rough guess, not measured.
  let deepPhase1Secs = simplePhase1Secs + Math.ceil((totalSizeA + totalSizeB) / (1024 * 1024 * 20));

  // Phase 2 (HTML rendering): 8 s per MB(A)*MB(B) plus 0.1 s per pair — rough guesses, not measured.
  let phase2BaseSecs = Math.ceil((complexityScore * 8) + (matchedPairsCount * 0.1));

  let simpleTimeSeconds = simplePhase1Secs + phase2BaseSecs;
  let deepTimeSeconds = deepPhase1Secs + phase2BaseSecs;

  return {
    fileCountA,
    fileCountB,
    totalSizeA,
    totalSizeB,
    matchedPairsCount,
    complexityScore,
    simpleTimeSeconds,
    deepTimeSeconds,
    maxPairSizeMB,
    simplePhase1Secs,
    deepPhase1Secs
  };
}

/**
 * Rough Phase 2 time hint for a subset of files, scaled by the ratio of actual
 * to guessed Phase 1 time. Display-only; not a measured or calibrated model.
 */
export function estimatePhase2Time(selectedFiles: string[], dirA: string, dirB: string, cpuMultiplier: number): number {
  let complexityScore = 0;
  for (const f of selectedFiles) {
    const pA = path.join(dirA, f);
    const pB = path.join(dirB, f);
    try {
      const sizeA = fs.existsSync(pA) ? fs.statSync(pA).size : 0;
      const sizeB = fs.existsSync(pB) ? fs.statSync(pB).size : 0;
      const mbA = sizeA / (1024 * 1024);
      const mbB = sizeB / (1024 * 1024);
      complexityScore += mbA * mbB;
    } catch { 
      // Ignore unreadable
    }
  }

  // Same unmeasured per-MB^2 / per-pair guesses as scanAndEstimate().
  const baseSecs = Math.ceil((complexityScore * 8) + (selectedFiles.length * 0.1));
  // Clamp 0.2-5.0: arbitrary bound so one odd Phase 1 timing cannot make the hint absurd; not measured.
  const mult = Math.max(0.2, Math.min(cpuMultiplier, 5.0));
  return Math.max(1, Math.ceil(baseSecs * mult));
}
