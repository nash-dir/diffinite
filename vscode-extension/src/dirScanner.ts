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

  // Heuristics (Approximate)
  // Phase 1 (Metrics only)
  // Simple: very fast ratio matching.
  let simplePhase1Secs = Math.max(1, Math.ceil(matchedPairsCount * 0.05));
  // Deep: Simple + full token hashing
  let deepPhase1Secs = simplePhase1Secs + Math.ceil((totalSizeA + totalSizeB) / (1024 * 1024 * 20)); // ~20MB/s hashing

  // Phase 2 (HTML rendering)
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
 * Recalculate estimated Phase 2 time for a subset of files, then apply the dynamic CPU multiplier.
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

  const baseSecs = Math.ceil((complexityScore * 8) + (selectedFiles.length * 0.1));
  const mult = Math.max(0.2, Math.min(cpuMultiplier, 5.0)); // Clamp between 0.2 and 5.0
  return Math.max(1, Math.ceil(baseSecs * mult));
}
