import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { collectOptions } from "./optionsPanel";
import { runAnalysis } from "./runner";
import { showResults } from "./resultViewer";
import { TreeViewerPanel } from "./treeViewer";
import { scanAndEstimate, estimatePhase2Time } from "./dirScanner";

export async function compareDirectories(
  context: vscode.ExtensionContext
): Promise<void> {
  const uriA = await vscode.window.showOpenDialog({
    canSelectFolders: true,
    canSelectFiles: false,
    canSelectMany: false,
    openLabel: "Select Directory A (Original)",
    title: "Diffinite — Select Original Directory",
  });
  if (!uriA || uriA.length === 0) { return; }

  const uriB = await vscode.window.showOpenDialog({
    canSelectFolders: true,
    canSelectFiles: false,
    canSelectMany: false,
    openLabel: "Select Directory B (Suspect)",
    title: "Diffinite — Select Comparison Directory",
  });
  if (!uriB || uriB.length === 0) { return; }

  const dirA = uriA[0].fsPath;
  const dirB = uriB[0].fsPath;

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

  const options = await collectOptions(context);
  if (!options) { return; }

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
