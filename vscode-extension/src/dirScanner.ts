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

function walkDir(dir: string, baseDir = ""): Record<string, number> {
  const result: Record<string, number> = {};
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      const relPath = path.join(baseDir, entry.name);

      try {
        if (entry.isDirectory()) {
          Object.assign(result, walkDir(fullPath, relPath));
        } else {
          result[relPath.replace(/\\/g, "/")] = fs.statSync(fullPath).size;
        }
      } catch (err) {
        // Skip unreadable files
      }
    }
  } catch (err) {
    // Skip unreadable directories
  }

  return result;
}

export function scanAndEstimate(dirA: string, dirB: string): ScanResult {
  const aFiles = walkDir(dirA);
  const bFiles = walkDir(dirB);

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
    if (relPath in bFiles) {
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
