/**
 * Runner — executes the diffinite CLI via subprocess and parses JSON output.
 *
 * Resolution order:
 *   1. (Windows) Bundled Embeddable Python (bin/python/python.exe -m diffinite)
 *   2. Fallback: System Python interpreter (`python -m diffinite`)
 */
import * as vscode from "vscode";
import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { getPythonPath } from "./config";
import { createTempJsonFile } from "./tempFiles";
import {
  buildCoreArgs,
  defaultAnalysisOptions,
  DiffiniteOptions,
  DiffiniteReport,
  parseLiveReport,
} from "./analysisModel";
import { ActiveProcessRegistry, waitForProcessClose } from "./processRegistry";
import { createExportTransaction } from "./exportTransaction";

export type { DiffiniteOptions, DiffiniteReport } from "./analysisModel";

type DiffiniteProcess = ReturnType<typeof spawn>;
const activeProcesses = new ActiveProcessRegistry<DiffiniteProcess>();
// VS Code caps deactivation at 5s; 4s leaves its final second for cleanup and log flushing.
// Source: microsoft/vscode extHostExtensionService.ts (`Promise.race([timeout(5000), ...])`).
const PROCESS_TERMINATION_TIMEOUT_MS = 4_000;
// Display limit only: enough for a full Python traceback, small enough to bound memory.
const STDERR_TAIL_CHARS = 8_192;

interface ProcessTerminationResult {
  closed: boolean;
  stillRunning: boolean;
  pid?: number;
}

/** Default analysis options. */
export function defaultOptions(): DiffiniteOptions {
  return defaultAnalysisOptions();
}

// ---------------------------------------------------------------------------
// Binary resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the diffinite executable path.
 *
 * Resolution order:
 *   1. (Windows) Bundled Embeddable Python: bin/python/python.exe -m diffinite
 *      → No PyInstaller, no antivirus false-positives.
 *   2. System Python fallback: python -m diffinite (all platforms)
 */
function resolveBinary(): { exe: string; prefixArgs: string[] } {
  // Windows: check for bundled Embeddable Python
  if (process.platform === "win32") {
    const bundledPython = path.join(__dirname, "..", "bin", "python", "python.exe");
    if (fs.existsSync(bundledPython)) {
      return { exe: bundledPython, prefixArgs: ["-I", "-m", "diffinite"] };
    }
  }

  // Fallback to system Python interpreter (all platforms)
  const pythonPath = getPythonPath();
  return { exe: pythonPath, prefixArgs: ["-I", "-m", "diffinite"] };
}

/**
 * Build CLI arguments from GUI options.
 */
function buildArgs(opts: DiffiniteOptions): string[] {
  const args = buildCoreArgs(opts);
  // Auto-inject built-in ignore file if it exists
  const defaultIgnoreFile = path.join(os.homedir(), ".diffignore");
  if (fs.existsSync(defaultIgnoreFile)) {
    args.push("--ignore-file", defaultIgnoreFile);
  }

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
  // Do not log source/report paths: they can contain privileged case metadata.
  console.log('[Diffinite] Starting local analyzer:', path.basename(exe));
  
  // Dev mode injection removed (L3): The Windows Embedded Python ignores
  // PYTHONPATH by design if a ._pth file exists. If running via system Python,
  // standard rules apply. It's safer to rely on the properly installed package
  // rather than dynamic runtime patching which causes silent fallbacks.
  const env = process.env;

  const proc = spawn(exe, allArgs, {
    env,
    windowsHide: true,
    // A separate POSIX process group lets cancellation reach worker children.
    detached: os.platform() !== "win32",
  });
  activeProcesses.track(proc);
  return proc;
}

function forceDirectProcessKill(proc: DiffiniteProcess): void {
  try { proc.kill("SIGKILL"); } catch { /* logged if it remains alive */ }
}

function isProcessTreeStillRunning(proc: DiffiniteProcess): boolean {
  if (proc.pid === undefined) {
    return proc.exitCode === null && proc.signalCode === null;
  }
  try {
    // POSIX children are launched in their own group; probe the group so a
    // surviving worker is detected even if the Python parent has exited.
    process.kill(os.platform() === "win32" ? proc.pid : -proc.pid, 0);
    return true;
  } catch (err) {
    return (err as NodeJS.ErrnoException).code !== "ESRCH";
  }
}

