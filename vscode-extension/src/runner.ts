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
  InputManifest,
  parseLiveReport,
} from "./analysisModel";
import { ActiveProcessRegistry, waitForProcessClose } from "./processRegistry";
import { createExportTransaction } from "./exportTransaction";
import {
  diffInputManifests, readIgnoreSnapshot, readInputManifest, writeIgnoreSnapshot,
} from "./inputFreeze";
import { LineBuffer, pipelineStepMessage } from "./lineBuffer";
import { countLabel, plural } from "./labels";

/** Progress text for the rendering workers: "Rendering: 5 of 20 pairs (25%)". */
export function renderProgressMessage(done: number, total: number): string {
  const pct = total > 0 ? Math.floor((done / total) * 100) : 0;
  return `Rendering: ${countLabel(done)} of ${plural(total, "pair")} (${pct}%)`;
}

export type { DiffiniteOptions, DiffiniteReport } from "./analysisModel";

type DiffiniteProcess = ReturnType<typeof spawn>;
const activeProcesses = new ActiveProcessRegistry<DiffiniteProcess>();
// VS Code caps deactivation at 5s; 4s leaves its final second for cleanup and log flushing.
// Source: microsoft/vscode extHostExtensionService.ts (`Promise.race([timeout(5000), ...])`).
const PROCESS_TERMINATION_TIMEOUT_MS = 4_000;
// Display limit only: enough for a full Python traceback, small enough to bound memory.
const STDERR_TAIL_CHARS = 8_192;

export interface ProcessTerminationResult {
  closed: boolean;
  stillRunning: boolean;
  pid?: number;
  /**
   * Windows only: the Python parent had already exited, so its PID may belong
   * to an unrelated process and taskkill /t was not run. Worker processes it
   * started cannot be reached from here and may still be running.
   */
  workersUnreachable?: boolean;
}

/**
 * Whether `taskkill /pid <pid> /t /f` may be used on this process. Once the
 * parent has exited, Windows can reuse its PID for an unrelated process, so
 * the tree kill could hit the wrong process tree; it also could not reach the
 * orphaned workers any more.
 */
