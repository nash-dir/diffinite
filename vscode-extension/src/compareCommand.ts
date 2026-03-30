import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { showOptionsPanel } from "./optionsPanel";
import { runAnalysis, DiffiniteOptions } from "./runner";
import { showResults } from "./resultViewer";
import { TreeViewerPanel } from "./treeViewer";
import { scanAndEstimate, estimatePhase2Time } from "./dirScanner";

export async function compareDirectories(
  context: vscode.ExtensionContext
): Promise<void> {
  // Step 1: Launch options panel immediately. It acts as the home base.
  showOptionsPanel(context, async (dirA: string, dirB: string, options: DiffiniteOptions) => {
    executePipeline(context, dirA, dirB, options);
  });
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
  
  if (scan.maxPairSizeMB >= 5) {
    vscode.window.showWarningMessage(
      `Diffinite OOM Risk: Found massive file pairs (max ${scan.maxPairSizeMB.toFixed(1)}MB). ` +
      `Rendering HTML Diff tables for files this large may take very long or exhaust memory. ` +
      `(Est. Simple: ${scan.simpleTimeSeconds}s | Deep: ${scan.deepTimeSeconds}s)`
    );
  } else {
    vscode.window.showInformationMessage(
      `Diffinite Estimate: Computed from ${scan.matchedPairsCount} matched pairs. ` +
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
    const cpuMultiplier = actualPhase1Secs / expectedPhase1Secs;

    // Show Tree Viewer instead of Result Viewer
    TreeViewerPanel.createOrShow(report1, async (selectedFiles) => {
      // Phase 2 callback: when user clicks "Generate Final Report"
      if (selectedFiles.length === 0) {
        vscode.window.showInformationMessage("Diffinite: No files selected. Aborting.");
        return;
      }

      const filterJsonPath = path.join(os.tmpdir(), `diffinite_filter_${Date.now()}.json`);
      fs.writeFileSync(filterJsonPath, JSON.stringify(selectedFiles), "utf-8");

      const phase2Opts = { ...options, filterJson: filterJsonPath };
      const phase2EstSecs = estimatePhase2Time(selectedFiles, dirA, dirB, cpuMultiplier);

      try {
        const report2 = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: `Diffinite (Phase 2): Rendering targeted report (${selectedFiles.length} files, Calibrated Est. ~${phase2EstSecs}s)…`,
            cancellable: true,
          },
          (progress, token) => runAnalysis(dirA, dirB, phase2Opts, progress, token)
        );

        try { fs.unlinkSync(filterJsonPath); } catch { /* ignore */ }

        // Final phase: show full interactive diff viewing results
        showResults(context, report2, options);

      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage("Diffinite Phase 2 failed: " + msg);
        try { fs.unlinkSync(filterJsonPath); } catch { /* ignore */ }
      }
    });

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage("Diffinite Phase 1 failed: " + msg);
  }
}