function detachUnresponsiveProcess(proc: DiffiniteProcess): void {
  proc.stdout?.removeAllListeners();
  proc.stderr?.removeAllListeners();
  proc.stdin?.removeAllListeners();
  proc.stdout?.destroy();
  proc.stderr?.destroy();
  proc.stdin?.destroy();
  proc.removeAllListeners();
  proc.once("error", (err) => {
    console.warn(`[Diffinite] Detached analyzer process later reported an error: ${err.message}`);
  });
  proc.unref();
}

async function terminateProcessTree(proc: DiffiniteProcess): Promise<ProcessTerminationResult> {
  if (proc.exitCode !== null || proc.signalCode !== null) {
    activeProcesses.release(proc);
    return { closed: true, stillRunning: false, pid: proc.pid };
  }
  const closedPromise = waitForProcessClose(proc, PROCESS_TERMINATION_TIMEOUT_MS);
  let windowsKiller: ReturnType<typeof spawn> | undefined;

  if (os.platform() === "win32" && proc.pid) {
    // Argument-array spawn avoids shell interpolation of the PID. Awaiting the
    // target close (below) prevents cleanup from racing worker termination.
    const systemRoot = process.env.SystemRoot;
    try {
      if (!systemRoot) {
        throw new Error("SystemRoot is unavailable");
      }
      // Use the OS-owned absolute path so a workspace/PATH taskkill.exe cannot run.
      const taskkillPath = path.join(systemRoot, "System32", "taskkill.exe");
      windowsKiller = spawn(taskkillPath, ["/pid", String(proc.pid), "/t", "/f"], {
        windowsHide: true,
        stdio: "ignore",
      });
      windowsKiller.once("error", () => {
        forceDirectProcessKill(proc);
      });
      windowsKiller.once("close", (code) => {
        if (code !== 0) { forceDirectProcessKill(proc); }
      });
    } catch {
      forceDirectProcessKill(proc);
    }
  } else if (proc.pid) {
    try {
      // Cancellation is an explicit forced stop. SIGKILL mirrors taskkill /f
      // and guarantees the whole dedicated POSIX worker group cannot linger.
      process.kill(-proc.pid, "SIGKILL");
    } catch {
      forceDirectProcessKill(proc);
    }
  } else {
    forceDirectProcessKill(proc);
  }

  const closed = await closedPromise;
  if (!closed) {
    // Retry the direct handle if the tree command failed or never completed.
    forceDirectProcessKill(proc);
  }
  if (windowsKiller?.exitCode === null) {
    try { windowsKiller.kill("SIGKILL"); } catch { /* helper already exited */ }
    windowsKiller.unref();
  }

  const stillRunning = !closed && isProcessTreeStillRunning(proc);
  if (!closed) {
    if (stillRunning) {
      console.warn(
        `[Diffinite] Analyzer process${proc.pid ? ` PID ${proc.pid}` : ""} is still running ` +
        `after the ${PROCESS_TERMINATION_TIMEOUT_MS}ms forced-shutdown timeout. ` +
        "Close it with the operating system process manager.",
      );
    } else {
      console.warn(
        `[Diffinite] Analyzer process${proc.pid ? ` PID ${proc.pid}` : ""} exited without ` +
        "emitting close; releasing extension resources.",
      );
    }
    detachUnresponsiveProcess(proc);
  }
  activeProcesses.release(proc);
  return { closed, stillRunning, pid: proc.pid };
}

function cancellationError(
  operation: "Analysis" | "Export",
  result: ProcessTerminationResult,
): Error {
  const preserved = operation === "Export" ? " Existing output was preserved." : "";
  if (result.stillRunning) {
    return new Error(
      `${operation} cancelled, but analyzer${result.pid ? ` PID ${result.pid}` : ""} is still ` +
      `running after forced termination. Close it with the operating system process manager.${preserved}`,
    );
  }
  if (!result.closed) {
    return new Error(
      `${operation} cancelled; the analyzer did not emit a close event before timeout.${preserved}`,
    );
  }
  return new Error(`${operation} cancelled by user.${preserved}`);
}

/** Terminate every analyzer still owned by this extension host. */
export async function terminateAllProcesses(): Promise<void> {
  try {
    await activeProcesses.terminateAll(async (proc) => {
      await terminateProcessTree(proc);
    });
  } catch (err) {
    // Never make VS Code deactivation wait on or reject for a broken child.
    console.warn(`[Diffinite] Analyzer shutdown completed with errors: ${err}`);
  }
}

/**
 * Run diffinite CLI and return parsed JSON report.
 */
