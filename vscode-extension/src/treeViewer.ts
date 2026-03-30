/**
 * Tree Viewer (Phase 1 Selection UI)
 *
 * Displays the metrics-only JSON report in a Checkbox Tree View.
 * Allows the user to select specific files based on similarity scores
 * before generating the final PDF report.
 */
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { DiffiniteReport } from "./runner";

export class TreeViewerPanel {
  public static currentPanel: TreeViewerPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];
  
  // Callback invoked when user clicks "Generate Final Report"
  private _onGenerateCallback: ((selectedFilesA: string[]) => void) | undefined;

  public static createOrShow(
    report: DiffiniteReport,
    onGenerate: (selectedFilesA: string[]) => void
  ) {
    if (TreeViewerPanel.currentPanel) {
      TreeViewerPanel.currentPanel._panel.reveal(vscode.ViewColumn.Active);
      TreeViewerPanel.currentPanel.update(report);
      TreeViewerPanel.currentPanel._onGenerateCallback = onGenerate;
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      "diffiniteTreeViewer",
      "Diffinite — Select Evidence Files",
      vscode.ViewColumn.Active,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    TreeViewerPanel.currentPanel = new TreeViewerPanel(panel, report, onGenerate);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    report: DiffiniteReport,
    onGenerate: (selectedFilesA: string[]) => void
  ) {
    this._panel = panel;
    this._onGenerateCallback = onGenerate;
    this.update(report);

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    this._panel.webview.onDidReceiveMessage(
      (message) => {
        switch (message.command) {
          case "generate":
            const selectedFiles: string[] = message.files;
            if (this._onGenerateCallback) {
                this._onGenerateCallback(selectedFiles);
            }
            this.dispose(); // Close tree view and proceed
            return;
          case "cancel":
            this.dispose();
            return;
        }
      },
      null,
      this._disposables
    );
  }

  public dispose() {
    TreeViewerPanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const x = this._disposables.pop();
      if (x) { x.dispose(); }
    }
  }

  private update(report: DiffiniteReport) {
    this._panel.webview.html = this._getHtmlForWebview(report);
  }

  private _getHtmlForWebview(report: DiffiniteReport): string {
    // Basic flat list rendered as a table with checkboxes.
    // In a production app, this would be a nested collapsible tree,
    // but a sortable table accomplishes the exact same selection capability
    // in a much more robust and readable way without complex JS tree libraries.
    
    let rowsHtml = "";
    
    // Sort results by similarity descending
    const sortedResults = [...report.results].sort((a, b) => {
       // Push exact matches (1.0 ratio) and high name similarity to top
       if (b.ratio !== a.ratio) return b.ratio - a.ratio;
       return b.name_similarity - a.name_similarity;
    });

    sortedResults.forEach((r, idx) => {
        const ratioPct = (r.ratio * 100).toFixed(1) + "%";
        const nameSimPct = r.name_similarity.toFixed(1) + "%";
        
        // Auto-check heuristic: Check if it has any similarity or if it's identical
        const defaultChecked = r.ratio > 0.0 ? "checked" : "";
        
        // Badge color for content ratio
        let badgeColor = "#dc3545"; // Red
        if (r.ratio >= 0.8) badgeColor = "#28a745"; // Green
        else if (r.ratio >= 0.3) badgeColor = "#ffc107"; // Yellow

        rowsHtml += `
        <tr>
            <td style="text-align:center;">
                <input type="checkbox" class="file-cb" value="${r.file_a}" ${defaultChecked}>
            </td>
            <td><code>${r.file_a}</code></td>
            <td><code>${r.file_b}</code></td>
            <td style="text-align:center;">${nameSimPct}</td>
            <td style="text-align:center;">
                <span style="background:${badgeColor}; color:${r.ratio >= 0.3 && r.ratio < 0.8 ? '#000': '#fff'}; padding: 2px 6px; border-radius: 4px; font-weight: bold;">
                    ${ratioPct}
                </span>
            </td>
            <td style="color:green; text-align:right;">+${r.additions}</td>
            <td style="color:red; text-align:right;">-${r.deletions}</td>
        </tr>
        `;
    });

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Select Evidence</title>
    <style>
        :root {
            --bg: #1e1e1e;
            --fg: #ccc;
            --border: #333;
            --accent: #0078d4;
        }
        body {
            font-family: var(--vscode-font-family, 'Segoe UI', sans-serif);
            background-color: var(--bg);
            color: var(--fg);
            padding: 20px;
        }
        .header { margin-bottom: 20px; }
        h1 { color: #fff; font-size: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th, td {
            border: 1px solid var(--border);
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #252526;
            color: #fff;
            position: sticky;
            top: 0;
        }
        tr:hover { background-color: #2a2d2e; }
        
        .toolbar {
            position: sticky;
            bottom: 0;
            background: #252526;
            padding: 15px;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        button {
            padding: 8px 16px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 2px;
            cursor: pointer;
            font-weight: bold;
        }
        button:hover { background: #0086f0; }
        .btn-secondary { background: #555; }
        .btn-secondary:hover { background: #666; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Select Files for Final Report</h1>
        <p>Phase 1 complete. Review the similarity metrics below and select ONLY the files you wish to include in the final PDF/HTML generation.</p>
        <div style="margin-bottom: 10px;">
            <button class="btn-secondary" id="btn-all">Check All</button>
            <button class="btn-secondary" id="btn-none">Uncheck All</button>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 40px; text-align:center;">Inc.</th>
                <th>File A</th>
                <th>File B</th>
                <th style="text-align:center; width:80px;">Name Sim.</th>
                <th style="text-align:center; width:80px;">Content Sim.</th>
                <th style="text-align:right; width:60px;">+Added</th>
                <th style="text-align:right; width:60px;">-Deleted</th>
            </tr>
        </thead>
        <tbody id="file-list">
            ${rowsHtml}
        </tbody>
    </table>

    <div class="toolbar">
        <div><span id="sel-count">0</span> / ${sortedResults.length} selected</div>
        <div>
            <button id="btn-generate">Generate Final Report (${sortedResults.length} files)</button>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const checkboxes = document.querySelectorAll('.file-cb');
        const countLabel = document.getElementById('sel-count');
        const genBtn = document.getElementById('btn-generate');

        function updateCount() {
            let count = 0;
            checkboxes.forEach(cb => { if(cb.checked) count++; });
            countLabel.textContent = count;
            
            // Heuristic Estimations
            const estSecs = Math.max(1, Math.round(count * 0.15)); // ~150ms per file
            const estMemMb = count * 2 + 30; // Base + 2MB RAM per file HTML render
            
            genBtn.textContent = 'Generate Final Report (' + count + ' files) • Est: ~' + estSecs + 's, ~' + estMemMb + 'MB';
        }

        checkboxes.forEach(cb => cb.addEventListener('change', updateCount));

        document.getElementById('btn-all').addEventListener('click', () => {
            checkboxes.forEach(cb => cb.checked = true);
            updateCount();
        });

        document.getElementById('btn-none').addEventListener('click', () => {
            checkboxes.forEach(cb => cb.checked = false);
            updateCount();
        });

        document.getElementById('btn-generate').addEventListener('click', () => {
            const selected = [];
            checkboxes.forEach(cb => {
                if(cb.checked) selected.push(cb.value);
            });
            vscode.postMessage({ command: 'generate', files: selected });
        });

        // Init
        updateCount();
    </script>
</body>
</html>`;
  }
}
