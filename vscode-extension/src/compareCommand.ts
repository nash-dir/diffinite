/**
 * Compare Command — orchestrates the full workflow:
 *   1. Select directories A and B
 *   2. Collect options via the options panel
 *   3. Run diffinite analysis
 *   4. Show results in the scrollable viewer
 */
import * as vscode from "vscode";
import { collectOptions } from "./optionsPanel";
import { runAnalysis } from "./runner";
import { showResults } from "./resultViewer";

export async function compareDirectories(
  context: vscode.ExtensionContext
): Promise<void> {
  // Step 1: Select Dir A
  const uriA = await vscode.window.showOpenDialog({
    canSelectFolders: true,
    canSelectFiles: false,
    canSelectMany: false,
    openLabel: "Select Directory A (Original)",
    title: "Diffinite — Select Original Directory",
  });
  if (!uriA || uriA.length === 0) { return; }

  // Step 2: Select Dir B
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

  // Step 3: Collect options
  console.log('[Diffinite] Step 3: Collecting options…');
  const options = await collectOptions(context);
  console.log('[Diffinite] Options received:', options);
  if (!options) {
    console.log('[Diffinite] Options was undefined — user cancelled or panel closed early');
    return;
  }

  // Step 4: Run analysis with progress
  console.log('[Diffinite] Step 4: Starting analysis…', { dirA, dirB, options });
  try {
    const report = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Diffinite",
        cancellable: false,
      },
      (progress) => runAnalysis(dirA, dirB, options, progress)
    );

    // Step 5: Show results
    console.log('[Diffinite] Step 5: Analysis complete, showing results…', {
      matched: report.summary?.matched_pairs,
      resultsCount: report.results?.length,
    });
    showResults(context, report, options);

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[Diffinite] Analysis FAILED:', msg);
    vscode.window.showErrorMessage(`Diffinite analysis failed: ${msg}`);
  }
}
