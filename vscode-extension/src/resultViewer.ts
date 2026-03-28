/**
 * Result Viewer — renders analysis results in a scrollable WebviewPanel.
 *
 * Features:
 *   (1) Scrollable block-by-block view of all matched file pairs
 *   (2) Floating navigation bar: Next/Prev block + Export buttons
 *   (3) Deep Compare cross-match table
 *   (4) Keyboard shortcuts: J (next), K (prev)
 */
import * as vscode from "vscode";
import { DiffiniteReport, DiffiniteOptions, runExport } from "./runner";

/**
 * Show the analysis results in a Webview panel.
 */
export function showResults(
  context: vscode.ExtensionContext,
  report: DiffiniteReport,
  options: DiffiniteOptions
): void {
  const panel = vscode.window.createWebviewPanel(
    "diffiniteResults",
    "Diffinite — Results",
    vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  panel.webview.html = buildResultHtml(report);

  // Handle messages from the Webview (export buttons)
  panel.webview.onDidReceiveMessage(
    async (msg: { command: string; format?: string }) => {
      if (msg.command === "export" && msg.format) {
        const format = msg.format as "pdf" | "html" | "md";
        const filters: Record<string, string[]> = {
          pdf: { "PDF": ["pdf"] },
          html: { "HTML": ["html"] },
          md: { "Markdown": ["md"] },
        }[format] as unknown as Record<string, string[]>;

        const basenameA = report.dir_a.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "A";
        const basenameB = report.dir_b.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "B";
        const now = new Date();
        const timestamp = `${now.getFullYear()}${(now.getMonth() + 1).toString().padStart(2, '0')}${now.getDate().toString().padStart(2, '0')}_${now.getHours().toString().padStart(2, '0')}${now.getMinutes().toString().padStart(2, '0')}`;
        const defaultFilename = `${basenameA}_${basenameB}_${timestamp}.${format}`;

        const uri = await vscode.window.showSaveDialog({
          defaultUri: vscode.Uri.file(defaultFilename),
          filters,
        });

        if (uri) {
          try {
            await vscode.window.withProgress(
              {
                location: vscode.ProgressLocation.Notification,
                title: "Diffinite",
                cancellable: false,
              },
              async (progress) => {
                await runExport(
                  report.dir_a, report.dir_b,
                  options, format, uri.fsPath, progress
                );
              }
            );
            // Show success message outside withProgress so spinner closes immediately
            const action = await vscode.window.showInformationMessage(
              `${format.toUpperCase()} report saved.`,
              "Open File"
            );
            if (action === "Open File") {
              vscode.env.openExternal(uri);
            }
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`Export failed: ${msg}`);
          }
        }
      }
    },
    undefined,
    context.subscriptions
  );
}

/* ------------------------------------------------------------------ */
/* HTML Builder                                                        */
/* ------------------------------------------------------------------ */

