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
import * as path from "path";
import { getPdfFont, getPdfLang } from "./config";
import { DiffiniteReport, DiffiniteOptions, runExport } from "./runner";
import { buildReportViewModel, similarityText } from "./analysisModel";
import { RunGate } from "./runGate";
import { escHtml, getNonce, THEME_CSS } from "./webviewUtils";
import {
  REPORT_PRESETS, ReportFormat, applyReportPreset, describeReportOutput,
  isReportFormat, isReportPresetId,
} from "./reportPresets";
import { showFailure } from "./failureNotice";

const exportRunGate = new RunGate();

/**
 * Show the analysis results in a Webview panel.
 */
export function showResults(
  context: vscode.ExtensionContext,
  report: DiffiniteReport,
  options: DiffiniteOptions,
  sourceDirs: { dirA: string; dirB: string }
): void {
  const panel = vscode.window.createWebviewPanel(
    "diffiniteResults",
    `Diffinite: Results (${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })})`,
    vscode.ViewColumn.Active,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  panel.webview.html = buildResultHtml(report, options, getNonce());

  // Handle messages from the Webview (export buttons)
  panel.webview.onDidReceiveMessage(
    async (msg: { command?: unknown; format?: unknown; preset?: unknown }) => {
      if (msg?.command === "export" && isReportFormat(msg.format) && isReportPresetId(msg.preset)) {
        const format = msg.format;
        const presetOptions = applyReportPreset(options, msg.preset);
        if (!exportRunGate.tryEnter()) {
          void panel.webview.postMessage({ command: "exportComplete" });
          void vscode.window.showWarningMessage(
            "Diffinite: Another report export is already running. Wait for it to finish or cancel it.",
          );
          return;
        }

        let completedExport: { openUri: vscode.Uri; splitMode: boolean } | undefined;
        try {
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
          if (!uri) { return; }

            await vscode.window.withProgress(
              {
                location: vscode.ProgressLocation.Notification,
                title: "Diffinite",
                cancellable: true,
              },
              async (progress, token) => {
                // Read latest PDF font config right before exporting without
                // mutating the analysis options retained by this result panel.
                const exportOptions = { ...presetOptions };
                if (format === "pdf") {
                  exportOptions.pdfFont = getPdfFont();
                  exportOptions.pdfLang = getPdfLang();
                }
                await runExport(
                  sourceDirs.dirA, sourceDirs.dirB,
                  exportOptions, format, uri.fsPath, progress, token
                );
              }
            );
          const splitMode = presetOptions.noMerge && (format === "pdf" || format === "html");
          completedExport = {
            splitMode,
            openUri: splitMode
              ? vscode.Uri.file(path.join(
                path.dirname(uri.fsPath),
                `${path.parse(uri.fsPath).name}_files`,
                format === "pdf" ? "000_cover.pdf" : "index.html",
              ))
              : uri,
          };
        } catch (err: unknown) {
          void showFailure(`${format.toUpperCase()} export`, err);
        } finally {
          exportRunGate.leave();
          void panel.webview.postMessage({ command: "exportComplete" });
        }

        if (completedExport) {
          const action = await vscode.window.showInformationMessage(
            `${format.toUpperCase()} ${completedExport.splitMode ? "split " : ""}report saved.`,
            "Open Report"
          );
          if (action === "Open Report") {
            void vscode.env.openExternal(completedExport.openUri);
          }
        }
      } else if (msg?.command === "export") {
        // Malformed request: re-enable the buttons instead of leaving them stuck.
        void panel.webview.postMessage({ command: "exportComplete" });
      }
    },
    undefined,
    context.subscriptions
  );
}

/* ------------------------------------------------------------------ */
/* HTML Builder                                                        */
/* ------------------------------------------------------------------ */

export function buildResultHtml(report: DiffiniteReport, options: DiffiniteOptions, nonce: string): string {
  const meta = report.metadata;
  const summary = report.summary;
  const view = buildReportViewModel(report);
  const bannersHtml = view.banners.map((banner) => `
    <div class="analysis-banner ${banner.kind}">
      <strong>${escHtml(banner.title)}</strong><br>${escHtml(banner.message)}
    </div>
  `).join("");

  // --- Summary section ---
  let summaryHtml = `
    <div class="summary-bar">
      <span class="stat"><strong>${summary.matched_pairs}</strong> matched pairs</span>
      <span class="stat"><strong>${summary.unmatched_a_count}</strong> unmatched (A)</span>
      <span class="stat"><strong>${summary.unmatched_b_count}</strong> unmatched (B)</span>
    </div>
  `;

  if (meta.exec_mode !== "unknown") {
    summaryHtml += `
      <div class="meta-bar">
        <span>Mode: <strong>${escHtml(meta.exec_mode)}</strong></span>
        <span>K=${meta.k ?? "unknown"}</span>
        <span>W=${meta.w ?? "unknown"}</span>
        <span>effective Jaccard=${meta.threshold === null ? "unknown" : `${meta.threshold.toFixed(1)}%`}</span>
        <span>provenance=${escHtml(meta.threshold_provenance)}</span>
        <span>normalize=${meta.normalize === null ? "unknown" : meta.normalize ? "on" : "off"}</span>
        <span>comments(line/deep)=${escHtml(String(report.preprocessing.line_diff_comments ?? "unknown"))}/${escHtml(String(report.preprocessing.deep_compare_comments ?? "unknown"))}</span>
      </div>
    `;
  }

  // --- Diff blocks ---
  let blocksHtml = "";
  report.results.forEach((r, i) => {

    blocksHtml += `
      <div class="diff-block" id="block-${i}">
        <div class="block-header">
          <span class="block-index">${i + 1} / ${report.results.length}</span>
          <span class="block-files">
            ${escHtml(r.file_a)} &harr; ${escHtml(r.file_b)}
          </span>
          <span class="badge" title="${r.binary ? "SHA-256 comparison only; content was not diffed" : "Content similarity"}">${escHtml(similarityText(r))}</span>
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
  if (view.deepRows.length > 0) {
    const pct = (v: number | null): string => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
    let deepRows = "";
    for (const m of view.deepRows) {
        const jpct = (m.jaccard * 100).toFixed(1);
        const jClass = m.kind === "inconclusive" ? "badge-inconclusive" : "";
        deepRows += `
          <tr>
            <td>${escHtml(m.file_a)}</td>
            <td>${escHtml(m.file_b)}</td>
            <td>${m.shared_hashes}</td>
            <td><span class="badge ${jClass}">${escHtml(m.label)} · ${jpct}%</span></td>
            <td>${pct(m.containment_a_in_b)}</td>
            <td>${pct(m.containment_b_in_a)}</td>
          </tr>
        `;
    }

    deepHtml = `
      <div class="deep-section" id="block-deep">
        <h2>Deep Compare — 유사 후보</h2>
        <table class="deep-table">
          <thead>
            <tr><th>File A</th><th>File B</th><th>Shared</th><th>Jaccard</th><th title="shared ÷ A의 고유 지문 수 (원본 기준)">A in B</th><th title="shared ÷ B의 고유 지문 수 (비교본 기준)">B in A</th></tr>
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
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>Diffinite Results</title>
  <style>${THEME_CSS}${CSS}</style>
</head>
<body>
  <header>
    <h1>Diffinite — Results</h1>
    <div class="dirs">
      <div><strong>A:</strong> ${escHtml(report.dir_a)}</div>
      <div><strong>B:</strong> ${escHtml(report.dir_b)}</div>
    </div>
    ${bannersHtml}
    ${summaryHtml}
  </header>

  ${buildExportSection(options)}

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
    <button id="btnGoExport" title="Go to the export settings (E)">Export&hellip;</button>
  </nav>

  <script nonce="${nonce}">${JS}</script>
</body>
</html>`;
}

/* ------------------------------------------------------------------ */
/* Export section                                                      */
/* ------------------------------------------------------------------ */

const FORMATS: ReadonlyArray<{ id: ReportFormat; label: string }> = [
  { id: "pdf", label: "PDF (print / submission)" },
  { id: "html", label: "HTML (browser)" },
  { id: "md", label: "Markdown (text)" },
];

/**
 * Export settings: preset, format, and the list of what the report will
 * contain. All 3x3 preset/format descriptions are rendered up front and the
 * script only toggles which one is visible, so no data is built in the page.
 */
function buildExportSection(options: DiffiniteOptions): string {
  const selectedPairs = options.selectedFiles === undefined ? null : options.selectedFiles.length;
  const presetOptions = REPORT_PRESETS.map((p, i) =>
    `<option value="${escHtml(p.id)}"${i === 0 ? " selected" : ""}>${escHtml(p.label)}</option>`).join("");
  const presetHelp = REPORT_PRESETS.map((p, i) =>
    `<p class="preset-help" data-preset="${escHtml(p.id)}"${i === 0 ? "" : " hidden"}>${escHtml(p.audience)}</p>`).join("");
  const formatRadios = FORMATS.map((f, i) => `
        <label class="radio"><input type="radio" name="format" value="${f.id}"${i === 0 ? " checked" : ""}> ${escHtml(f.label)}</label>`).join("");
  const contents = REPORT_PRESETS.flatMap((p) => FORMATS.map((f) => {
    const lines = describeReportOutput(applyReportPreset(options, p.id), f.id, { selectedPairs });
    const hidden = p === REPORT_PRESETS[0] && f === FORMATS[0] ? "" : " hidden";
    return `<ul class="contents" data-combo="${escHtml(p.id)}:${f.id}"${hidden}>${lines.map((l) => `<li>${escHtml(l)}</li>`).join("")}</ul>`;
  })).join("");

  return `
  <section class="export-section" id="exportSection" aria-labelledby="export-h">
    <h2 id="export-h">Export report</h2>
    <div class="export-grid">
      <div>
        <label for="presetSelect" class="field-label">Report preset</label>
        <select id="presetSelect">${presetOptions}</select>
        ${presetHelp}
        <fieldset class="formats">
          <legend class="field-label">Format</legend>${formatRadios}
        </fieldset>
        <button type="button" class="btn-primary" id="btnExport">Export&hellip;</button>
        <p class="dim small">You choose the file name and folder next. Presets change only how the report is laid out.</p>
      </div>
      <div>
        <div class="field-label">This report will contain</div>
        ${contents}
      </div>
    </div>
  </section>`;
}

/* ------------------------------------------------------------------ */
/* Inline CSS for the Webview                                          */
/* ------------------------------------------------------------------ */
const CSS = `
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body { font-size: 13px; padding-bottom: 80px; }

  header { padding: 20px 24px 16px; border-bottom: 1px solid var(--border); background: var(--bg-surface); }
  h1 { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
  h2 { font-size: 15px; font-weight: 600; margin: 20px 0 12px; padding-bottom: 4px; border-bottom: 1px solid var(--border); }
  h3 { font-size: 13px; color: var(--fg-dim); margin: 12px 0 6px; }

  .dirs { font-size: 11px; color: var(--fg-dim); margin-bottom: 8px; overflow-wrap: anywhere; }
  .dim { color: var(--fg-dim); }
  .small { font-size: 11px; margin-top: 6px; }

  .summary-bar, .meta-bar { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12px; margin-top: 6px; }
  .meta-bar { color: var(--fg-dim); font-size: 11px; }
  .analysis-banner { margin: 10px 0; padding: 10px 12px; border-radius: 4px; border: 1px solid var(--info); border-left-width: 4px; }
  .analysis-banner.warning { border-color: var(--warning); }

  main { padding: 16px 24px; }

  /* Export */
  .export-section { margin: 0 24px; padding: 4px 0 12px; border-bottom: 1px solid var(--border); }
  .export-grid { display: grid; grid-template-columns: minmax(220px, 1fr) 2fr; gap: 16px 24px; }
  @media (max-width: 640px) { .export-grid { grid-template-columns: 1fr; } }
  .field-label { display: block; font-weight: 600; font-size: 12px; margin-bottom: 4px; }
  #presetSelect { padding: 4px; width: 100%; max-width: 320px; }
  .preset-help { color: var(--fg-dim); font-size: 12px; margin: 6px 0 10px; }
  .formats { border: none; margin: 0 0 10px; }
  .radio { display: block; margin: 3px 0; cursor: pointer; }
  .contents { padding-left: 18px; font-size: 12px; }
  .contents li { margin: 3px 0; }
  ul[hidden], p[hidden] { display: none; }

  button { border-radius: 2px; cursor: pointer; border: 1px solid transparent; font-size: 12px; }
  .btn-primary { background: var(--btn-bg); color: var(--btn-fg); padding: 6px 14px; font-weight: 600; }
  .btn-primary:hover:not(:disabled) { background: var(--btn-hover); }

  /* Diff blocks */
  .diff-block { background: var(--bg); border: 1px solid var(--border); border-radius: 4px; margin-bottom: 16px; overflow: hidden; }
  .diff-block.active { border-color: var(--focus); box-shadow: 0 0 0 1px var(--focus); }
  .block-header { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: var(--bg-surface); border-bottom: 1px solid var(--border); font-size: 12px; }
  .block-index { background: var(--badge-bg); color: var(--badge-fg); padding: 2px 8px; border-radius: 3px; font-weight: 600; font-size: 11px; white-space: nowrap; }
  .block-files { flex: 1; font-family: var(--code-font); font-size: 12px; overflow-wrap: anywhere; }
  .block-stats { display: flex; gap: 12px; padding: 6px 12px; font-size: 11px; color: var(--fg-dim); border-bottom: 1px solid var(--border); }
  .stat-add { color: var(--added-fg); }
  .stat-del { color: var(--deleted-fg); }
  .block-error { padding: 12px 14px; color: var(--error); }
  .block-diff { overflow-x: auto; }

  /* Diff table (HTML produced by differ.py) */
  .difftbl { width: 100%; border-collapse: collapse; font-size: 11px; }
  .difftbl th, .difftbl td { border: 1px solid var(--border); padding: 1px 4px; }
  .difftbl thead th { background: var(--bg-surface); color: var(--fg); font-size: 11px; padding: 4px 6px; }
  .difftbl .ln { color: var(--fg-dim); text-align: right; font-size: 10px; }
  .difftbl .code { white-space: pre-wrap; word-wrap: break-word; font-family: var(--code-font); }
  .difftbl .code pre { margin: 0; padding: 0; font-size: inherit; font-family: inherit; white-space: pre-wrap; }
  .difftbl .del { background: var(--diff-del-line); outline: 1px dashed var(--diff-del-border); outline-offset: -1px; }
  .difftbl .add { background: var(--diff-add-line); outline: 1px dashed var(--diff-add-border); outline-offset: -1px; }
  .difftbl .empty { background: repeating-linear-gradient(135deg, transparent 0 4px, var(--hover-bg) 4px 6px); }
  .difftbl .chg { background: var(--diff-add-line); }
  .difftbl .moved-del { background: var(--diff-del-line); box-shadow: inset 3px 0 0 var(--diff-move-border); }
  .difftbl .moved-add { background: var(--diff-add-line); box-shadow: inset 3px 0 0 var(--diff-move-border); }
  .word-del { background: var(--diff-del-text); text-decoration: line-through; border-radius: 2px; padding: 0 2px; }
  .word-add { background: var(--diff-add-text); text-decoration: underline; border-radius: 2px; padding: 0 2px; }
  /* differ.py sets an inline light background on fold rows; override it for every theme. */
  .difftbl tr.fold td { text-align: center; color: var(--fg-dim) !important; background: var(--bg-surface) !important; }

  /* Pygments token colours (inline styles from differ.py) are designed for light
     backgrounds. In dark and high-contrast themes they become unreadable, so the
     text falls back to the theme colour there. VS Code sets these body classes. */
  body.vscode-dark .block-diff .code span[style],
  body.vscode-high-contrast .block-diff .code span[style] { color: inherit !important; background: none !important; }

  /* Override Pygments error token red border (inline style: border: 1px solid #F00) */
  .block-diff span[style*="border"] { border: none !important; }

  /* Badge: neutral on purpose; a colour scale would read as a verdict. */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
           background: var(--badge-bg); color: var(--badge-fg); white-space: nowrap; }
  .badge-inconclusive { background: transparent; color: var(--fg); border: 1px dashed var(--fg-dim); }

  /* Deep Compare */
  .deep-section { margin-top: 24px; }
  .deep-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .deep-table th, .deep-table td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; overflow-wrap: anywhere; }
  .deep-table thead th { background: var(--bg-surface); }
  .deep-table tbody tr:hover { background: var(--hover-bg); }

  /* Unmatched */
  .unmatched-section { margin-top: 16px; font-size: 12px; }
  .unmatched-section ul { list-style: disc; padding-left: 20px; }
  .unmatched-section li { margin: 2px 0; overflow-wrap: anywhere; }

  /* Floating Nav */
  .floating-nav { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 8px;
                  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 6px; padding: 6px 12px;
                  box-shadow: 0 2px 8px var(--vscode-widget-shadow, rgba(0,0,0,.25)); z-index: 9999; }
  .floating-nav button { background: var(--btn2-bg); color: var(--btn2-fg); border: 1px solid var(--border); border-radius: 2px; padding: 4px 10px; }
  .floating-nav button:hover:not(:disabled) { background: var(--btn2-hover); }
  .nav-pos { color: var(--fg-dim); font-size: 11px; min-width: 50px; text-align: center; }
  .nav-divider { width: 1px; height: 20px; background: var(--border); margin: 0 4px; }
`;

/* ------------------------------------------------------------------ */
/* Inline JS for the Webview                                           */
/* ------------------------------------------------------------------ */
const JS = `
(function() {
  const vscode = acquireVsCodeApi();
  const blocks = document.querySelectorAll('.diff-block');
  const navPos = document.getElementById('navPos');
  const exportBtn = document.getElementById('btnExport');
  const presetSelect = document.getElementById('presetSelect');
  let currentBlock = -1;
  let exportPending = false;

  function currentFormat() {
    const checked = document.querySelector('input[name="format"]:checked');
    return checked ? checked.value : 'pdf';
  }

  function refreshExportDetails() {
    const preset = presetSelect.value;
    const combo = preset + ':' + currentFormat();
    document.querySelectorAll('.contents').forEach(ul => { ul.hidden = ul.dataset.combo !== combo; });
    document.querySelectorAll('.preset-help').forEach(p => { p.hidden = p.dataset.preset !== preset; });
  }

  window.addEventListener('message', (event) => {
    if (event.data && event.data.command === 'exportComplete') {
      exportPending = false;
      exportBtn.disabled = false;
    }
  });

  function goTo(idx) {
    if (blocks.length === 0) return;
    idx = Math.max(0, Math.min(idx, blocks.length - 1));
    blocks.forEach(b => b.classList.remove('active'));
    blocks[idx].classList.add('active');
    blocks[idx].scrollIntoView({ behavior: 'smooth', block: 'start' });
    currentBlock = idx;
    navPos.textContent = (idx + 1) + ' / ' + blocks.length;
  }

  function goExport() {
    document.getElementById('exportSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
    presetSelect.focus({ preventScroll: true });
  }

  document.getElementById('btnNext').addEventListener('click', () => goTo(currentBlock + 1));
  document.getElementById('btnPrev').addEventListener('click', () => goTo(currentBlock - 1));
  document.getElementById('btnGoExport').addEventListener('click', goExport);
  presetSelect.addEventListener('change', refreshExportDetails);
  document.querySelectorAll('input[name="format"]').forEach(r => r.addEventListener('change', refreshExportDetails));

  document.addEventListener('keydown', (e) => {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'j' || e.key === 'J') { e.preventDefault(); goTo(currentBlock + 1); }
    if (e.key === 'k' || e.key === 'K') { e.preventDefault(); goTo(currentBlock - 1); }
    if (e.key === 'e' || e.key === 'E') { e.preventDefault(); goExport(); }
  });

  exportBtn.addEventListener('click', () => {
    if (exportPending) return;
    exportPending = true;
    exportBtn.disabled = true;
    vscode.postMessage({ command: 'export', format: currentFormat(), preset: presetSelect.value });
  });

  refreshExportDetails();
  // Initialize at first block
  if (blocks.length > 0) goTo(0);
})();
`;
