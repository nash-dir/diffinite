/**
 * Runner — executes the diffinite CLI via subprocess and parses JSON output.
 *
 * Binary resolution order:
 *   1. Bundled standalone binary (bin/{platform}/diffinite[.exe])
 *   2. Fallback: Python interpreter (`python -m diffinite`)
 */
import * as vscode from "vscode";
import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { getPythonPath } from "./config";

/** Options collected from the GUI panel. */
export interface DiffiniteOptions {
  mode: "simple" | "deep";
  noComments: boolean;
  byWord: boolean;
  normalize: boolean;
  collapseIdentical: boolean;
  noAutojunk: boolean;
  threshold: number;
  kGram: number;
  window: number;
  thresholdDeep: number;
  pageNumber: boolean;
  fileNumber: boolean;
  batesNumber: boolean;
  hash: boolean;
}

/** Structure of the JSON report produced by `diffinite --report-json`. */
export interface DiffiniteReport {
  metadata: {
    exec_mode: string;
    k: number;
    w: number;
    threshold: number;
    autojunk: boolean;
  } | null;
  dir_a: string;
  dir_b: string;
  comparison_unit: string;
  comment_mode: string;
  summary: {
    matched_pairs: number;
    unmatched_a: number;
    unmatched_b: number;
  };
  results: Array<{
    file_a: string;
    file_b: string;
    name_similarity: number;
    ratio: number;
    additions: number;
    deletions: number;
    html_diff: string;
    error: string | null;
  }>;
  deep_results: Array<{
    file_a: string;
    fingerprint_count_a: number;
    matches: Array<{
      file_b: string;
      shared_hashes: number;
      jaccard: number;
    }>;
  }> | null;
  unmatched_a: string[];
  unmatched_b: string[];
}

/** Default analysis options. */
export function defaultOptions(): DiffiniteOptions {
  return {
    mode: "deep",
    noComments: false,
    byWord: false,
    normalize: false,
    collapseIdentical: false,
    noAutojunk: false,
    threshold: 60,
    kGram: 5,
    window: 4,
    thresholdDeep: 0.05,
    pageNumber: true,
    fileNumber: true,
    batesNumber: true,
    hash: true,
  };
}

// ---------------------------------------------------------------------------
// Binary resolution
// ---------------------------------------------------------------------------

/** Platform directory names matching CI build matrix. */
const PLATFORM_MAP: Record<string, string> = {
  win32: "win-x64",
  linux: "linux-x64",
  darwin: "darwin-x64",
};

/**
 * Resolve the diffinite executable path.
 *
 * Returns { exe, args } where:
 *   - Bundled binary: exe = "/path/to/bin/win-x64/diffinite.exe", args = []
 *   - Python fallback: exe = "python", args = ["-m", "diffinite"]
 */
function resolveBinary(): { exe: string; prefixArgs: string[] } {
  const ext = process.platform === "win32" ? ".exe" : "";
  const platformDir = PLATFORM_MAP[process.platform];

  if (platformDir) {
    // __dirname is "out/", binary is in "bin/{platform}/"
    const bundled = path.join(__dirname, "..", "bin", platformDir, `diffinite${ext}`);
    if (fs.existsSync(bundled)) {
      return { exe: bundled, prefixArgs: [] };
    }
  }

  // Fallback to Python interpreter
  const pythonPath = getPythonPath();
  return { exe: pythonPath, prefixArgs: ["-m", "diffinite"] };
}

/**
 * Build CLI arguments from GUI options.
 */
function buildArgs(opts: DiffiniteOptions): string[] {
  const args: string[] = ["--mode", opts.mode];
  if (opts.noComments) { args.push("--no-comments"); }
  if (opts.byWord) { args.push("--by-word"); }
  if (opts.normalize) { args.push("--normalize"); }
  if (opts.collapseIdentical) { args.push("--collapse-identical"); }
  if (opts.noAutojunk) { args.push("--no-autojunk"); }
  args.push("--threshold", String(opts.threshold));
  args.push("--k-gram", String(opts.kGram));
  args.push("--window", String(opts.window));
  args.push("--threshold-deep", String(opts.thresholdDeep));
  if (opts.pageNumber) { args.push("--page-number"); }
  if (opts.fileNumber) { args.push("--file-number"); }
  if (opts.batesNumber) { args.push("--bates-number"); }
  if (opts.hash) { args.push("--hash"); }
  return args;
}

/**
 * Spawn diffinite process with the resolved binary.
 */
function spawnDiffinite(
  extraArgs: string[]
): ReturnType<typeof spawn> {
  const { exe, prefixArgs } = resolveBinary();
  const allArgs = [...prefixArgs, ...extraArgs];
  console.log('[Diffinite] Spawning:', exe, allArgs.join(' '));
  return spawn(exe, allArgs);
}

/**
 * Run diffinite CLI and return parsed JSON report.
 */
export async function runAnalysis(
  dirA: string,
  dirB: string,
  opts: DiffiniteOptions,
  progress: vscode.Progress<{ message?: string; increment?: number }>
): Promise<DiffiniteReport> {
  const tmpJson = path.join(os.tmpdir(), `diffinite_${Date.now()}.json`);

  const cliArgs = [
    dirA, dirB,
    "--report-json", tmpJson,
    ...buildArgs(opts),
  ];

  progress.report({ message: "Running diffinite analysis…" });

  return new Promise<DiffiniteReport>((resolve, reject) => {
    const proc = spawnDiffinite(cliArgs);

    let stderr = "";
    proc.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on("close", (code) => {
      console.log('[Diffinite] Process exited with code:', code);
      if (code !== 0) {
        console.error('[Diffinite] stderr:', stderr);
        reject(new Error(`diffinite exited with code ${code}:\n${stderr}`));
        return;
      }
      try {
        const raw = fs.readFileSync(tmpJson, "utf-8");
        const report: DiffiniteReport = JSON.parse(raw);
        try { fs.unlinkSync(tmpJson); } catch { /* ignore */ }
        resolve(report);
      } catch (err) {
        reject(new Error(`Failed to parse JSON report: ${err}`));
      }
    });

    proc.on("error", (err) => {
      reject(new Error(
        `Failed to start diffinite. Check that the bundled binary exists ` +
        `or set diffinite.pythonPath in settings.\n${err.message}`
      ));
    });
  });
}

/**
 * Run diffinite CLI to export a report in a specific format.
 */
export async function runExport(
  dirA: string,
  dirB: string,
  opts: DiffiniteOptions,
  format: "pdf" | "html" | "md",
  outputPath: string,
  progress: vscode.Progress<{ message?: string; increment?: number }>
): Promise<void> {
  const formatFlag = `--report-${format}`;

  const cliArgs = [
    dirA, dirB,
    formatFlag, outputPath,
    ...buildArgs(opts),
  ];

  progress.report({ message: `Exporting ${format.toUpperCase()} report…` });

  return new Promise<void>((resolve, reject) => {
    const proc = spawnDiffinite(cliArgs);

    let stderr = "";
    proc.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`diffinite export failed (code ${code}):\n${stderr}`));
        return;
      }
      resolve();
    });

    proc.on("error", (err) => {
      reject(new Error(`Failed to start diffinite: ${err.message}`));
    });
  });
}