export async function runAnalysis(
  dirA: string,
  dirB: string,
  opts: DiffiniteOptions,
  progress: vscode.Progress<{ message?: string; increment?: number }>,
  token?: vscode.CancellationToken
): Promise<DiffiniteReport> {
  const temporary = createTempJsonFile("diffinite-report-");
  const tmpJson = temporary.filePath;
  const cleanupTmp = temporary.cleanup;

  // Options first, then '--', then the positional directories. The '--' sentinel
  // stops argparse treating a path that begins with '-' as an option.
  const cliArgs = [
    "--report-json", tmpJson,
    ...buildArgs(opts),
    "--", dirA, dirB,
  ];

  progress.report({ message: "Running diffinite analysis…" });

  return new Promise<DiffiniteReport>((resolve, reject) => {
    let proc: DiffiniteProcess;
    try {
      proc = spawnDiffinite(cliArgs);
    } catch (err) {
      cleanupTmp();
      reject(new Error(`Failed to start diffinite: ${err instanceof Error ? err.message : String(err)}`));
      return;
    }
    let settled = false;
    let cancelled = false;
    let cancellationDisposable: vscode.Disposable | undefined;
    let stderrData = "";
    const workerProgress: Record<string, { current: number, total: number }> = {};
    let lastReportedPct = 0;

    const rejectOnce = (error: Error): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      cleanupTmp();
      reject(error);
    };

    const resolveOnce = (report: DiffiniteReport): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      cleanupTmp();
      resolve(report);
    };

    proc.stderr?.on("data", (chunk: Buffer) => {
      // Keep a bounded tail so a noisy child cannot exhaust the extension host.
      // Python tracebacks place the final exception last.
      stderrData = (stderrData + chunk.toString()).slice(-STDERR_TAIL_CHARS);
    });

    proc.stdout?.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      const lines = text.split(/\r?\n/);
      let progressUpdated = false;
      for (const line of lines) {
        // [Worker-1] 5/20 (25%)
        const match = line.match(/\[Worker-?(\d+)\]\s+(\d+)\/(\d+)/i);
        if (match) {
          const wId = match[1];
          const current = parseInt(match[2], 10);
          const total = parseInt(match[3], 10);
          workerProgress[wId] = { current, total };
          progressUpdated = true;
        } else if (line.includes("[INFO] Step")) {
          // Pass significant pipeline steps directly to status
          const stepMsg = line.split("[INFO]")[1].trim();
          progress.report({ message: stepMsg });
        }
      }

      if (progressUpdated) {
        let sumCurrent = 0;
        let sumTotal = 0;
        for (const w of Object.values(workerProgress)) {
          sumCurrent += w.current;
          sumTotal += w.total;
        }
        
        let overallPct = 0;
        if (sumTotal > 0) {
          overallPct = Math.floor((sumCurrent / sumTotal) * 100);
        }
        
        const increment = overallPct - lastReportedPct;
        const wkeys = Object.keys(workerProgress).sort((a,b) => Number(a) - Number(b));
        const msg = wkeys.map(k => `W${k} [${workerProgress[k].current}/${workerProgress[k].total}]`).join(" | ");
        
        if (increment > 0) {
          progress.report({ increment, message: `Rendering... ${msg} (${overallPct}%)` });
          lastReportedPct = overallPct;
        } else {
          progress.report({ message: `Rendering... ${msg} (${overallPct}%)` });
        }
      }
    });

    proc.on("close", async (code) => {
      console.log('[Diffinite] Process exited with code:', code);
      if (cancelled) {
        rejectOnce(new Error("Analysis cancelled by user."));
        return;
      }
      if (code !== 0) {
        rejectOnce(new Error(`diffinite exited with code ${code}:\n${stderrData}`));
        return;
      }
      try {
        // Phase-2 JSON embeds full html_diff per file and can be large, so read
        // it off the UI thread to avoid freezing VS Code on big selections.
        const raw = await fs.promises.readFile(tmpJson, "utf-8");
        const report = parseLiveReport(JSON.parse(raw));
        if (cancelled) {
          rejectOnce(new Error("Analysis cancelled by user."));
        } else {
          resolveOnce(report);
        }
      } catch (err) {
        rejectOnce(new Error(`Failed to parse JSON report: ${err}`));
      }
    });

    proc.on("error", (err) => {
      rejectOnce(cancelled
        ? new Error("Analysis cancelled by user.")
        : new Error(
          `Failed to start diffinite. Check that the bundled binary exists ` +
          `or set diffinite.pythonPath in settings.\n${err.message}`
        ));
    });

    const cancel = (): void => {
      if (settled || cancelled) { return; }
      cancelled = true;
      progress.report({ message: "Cancelling analysis and stopping workers…" });
      void terminateProcessTree(proc).then(
        (result) => rejectOnce(cancellationError("Analysis", result)),
        (err) => rejectOnce(new Error(`Analysis cancellation cleanup failed: ${err}`)),
      );
    };
    if (token?.isCancellationRequested) {
      cancel();
    } else if (token) {
      cancellationDisposable = token.onCancellationRequested(cancel);
    }
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
  progress: vscode.Progress<{ message?: string; increment?: number }>,
  token?: vscode.CancellationToken
): Promise<void> {
  const formatFlag = `--report-${format}`;
  const exportTransaction = createExportTransaction({
    dirA,
    dirB,
    outputPath,
    format,
    noMerge: opts.noMerge,
    uncomparedFiles: opts.uncomparedFiles,
    batesNumber: opts.batesNumber,
  });

  let selectionFilter: ReturnType<typeof createTempJsonFile> | undefined;
  const exportOptions = { ...opts };
  try {
    if (opts.selectedFiles !== undefined) {
      if (opts.selectedFiles.length === 0) {
        throw new Error("Cannot export an empty Phase-2 selection");
      }
      selectionFilter = createTempJsonFile("diffinite-export-filter-");
      fs.writeFileSync(
        selectionFilter.filePath,
        JSON.stringify(opts.selectedFiles),
        "utf8",
      );
      exportOptions.filterJson = selectionFilter.filePath;
    }
  } catch (err) {
    selectionFilter?.cleanup();
    exportTransaction.abort();
    throw err;
  }

  const cliArgs = [
    formatFlag, exportTransaction.stagedOutputPath,
    ...buildArgs(exportOptions),
    "--", dirA, dirB,
  ];

  progress.report({ message: `Exporting ${format.toUpperCase()} report…` });

  return new Promise<void>((resolve, reject) => {
    let proc: DiffiniteProcess;
    try {
      proc = spawnDiffinite(cliArgs);
    } catch (err) {
      selectionFilter?.cleanup();
      exportTransaction.abort();
      reject(new Error(`Failed to start diffinite: ${err instanceof Error ? err.message : String(err)}`));
      return;
    }
    let settled = false;
    let cancelled = false;
    let cancellationDisposable: vscode.Disposable | undefined;
    let stderr = "";
    const workerProgress: Record<string, string> = {};

    const rejectOnce = (error: Error): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      selectionFilter?.cleanup();
      exportTransaction.abort();
      reject(error);
    };
    const resolveOnce = (): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      selectionFilter?.cleanup();
      resolve();
    };

    proc.stderr?.on("data", (chunk: Buffer) => {
      // See runAnalysis: retain useful terminal context without unbounded growth.
      stderr = chunk.toString();
    });

    proc.stdout?.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      
      const lines = text.split(/\r?\n/);
      for (const line of lines) {
        const match = line.match(/\[Worker-?(\d+)\]\s+(.*)/i);
        if (match) {
          workerProgress[match[1]] = match[2].trim();
          
          const wkeys = Object.keys(workerProgress).sort((a,b) => Number(a) - Number(b));
          const msg = wkeys.map(k => `W${k} [${workerProgress[k]}]`).join(" | ");
          progress.report({ message: `Rendering... ${msg}` });
        }
      }
    });

    proc.on("close", async (code) => {
      if (cancelled) {
        rejectOnce(new Error("Export cancelled by user. Existing output was preserved."));
        return;
      }
      if (code !== 0) {
        rejectOnce(new Error(`diffinite export failed (code ${code}):\n${stderr}`));
        return;
      }
      try {
        await exportTransaction.publish({
          isCancellationRequested: () => cancelled || token?.isCancellationRequested === true,
        });
        resolveOnce();
      } catch (err) {
        rejectOnce(cancelled || token?.isCancellationRequested
          ? new Error("Export cancelled by user. Existing output was preserved.")
          : new Error(`Failed to publish complete export artifacts: ${err}`));
      }
    });

    proc.on("error", (err) => {
      rejectOnce(cancelled
        ? new Error("Export cancelled by user.")
        : new Error(`Failed to start diffinite: ${err.message}`));
    });

    const cancel = (): void => {
      if (settled || cancelled) { return; }
      cancelled = true;
      progress.report({ message: "Cancelling export and stopping workers…" });
      void terminateProcessTree(proc).then(
        (result) => rejectOnce(cancellationError("Export", result)),
        (err) => rejectOnce(new Error(`Export cancellation cleanup failed: ${err}`)),
      );
    };
    if (token?.isCancellationRequested) {
      cancel();
    } else if (token) {
      cancellationDisposable = token.onCancellationRequested(cancel);
    }
  });
}