export function windowsTreeKillAllowed(proc: { exitCode: number | null; signalCode: NodeJS.Signals | null }): boolean {
  return proc.exitCode === null && proc.signalCode === null;
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
function buildArgs(opts: DiffiniteOptions, ignoreFile: string | null): string[] {
  const args = buildCoreArgs(opts);
  if (ignoreFile) {
    args.push("--ignore-file", ignoreFile);
  }
  return args;
}

/**
 * Materialize the exclusion list for one CLI run. A frozen Phase-1 snapshot
 * (opts.ignoreSnapshot) is reused byte for byte; only a caller without one
 * reads ~/.diffignore at this moment.
 */
function prepareIgnoreFile(opts: DiffiniteOptions): { filePath: string | null; cleanup: () => void } {
  const snapshot = opts.ignoreSnapshot !== undefined ? opts.ignoreSnapshot : readIgnoreSnapshot();
  if (!snapshot) { return { filePath: null, cleanup: () => undefined }; }
  const temporary = writeIgnoreSnapshot(snapshot);
  return { filePath: temporary.filePath, cleanup: temporary.cleanup };
}

/** Decode a child's output as UTF-8 across chunk boundaries, one line at a time. */
function onOutputLines(
  stream: NodeJS.ReadableStream | null | undefined,
  onLine: (line: string) => void,
): void {
  if (!stream) { return; }
  // setEncoding keeps multi-byte characters split across reads intact.
  stream.setEncoding("utf8");
  const lines = new LineBuffer(onLine, STDERR_TAIL_CHARS);
  stream.on("data", (chunk: string) => lines.push(chunk));
  stream.on("end", () => lines.flush());
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
  // Only a 'close' event (which releases the registry entry) proves the tree
  // is gone. An exitCode alone means the Python parent exited; its pool
  // workers can still hold the pipes and keep running, so kill the tree anyway.
  if (!activeProcesses.has(proc)) {
    return { closed: true, stillRunning: false, pid: proc.pid };
  }
  const closedPromise = waitForProcessClose(proc, PROCESS_TERMINATION_TIMEOUT_MS);
  let windowsKiller: ReturnType<typeof spawn> | undefined;
  let workersUnreachable = false;

  if (os.platform() === "win32" && proc.pid && !windowsTreeKillAllowed(proc)) {
    // The parent is gone: its PID may already name another process, so no
    // taskkill. Pool workers exit on their own when they see the parent die
    // (pipeline._exit_when_parent_dies); until the pipes close we cannot
    // prove that, and the cancellation message says so.
    workersUnreachable = true;
  } else if (os.platform() === "win32" && proc.pid) {
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
      // The group outlives its leader, so this reaches orphaned workers too.
      process.kill(-proc.pid, "SIGKILL");
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "ESRCH") { forceDirectProcessKill(proc); }
    }
  } else {
    forceDirectProcessKill(proc);
  }

  const closed = await closedPromise;
  if (!closed && !workersUnreachable) {
    // Retry the direct handle if the tree command failed or never completed.
    forceDirectProcessKill(proc);
  }
  if (windowsKiller?.exitCode === null) {
    try { windowsKiller.kill("SIGKILL"); } catch { /* helper already exited */ }
    windowsKiller.unref();
  }

  // With an exited Windows parent, probing its (possibly reused) PID says
  // nothing about the workers, so the result is reported as unknown instead.
  const stillRunning = !closed && !workersUnreachable && isProcessTreeStillRunning(proc);
  if (!closed) {
    if (workersUnreachable) {
      console.warn(
        `[Diffinite] Analyzer process${proc.pid ? ` PID ${proc.pid}` : ""} had already exited, but its ` +
        "output pipes stayed open: worker processes may still be running.",
      );
    } else if (stillRunning) {
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
  return { closed, stillRunning, pid: proc.pid, workersUnreachable: workersUnreachable && !closed };
}

export function cancellationError(
  operation: "Analysis" | "Export",
  result: ProcessTerminationResult,
): Error {
  const preserved = operation === "Export" ? " Existing output was preserved." : "";
  if (result.stillRunning) {
    return new Error(
      `${operation} canceled, but analyzer${result.pid ? ` PID ${result.pid}` : ""} is still ` +
      `running after forced termination. Close it with the operating system process manager.${preserved}`,
    );
  }
  if (result.workersUnreachable) {
    return new Error(
      `${operation} canceled. The analyzer${result.pid ? ` (PID ${result.pid})` : ""} had already exited, ` +
      "but its worker processes kept its output open and could not be stopped from VS Code; they may still " +
      `be running. If python.exe keeps using CPU, end it in Task Manager.${preserved}`,
    );
  }
  if (!result.closed) {
    return new Error(
      `${operation} canceled, but the analyzer did not confirm that all of its processes ended before the ` +
      `timeout; worker processes may still be running. Check the operating system process manager.${preserved}`,
    );
  }
  return new Error(`${operation} canceled by user.${preserved}`);
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
  return (await runAnalysisWithInputs(dirA, dirB, opts, progress, token)).report;
}

export interface LiveAnalysis {
  report: DiffiniteReport;
  /** Input SHA-256 values from the run's manifest; null if it could not be read. */
  inputs: InputManifest | null;
}

/**
 * Run diffinite CLI and return the parsed JSON report together with the
 * per-file input hashes Python recorded for that run.
 */
export async function runAnalysisWithInputs(
  dirA: string,
  dirB: string,
  opts: DiffiniteOptions,
  progress: vscode.Progress<{ message?: string; increment?: number }>,
  token?: vscode.CancellationToken
): Promise<LiveAnalysis> {
  const temporary = createTempJsonFile("diffinite-report-");
  const tmpJson = temporary.filePath;
  // Python writes manifest.sha256.json next to the first report (pipeline.py).
  const tmpManifest = path.join(temporary.directory, "manifest.sha256.json");
  let ignoreFile: ReturnType<typeof prepareIgnoreFile>;
  try {
    ignoreFile = prepareIgnoreFile(opts);
  } catch (err) {
    temporary.cleanup();
    throw err;
  }
  const cleanupTmp = (): void => {
    temporary.cleanup();
    ignoreFile.cleanup();
  };

  // Options first, then '--', then the positional directories. The '--' sentinel
  // stops argparse treating a path that begins with '-' as an option.
  const cliArgs = [
    "--report-json", tmpJson,
    ...buildArgs(opts, ignoreFile.filePath),
    "--", dirA, dirB,
  ];

  progress.report({ message: "Running the analysis" });

  return new Promise<LiveAnalysis>((resolve, reject) => {
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

    const resolveOnce = (analysis: LiveAnalysis): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      cleanupTmp();
      resolve(analysis);
    };

    onOutputLines(proc.stderr, (line) => {
      // Keep a bounded tail so a noisy child cannot exhaust the extension host.
      // Python tracebacks place the final exception last.
      stderrData = (stderrData + line + "\n").slice(-STDERR_TAIL_CHARS);
      // Python logs its pipeline steps to stderr (logging.basicConfig in cli.py).
      const step = pipelineStepMessage(line);
      if (step) { progress.report({ message: step }); }
    });

    onOutputLines(proc.stdout, (line) => {
      // [Worker-1] 5/20 (25%)
      const match = line.match(/\[Worker-?(\d+)\]\s+(\d+)\/(\d+)/i);
      if (match) {
        const wId = match[1];
        const current = parseInt(match[2], 10);
        const total = parseInt(match[3], 10);
        workerProgress[wId] = { current, total };
        reportWorkerProgress();
      }
    });

    function reportWorkerProgress(): void {
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
      const message = renderProgressMessage(sumCurrent, sumTotal);

      if (increment > 0) {
        progress.report({ increment, message });
        lastReportedPct = overallPct;
      } else {
        progress.report({ message });
      }
    }

    proc.on("close", async (code) => {
      console.log('[Diffinite] Process exited with code:', code);
      if (cancelled) {
        rejectOnce(new Error("Analysis canceled by user."));
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
        const inputs = await readInputManifest(tmpManifest);
        if (cancelled) {
          rejectOnce(new Error("Analysis canceled by user."));
        } else {
          resolveOnce({ report, inputs });
        }
      } catch (err) {
        rejectOnce(new Error(`Failed to parse JSON report: ${err}`));
      }
    });

    proc.on("error", (err) => {
      rejectOnce(cancelled
        ? new Error("Analysis canceled by user.")
        : new Error(
          `Failed to start diffinite. Check that the bundled binary exists ` +
          `or set diffinite.pythonPath in settings.\n${err.message}`
        ));
    });

    const cancel = (): void => {
      if (settled || cancelled) { return; }
      cancelled = true;
      progress.report({ message: "Canceling the analysis and stopping workers" });
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
  let ignoreFile: ReturnType<typeof prepareIgnoreFile> | undefined;
  const exportOptions = { ...opts };
  try {
    // Refuse before the (possibly long) analyzer run if publishing would have
    // to replace a <stem>_files tree that is not a verified prior output.
    await exportTransaction.verifyExistingOutputs();
    // Same exclusion list bytes as the reviewed analysis (Phase 1).
    ignoreFile = prepareIgnoreFile(opts);
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
    ignoreFile?.cleanup();
    exportTransaction.abort();
    throw err;
  }
  const cleanupIgnoreFile = ignoreFile.cleanup;

  const cliArgs = [
    formatFlag, exportTransaction.stagedOutputPath,
    ...buildArgs(exportOptions, ignoreFile.filePath),
    "--", dirA, dirB,
  ];

  progress.report({ message: `Exporting the ${format.toUpperCase()} report` });

  return new Promise<void>((resolve, reject) => {
    let proc: DiffiniteProcess;
    try {
      proc = spawnDiffinite(cliArgs);
    } catch (err) {
      selectionFilter?.cleanup();
      cleanupIgnoreFile();
      exportTransaction.abort();
      reject(new Error(`Failed to start diffinite: ${err instanceof Error ? err.message : String(err)}`));
      return;
    }
    let settled = false;
    let cancelled = false;
    let cancellationDisposable: vscode.Disposable | undefined;
    let stderr = "";
    const workerProgress: Record<string, { current: number, total: number }> = {};

    const rejectOnce = (error: Error): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      selectionFilter?.cleanup();
      cleanupIgnoreFile();
      exportTransaction.abort();
      reject(error);
    };
    const resolveOnce = (): void => {
      if (settled) { return; }
      settled = true;
      cancellationDisposable?.dispose();
      selectionFilter?.cleanup();
      cleanupIgnoreFile();
      resolve();
    };

    onOutputLines(proc.stderr, (line) => {
      // See runAnalysis: retain useful terminal context without unbounded growth.
      stderr = (stderr + line + "\n").slice(-STDERR_TAIL_CHARS);
      const step = pipelineStepMessage(line);
      if (step) { progress.report({ message: step }); }
    });

    onOutputLines(proc.stdout, (line) => {
      // [Worker-1] 5/20 (25%)
      const match = line.match(/\[Worker-?(\d+)\]\s+(\d+)\/(\d+)/i);
      if (match) {
        workerProgress[match[1]] = { current: parseInt(match[2], 10), total: parseInt(match[3], 10) };
        let done = 0;
        let total = 0;
        for (const w of Object.values(workerProgress)) { done += w.current; total += w.total; }
        progress.report({ message: renderProgressMessage(done, total) });
      }
    });

    proc.on("close", async (code) => {
      if (cancelled) {
        rejectOnce(new Error("Export canceled by user. Existing output was preserved."));
        return;
      }
      if (code !== 0) {
        rejectOnce(new Error(`diffinite export failed (code ${code}):\n${stderr}`));
        return;
      }
      if (opts.reviewedInputs !== undefined) {
        // The export re-reads the live source folders. Publish it only if it
        // analysed exactly the input files of the analysis on screen. null
        // means the reviewed hashes are unknown, so nothing can be confirmed.
        const reviewed = opts.reviewedInputs;
        const exported = await readInputManifest(exportTransaction.stagedManifestPath);
        const changes = exported && reviewed ? diffInputManifests(reviewed, exported) : [];
        if (!exported || !reviewed || changes.length) {
          rejectOnce(new Error(
            "Export not published: the source folders no longer match the reviewed analysis" +
            (exported && reviewed
              ? ` (${changes.join("; ")})`
              : " (input hashes of the reviewed analysis or of the export could not be read)") +
            ". Existing output was preserved. Run the analysis again to review the current files.",
          ));
          return;
        }
      }
      try {
        await exportTransaction.publish({
          isCancellationRequested: () => cancelled || token?.isCancellationRequested === true,
        });
        resolveOnce();
      } catch (err) {
        rejectOnce(cancelled || token?.isCancellationRequested
          ? new Error("Export canceled by user. Existing output was preserved.")
          : new Error(`Failed to publish complete export artifacts: ${err}`));
      }
    });

    proc.on("error", (err) => {
      rejectOnce(cancelled
        ? new Error("Export canceled by user.")
        : new Error(`Failed to start diffinite: ${err.message}`));
    });

    const cancel = (): void => {
      if (settled || cancelled) { return; }
      cancelled = true;
      progress.report({ message: "Canceling the export and stopping workers" });
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
