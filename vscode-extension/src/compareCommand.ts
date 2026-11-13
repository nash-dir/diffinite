import * as vscode from "vscode";
import * as fs from "fs";
import { showOptionsPanel } from "./optionsPanel";
import { runAnalysisWithInputs, DiffiniteOptions } from "./runner";
import type { IgnoreSnapshot } from "./analysisModel";
import { compareReviewedRuns, readIgnoreSnapshot, snapshotRules } from "./inputFreeze";
import { showResults } from "./resultViewer";
import { TreeViewerPanel } from "./treeViewer";
import { scanAndEstimate, estimatePhase2Time, ScanResult } from "./dirScanner";
import { createTempJsonFile } from "./tempFiles";
import { RunGate } from "./runGate";
import { showFailure } from "./failureNotice";
import { plural } from "./labels";

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
    vscode.window.showWarningMessage("Diffinite: The Review and Select panel is open. Generate the report or close the panel before starting a new analysis.");
    return;
  }
  if (!phase1RunGate.tryEnter()) {
    vscode.window.showWarningMessage("Diffinite: Phase 1 is already running. Wait for it to finish or cancel it before starting again.");
    return;
  }

  try {
    if (!dirA || !dirB) {
      vscode.window.showErrorMessage("Diffinite: Enter both Directory A and Directory B.");
      return;
    }
    if (!fs.existsSync(dirA) || !fs.statSync(dirA).isDirectory()) {
      vscode.window.showErrorMessage(`Diffinite: Directory A does not exist or is not a folder: ${dirA}`);
      return;
    }
    if (!fs.existsSync(dirB) || !fs.statSync(dirB).isDirectory()) {
      vscode.window.showErrorMessage(`Diffinite: Directory B does not exist or is not a folder: ${dirB}`);
      return;
    }

    // Freeze the exclusion list once. Phase 1, Phase 2 and every export of
    // this analysis use these exact bytes, whatever happens to the file later.
    let ignoreSnapshot: IgnoreSnapshot | null;
    try {
      ignoreSnapshot = readIgnoreSnapshot();
    } catch (err: unknown) {
      void showFailure("analysis (Phase 1)", err);
      return;
    }

    try {
      // Phase 1: Metrics Only (Fast Scan). Unmatched lists are always kept
      // inline here so every A file the user may select is visible for review.
      const phase1Opts: DiffiniteOptions = {
        ...options, metricsOnly: true, uncomparedFiles: "inline", ignoreSnapshot,
      };
      let expectedPhase1Secs = 0;
      let phase1Start = Date.now();

      const phase1 = await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "Diffinite (Phase 1): Scanning and matching files",
          cancellable: true,
        },
        async (progress, token) => {
          progress.report({ message: "Counting files for a time estimate" });
          const scan = await scanAndEstimate(dirA, dirB, snapshotRules(ignoreSnapshot), token);
          if (!scan) { throw new Error("Analysis canceled by user."); }
          showEstimate(scan);
          expectedPhase1Secs = options.mode === "deep" ? scan.deepPhase1Secs : scan.simplePhase1Secs;
          phase1Start = Date.now();
          return runAnalysisWithInputs(dirA, dirB, phase1Opts, progress, token);
        },
      );
      const report1 = phase1.report;

      const actualPhase1Secs = Math.max(0.1, (Date.now() - phase1Start) / 1000);
      const safeExpectedSecs = Math.max(0.1, expectedPhase1Secs);
      const cpuMultiplier = actualPhase1Secs / safeExpectedSecs;

      // Show Tree Viewer instead of Result Viewer
      TreeViewerPanel.createOrShow(report1, { dirA, dirB }, async (selectedFiles) => {
        // Phase 2 callback: when user clicks "Generate Final Report"
        if (selectedFiles.length === 0) {
          vscode.window.showInformationMessage("Diffinite: No files selected. No report was generated.");
          return;
        }

        let temporaryFilter: ReturnType<typeof createTempJsonFile> | undefined;
        try {
          temporaryFilter = createTempJsonFile("diffinite-filter-");
          const filterJsonPath = temporaryFilter.filePath;
          fs.writeFileSync(filterJsonPath, JSON.stringify(selectedFiles), "utf-8");

          const phase2Opts = { ...options, filterJson: filterJsonPath, ignoreSnapshot };
          const phase2EstSecs = estimatePhase2Time(selectedFiles, dirA, dirB, cpuMultiplier);
          const phase2 = await vscode.window.withProgress(
            {
              location: vscode.ProgressLocation.Notification,
              title: `Diffinite (Phase 2): Rendering the report for ${plural(selectedFiles.length, "file")}, estimated ${phase2EstSecs} s`,
              cancellable: true,
            },
            (progress, token) => runAnalysisWithInputs(dirA, dirB, phase2Opts, progress, token)
          );
          const report2 = phase2.report;

          // Phase 2 re-reads the source folders. Confirm it analysed the same
          // inputs and paired the selected files as the user reviewed them.
          const reviewWarnings = compareReviewedRuns(
            phase1, phase2, selectedFiles, ignoreSnapshot?.sha256 ?? null,
          );
          if (reviewWarnings.length) {
            void vscode.window.showWarningMessage(
              "Diffinite: the final report does not match the analysis you reviewed.",
              { modal: true, detail: reviewWarnings.join("\n\n") },
            );
          }

          // Final phase: show full interactive diff viewing results
          // Keep privileged local source paths in extension-host memory only;
          // JSON evidence carries privacy-safe labels, not absolute paths.
          showResults(
            context,
            report2,
            {
              ...options, selectedFiles: [...selectedFiles],
              ignoreSnapshot, reviewedInputs: phase2.inputs,
            },
            { dirA, dirB },
            reviewWarnings,
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

function showEstimate(scan: ScanResult): void {
  // 5 MB: rough heuristic for "a side-by-side HTML diff gets slow", not measured.
  // Non-blocking notice only; memory protection is the CLI's --max-file-size.
  if (scan.maxPairSizeMB >= 5) {
    vscode.window.showWarningMessage(
      `Diffinite: A file pair with the same path is ${scan.maxPairSizeMB.toFixed(1)} MB. ` +
      `Diff tables for files of this size take longer to render. The analysis continues. ` +
      `Estimated time: Simple ${scan.simpleTimeSeconds} s, Deep ${scan.deepTimeSeconds} s.`
    );
  } else {
    vscode.window.showInformationMessage(
      `Diffinite: Estimated time: Simple ${scan.simpleTimeSeconds} s, Deep ${scan.deepTimeSeconds} s ` +
      `(${scan.matchedPairsCount} files share a relative path; the analyzer does the final pairing).`
    );
  }
}