function buildResultHtml(report: DiffiniteReport): string {
  const meta = report.metadata;
  const summary = report.summary;

  // --- Summary section ---
  let summaryHtml = `
    <div class="summary-bar">
      <span class="stat"><strong>${summary.matched_pairs}</strong> matched pairs</span>
      <span class="stat"><strong>${summary.unmatched_a_count}</strong> unmatched (A)</span>
      <span class="stat"><strong>${summary.unmatched_b_count}</strong> unmatched (B)</span>
    </div>
  `;

  if (meta) {
    summaryHtml += `
      <div class="meta-bar">
        <span>Mode: <strong>${escHtml(meta.exec_mode)}</strong></span>
        <span>K=${meta.k}</span>
        <span>W=${meta.w}</span>
        <span>T=${meta.threshold.toFixed(2)}</span>
      </div>
    `;
  }

  // --- Diff blocks ---
  let blocksHtml = "";
  report.results.forEach((r, i) => {
    const pct = (r.ratio * 100).toFixed(1);
    const badgeClass = r.ratio >= 0.8 ? "badge-high" : r.ratio >= 0.5 ? "badge-mid" : "badge-low";

    blocksHtml += `
      <div class="diff-block" id="block-${i}">
        <div class="block-header">
          <span class="block-index">${i + 1} / ${report.results.length}</span>
          <span class="block-files">
            ${escHtml(r.file_a)} &harr; ${escHtml(r.file_b)}
          </span>
          <span class="badge ${badgeClass}">${pct}%</span>
        </div>
        <div class="block-stats">
          <span class="stat-add">+${r.additions}</span>
          <span class="stat-del">&minus;${r.deletions}</span>
          <span class="stat-sim">name: ${r.name_similarity.toFixed(0)}</span>
        </div>
        ${
          r.error
            ? `<div class="block-error">Error: ${escHtml(r.error)}</div>`
            : `<div class="block-diff">${r.html_diff}</div>`
        }
      </div>
    `;
  });

  // --- Deep Compare section ---
  let deepHtml = "";
  if (report.deep_results && report.deep_results.length > 0) {
    let deepRows = "";
    for (const dr of report.deep_results) {
      for (const m of dr.matches) {
        const jpct = (m.jaccard * 100).toFixed(1);
        const jClass = m.jaccard >= 0.8 ? "badge-high" : m.jaccard >= 0.5 ? "badge-mid" : "badge-low";
        deepRows += `
          <tr>
            <td>${escHtml(dr.file_a)}</td>
            <td>${escHtml(m.file_b)}</td>
            <td>${m.shared_hashes}</td>
            <td><span class="badge ${jClass}">${jpct}%</span></td>
          </tr>
        `;
      }
    }

    deepHtml = `
      <div class="deep-section" id="block-deep">
        <h2>Deep Compare — N:M Cross-Match</h2>
        <table class="deep-table">
          <thead>
            <tr><th>File A</th><th>File B</th><th>Shared</th><th>Jaccard</th></tr>
          </thead>
          <tbody>${deepRows}</tbody>
        </table>
      </div>
    `;
  }

  // --- Unmatched files ---
  let unmatchedHtml = "";
  if (report.unmatched_a.length > 0 || report.unmatched_b.length > 0) {
    unmatchedHtml = `<div class="unmatched-section">`;
    if (report.unmatched_a.length > 0) {
      unmatchedHtml += `<h3>Unmatched in A</h3><ul>${report.unmatched_a.map(f => `<li>${escHtml(f)}</li>`).join("")}</ul>`;
    }
    if (report.unmatched_b.length > 0) {
      unmatchedHtml += `<h3>Unmatched in B</h3><ul>${report.unmatched_b.map(f => `<li>${escHtml(f)}</li>`).join("")}</ul>`;
    }
    unmatchedHtml += `</div>`;
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Diffinite Results</title>
  <style>${CSS}</style>
</head>
<body>
  <header>
    <h1>Diffinite — Results</h1>
    <div class="dirs">
      <div><strong>A:</strong> ${escHtml(report.dir_a)}</div>
      <div><strong>B:</strong> ${escHtml(report.dir_b)}</div>
    </div>
    ${summaryHtml}
  </header>

  <main>
    ${blocksHtml}
    ${deepHtml}
    ${unmatchedHtml}
  </main>

  <!-- Floating navigation bar -->
  <nav class="floating-nav" id="floatingNav">
    <button id="btnPrev" title="Previous block (K)">&#9650; Prev</button>
    <span class="nav-pos" id="navPos">—</span>
    <button id="btnNext" title="Next block (J)">&#9660; Next</button>
    <div class="nav-divider"></div>
    <button class="export-btn" data-format="pdf" title="Export PDF">&#128196; PDF</button>
    <button class="export-btn" data-format="html" title="Export HTML">&#127760; HTML</button>
    <button class="export-btn" data-format="md" title="Export Markdown">&#128221; MD</button>
  </nav>

  <script>${JS}</script>
</body>
</html>`;
}

/* ------------------------------------------------------------------ */
/* Inline CSS for the Webview                                          */
/* ------------------------------------------------------------------ */
const CSS = `
  :root {
    --bg: #1e1e1e;
    --bg-surface: #252526;
    --bg-block: #2d2d2d;
    --fg: #cccccc;
    --fg-dim: #888;
    --accent: #0078d4;
    --green: #4ec9b0;
    --red: #f14c4c;
    --yellow: #dcdcaa;
    --border: #3c3c3c;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: "Segoe UI", "Noto Sans KR", -apple-system, sans-serif;
    font-size: 13px;
    color: var(--fg);
    background: var(--bg);
    padding-bottom: 80px;
  }

  header {
    padding: 20px 24px 16px;
    border-bottom: 2px solid var(--accent);
    background: var(--bg-surface);
  }

  h1 {
    font-size: 18px;
    color: var(--accent);
    margin-bottom: 8px;
  }

  h2 {
    font-size: 15px;
    color: var(--accent);
    margin: 20px 0 12px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--border);
  }

  h3 { font-size: 13px; color: var(--fg-dim); margin: 12px 0 6px; }

  .dirs { font-size: 11px; color: var(--fg-dim); margin-bottom: 8px; }

  .summary-bar, .meta-bar {
    display: flex;
    gap: 16px;
    font-size: 12px;
    margin-top: 6px;
  }

  .meta-bar { color: var(--fg-dim); font-size: 11px; }

  .stat strong { color: var(--accent); }

  main { padding: 16px 24px; }

  /* Diff blocks */
  .diff-block {
    background: var(--bg-block);
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-bottom: 16px;
    overflow: hidden;
  }

  .diff-block.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

  .block-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border);
    font-size: 12px;
  }

  .block-index {
    background: var(--accent);
    color: #fff;
    padding: 2px 8px;
    border-radius: 3px;
    font-weight: 600;
    font-size: 11px;
  }

  .block-files { flex: 1; font-family: "Consolas", monospace; font-size: 12px; }

  .block-stats {
    display: flex;
    gap: 12px;
    padding: 6px 14px;
    font-size: 11px;
    color: var(--fg-dim);
    background: rgba(0,0,0,0.15);
  }

  .stat-add { color: var(--green); }
  .stat-del { color: var(--red); }

  .block-error { padding: 12px 14px; color: var(--red); }

  .block-diff { overflow-x: auto; }

  /* Override difftbl styles for dark mode */
  .difftbl { width: 100%; border-collapse: collapse; font-size: 11px; }
  .difftbl th, .difftbl td { border: 1px solid var(--border); padding: 1px 4px; }
  .difftbl thead th { background: #333; color: #ddd; font-size: 11px; padding: 4px 6px; }
  .difftbl .ln { color: var(--fg-dim); background: rgba(255,255,255,0.03); text-align: right; font-size: 10px; }
  .difftbl .code { white-space: pre-wrap; word-wrap: break-word; font-family: "Consolas", "Courier New", monospace; }
  .difftbl .code pre { margin: 0; padding: 0; font-size: inherit; font-family: inherit; white-space: pre-wrap; }
  .difftbl .del { background: rgba(241, 76, 76, 0.15); }
  .difftbl .add { background: rgba(78, 201, 176, 0.15); }
  .difftbl .empty { background: rgba(255,255,255,0.02); }
  .difftbl .chg { background: rgba(255, 200, 50, 0.10); }
  .difftbl .moved-del { background: rgba(168, 85, 247, 0.18); }
  .difftbl .moved-add { background: rgba(59, 130, 246, 0.18); }
  .word-del { background: rgba(241, 76, 76, 0.35); border-radius: 2px; padding: 0 2px; }
  .word-add { background: rgba(78, 201, 176, 0.35); border-radius: 2px; padding: 0 2px; }
  .difftbl tr.fold td { text-align: center; color: var(--fg-dim); background: rgba(255,255,255,0.04); }

  /* difflib HtmlDiff inline change markers */
  .diff_chg { background: rgba(255, 200, 50, 0.25); border-radius: 2px; text-decoration: none; }
  .diff_add { background: rgba(78, 201, 176, 0.25); border-radius: 2px; }
  .diff_sub { background: rgba(241, 76, 76, 0.25); border-radius: 2px; }
  .diff_next { display: none; }

  /* Override Pygments error token red border (inline style: border: 1px solid #F00) */
  .block-diff span[style*="border"] { border: none !important; }

  /* Badge */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; color: #fff; }
  .badge-high { background: #28a745; }
  .badge-mid  { background: #e0a800; color: #1e1e1e; }
  .badge-low  { background: #dc3545; }

  /* Deep Compare */
  .deep-section { margin-top: 24px; }
  .deep-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .deep-table th, .deep-table td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
  .deep-table thead th { background: #6c5ce7; color: #fff; }
  .deep-table tbody tr:nth-child(even) { background: rgba(108, 92, 231, 0.08); }

  /* Unmatched */
  .unmatched-section { margin-top: 16px; font-size: 12px; }
  .unmatched-section ul { list-style: disc; padding-left: 20px; color: var(--red); }
  .unmatched-section li { margin: 2px 0; }

  /* Floating Nav */
  .floating-nav {
    position: fixed;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 16px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    z-index: 9999;
  }

  .floating-nav button {
    background: var(--bg-block);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 12px;
    cursor: pointer;
    font-size: 12px;
  }

  .floating-nav button:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

  .nav-pos { color: var(--fg-dim); font-size: 11px; min-width: 50px; text-align: center; }
  .nav-divider { width: 1px; height: 20px; background: var(--border); margin: 0 4px; }

  .export-btn { font-size: 11px !important; padding: 4px 8px !important; }
`;

/* ------------------------------------------------------------------ */
/* Inline JS for the Webview                                           */
/* ------------------------------------------------------------------ */
const JS = `
(function() {
  const vscode = acquireVsCodeApi();
  const blocks = document.querySelectorAll('.diff-block');
  const navPos = document.getElementById('navPos');
  let currentBlock = -1;

  function goTo(idx) {
    if (blocks.length === 0) return;
    idx = Math.max(0, Math.min(idx, blocks.length - 1));
    blocks.forEach(b => b.classList.remove('active'));
    blocks[idx].classList.add('active');
    blocks[idx].scrollIntoView({ behavior: 'smooth', block: 'start' });
    currentBlock = idx;
    navPos.textContent = (idx + 1) + ' / ' + blocks.length;
  }

  document.getElementById('btnNext').addEventListener('click', () => goTo(currentBlock + 1));
  document.getElementById('btnPrev').addEventListener('click', () => goTo(currentBlock - 1));

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'j' || e.key === 'J') { e.preventDefault(); goTo(currentBlock + 1); }
    if (e.key === 'k' || e.key === 'K') { e.preventDefault(); goTo(currentBlock - 1); }
  });

  document.querySelectorAll('.export-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const format = btn.getAttribute('data-format');
      vscode.postMessage({ command: 'export', format });
    });
  });

  // Initialize at first block
  if (blocks.length > 0) goTo(0);
})();
`;

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
