import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { collectOptions } from "./optionsPanel";
import { runAnalysis } from "./runner";
import { showResults } from "./resultViewer";
import { TreeViewerPanel } from "./treeViewer";

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

  const options = await collectOptions(context);
  if (!options) { return; }

  try {
    // Phase 1: Metrics Only (Fast Scan)
    const phase1Opts = { ...options, metricsOnly: true };
    const report1 = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Diffinite (Phase 1): Scanning and matching files…",
        cancellable: true,
      },
      (progress, token) => runAnalysis(dirA, dirB, phase1Opts, progress, token)
    );

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

      try {
        const report2 = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: `Diffinite (Phase 2): Rendering targeted report (${selectedFiles.length} files)…`,
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
