import * as vscode from "vscode";
import * as fs from "fs";
import { showOptionsPanel } from "./optionsPanel";
import { runAnalysis, DiffiniteOptions } from "./runner";
import { showResults } from "./resultViewer";
import { TreeViewerPanel } from "./treeViewer";
import { scanAndEstimate, estimatePhase2Time } from "./dirScanner";
import { createTempJsonFile } from "./tempFiles";
import { RunGate } from "./runGate";
import { showFailure } from "./failureNotice";

const phase1RunGate = new RunGate();

export async function compareDirectories(
  context: vscode.ExtensionContext
): Promise<void> {
  // Step 1: Launch options panel immediately. It acts as the home base.
  // Return the pipeline promise so optionsPanel's `await onRun(...)` waits for
  // Phase 1 + opening the Tree Viewer before reverting the button / posting
  // runComplete (otherwise it would resolve at the first await, mid-Phase-1).
  // NOTE: this does NOT cover Phase 2 — the Tree Viewer's "Generate Report"
  // callback runs later and is not awaited here.
  showOptionsPanel(context, (dirA: string, dirB: string, options: DiffiniteOptions) =>
    executePipeline(context, dirA, dirB, options)
  );
}

export async function executePipeline(
  context: vscode.ExtensionContext,
  dirA: string,
  dirB: string,
  options: DiffiniteOptions
): Promise<void> {
  // Prevent parallel Phase 1 execution if a TreeViewer is already pending user action
  if (TreeViewerPanel.currentPanel) {
    vscode.window.showWarningMessage("Diffinite: An evidence selection panel (Tree Viewer) is already open. Please complete or close it before running a new analysis.");
    return;
  }
  if (!phase1RunGate.tryEnter()) {
    vscode.window.showWarningMessage("Diffinite: Phase 1 is already running. Wait for it to finish or cancel it before starting again.");
    return;
  }

  try {
    if (!dirA || !dirB) {
      vscode.window.showErrorMessage("Diffinite: Both Directory A and Directory B must be specified.");
      return;
    }
    if (!fs.existsSync(dirA) || !fs.statSync(dirA).isDirectory()) {
      vscode.window.showErrorMessage(`Directory A is invalid or not a directory: ${dirA}`);
      return;
    }
    if (!fs.existsSync(dirB) || !fs.statSync(dirB).isDirectory()) {
      vscode.window.showErrorMessage(`Directory B is invalid or not a directory: ${dirB}`);
      return;
    }

    // Predict time complexity
    const scanMsg = vscode.window.setStatusBarMessage("Diffinite: Scanning files for time estimation...");
    const scan = scanAndEstimate(dirA, dirB);
    scanMsg.dispose();
  
    // 5 MB: rough heuristic for "a side-by-side HTML diff gets slow", not measured.
    // Non-blocking notice only; memory protection is the CLI's --max-file-size.
    if (scan.maxPairSizeMB >= 5) {
      vscode.window.showWarningMessage(
        `Diffinite large-file notice: a same-path file pair is ${scan.maxPairSizeMB.toFixed(1)}MB. ` +
        `Rendering HTML diff tables for files this large may be slow. Analysis continues. ` +
        `(Rough est. Simple: ~${scan.simpleTimeSeconds}s | Deep: ~${scan.deepTimeSeconds}s)`
      );
    } else {
      vscode.window.showInformationMessage(
        `Diffinite rough estimate (${scan.matchedPairsCount} files share an identical relative path; ` +
        `actual pairing is done by the analyzer): ` +
        `[Simple Mode: ~${scan.simpleTimeSeconds}s] [Deep Mode: ~${scan.deepTimeSeconds}s]`
      );
    }

    const expectedPhase1Secs = options.mode === "deep" ? scan.deepPhase1Secs : scan.simplePhase1Secs;

    try {
      // Phase 1: Metrics Only (Fast Scan)
      const phase1Opts = { ...options, metricsOnly: true };
      const phase1Start = Date.now();
    
    const report1 = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Diffinite (Phase 1): Scanning and matching files…",
        cancellable: true,
      },
      (progress, token) => runAnalysis(dirA, dirB, phase1Opts, progress, token)
    );
    
    const actualPhase1Secs = Math.max(0.1, (Date.now() - phase1Start) / 1000);
    const safeExpectedSecs = Math.max(0.1, expectedPhase1Secs);
    const cpuMultiplier = actualPhase1Secs / safeExpectedSecs;

    // Show Tree Viewer instead of Result Viewer
      TreeViewerPanel.createOrShow(report1, { dirA, dirB }, async (selectedFiles) => {
        // Phase 2 callback: when user clicks "Generate Final Report"
        if (selectedFiles.length === 0) {
          vscode.window.showInformationMessage("Diffinite: No files selected. Aborting.");
          return;
        }

        let temporaryFilter: ReturnType<typeof createTempJsonFile> | undefined;
        try {
          temporaryFilter = createTempJsonFile("diffinite-filter-");
          const filterJsonPath = temporaryFilter.filePath;
          fs.writeFileSync(filterJsonPath, JSON.stringify(selectedFiles), "utf-8");

          const phase2Opts = { ...options, filterJson: filterJsonPath };
          const phase2EstSecs = estimatePhase2Time(selectedFiles, dirA, dirB, cpuMultiplier);
          const report2 = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: `Diffinite (Phase 2): Rendering targeted report (${selectedFiles.length} files, rough est. ~${phase2EstSecs}s)…`,
            cancellable: true,
          },
          (progress, token) => runAnalysis(dirA, dirB, phase2Opts, progress, token)
        );

          // Final phase: show full interactive diff viewing results
          // Keep privileged local source paths in extension-host memory only;
          // JSON evidence carries privacy-safe labels, not absolute paths.
          showResults(
            context,
            report2,
            { ...options, selectedFiles: [...selectedFiles] },
            { dirA, dirB },
          );

        } catch (err: unknown) {
          void showFailure("report rendering (Phase 2)", err);
        } finally {
          temporaryFilter?.cleanup();
        }
      });

    } catch (err: unknown) {
      void showFailure("analysis (Phase 1)", err);
    }
  } finally {
    phase1RunGate.leave();
  }
}
