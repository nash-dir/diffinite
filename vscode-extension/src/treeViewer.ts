/**
 * Tree Viewer (Phase 1 review and selection UI)
 *
 * Shows the metrics-only JSON report: a summary of what was analysed, the
 * analysis caveats, and a filterable table of matched pairs. The user picks
 * the pairs to render in the final report, and can open any pair in VS
 * Code's own diff editor without leaving this panel.
 */
import * as vscode from "vscode";
import * as path from "path";
import { DiffiniteReport } from "./runner";
import { buildReportViewModel, similarityText } from "./analysisModel";
import { buildReviewSummary } from "./reviewSummary";
import { escHtml, getNonce, THEME_CSS } from "./webviewUtils";

export interface SourceDirs { dirA: string; dirB: string; }

/** Resolve a report-relative path inside `root`; null if it would escape it. */
export function resolveInside(root: string, relative: string): string | null {
  const base = path.resolve(root);
  const target = path.resolve(base, relative);
  const rel = path.relative(base, target);
  // ".." as a whole first segment escapes; a name such as "..eslintrc" does not.
  if (rel === "" || rel === ".." || rel.startsWith(".." + path.sep) || path.isAbsolute(rel)) { return null; }
  return target;
}

/** Same order as the table: content similarity, then name similarity, both descending. */
export function sortForReview(report: DiffiniteReport): DiffiniteReport["results"] {
  return [...report.results].sort((a, b) => {
    if (b.ratio !== a.ratio) { return b.ratio - a.ratio; }
    return b.name_similarity - a.name_similarity;
  });
}

export class TreeViewerPanel {
  public static currentPanel: TreeViewerPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];
  private _disposed = false;
  private _rows: DiffiniteReport["results"] = [];
  private _dirs: SourceDirs;

  // Callback invoked when user clicks "Generate report"
  private _onGenerateCallback: ((selectedFilesA: string[]) => Promise<void>) | undefined;

  public static createOrShow(
    report: DiffiniteReport,
    dirs: SourceDirs,
    onGenerate: (selectedFilesA: string[]) => Promise<void>
  ) {
    if (TreeViewerPanel.currentPanel) {
      TreeViewerPanel.currentPanel._panel.reveal(vscode.ViewColumn.Active);
      TreeViewerPanel.currentPanel._dirs = dirs;
      TreeViewerPanel.currentPanel.update(report);
      TreeViewerPanel.currentPanel._onGenerateCallback = onGenerate;
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      "diffiniteTreeViewer",
      "Diffinite — Review & Select",
      vscode.ViewColumn.Active,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    TreeViewerPanel.currentPanel = new TreeViewerPanel(panel, report, dirs, onGenerate);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    report: DiffiniteReport,
    dirs: SourceDirs,
    onGenerate: (selectedFilesA: string[]) => Promise<void>
  ) {
    this._panel = panel;
    this._dirs = dirs;
    this._onGenerateCallback = onGenerate;
    this.update(report);

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    this._panel.webview.onDidReceiveMessage(
      async (message) => {
        switch (message?.command) {
          case "generate": {
            // Only accept file-A paths that are rows of this report.
            const known = new Set(this._rows.map((r) => r.file_a));
            const selectedFiles: string[] = Array.isArray(message.files)
              ? message.files.filter((f: unknown): f is string => typeof f === "string" && known.has(f))
              : [];
            const callback = this._onGenerateCallback;
            this.dispose(); // Close first so a second Generate message cannot race.
            if (callback) {
              await callback(selectedFiles);
            }
            return;
          }
          case "openDiff": {
            const index = message.index;
            if (!Number.isInteger(index) || index < 0 || index >= this._rows.length) { return; }
            await this.openDiff(this._rows[index]);
            return;
          }
          case "cancel":
            this.dispose();
            return;
        }
      },
      null,
      this._disposables
    );
  }

  private async openDiff(row: DiffiniteReport["results"][number]): Promise<void> {
    const fileA = resolveInside(this._dirs.dirA, row.file_a);
    const fileB = resolveInside(this._dirs.dirB, row.file_b);
    if (!fileA || !fileB) {
      void vscode.window.showWarningMessage("Diffinite: this pair's paths are outside the compared folders and were not opened.");
      return;
    }
    await vscode.commands.executeCommand(
      "vscode.diff",
      vscode.Uri.file(fileA),
      vscode.Uri.file(fileB),
      `A: ${row.file_a} ↔ B: ${row.file_b} (original files)`,
      { viewColumn: vscode.ViewColumn.Beside, preview: true, preserveFocus: true },
    );
  }

  public dispose() {
    if (this._disposed) { return; }
    this._disposed = true;
    TreeViewerPanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const x = this._disposables.pop();
      if (x) { x.dispose(); }
    }
  }

  private update(report: DiffiniteReport) {
    this._rows = sortForReview(report);
    this._panel.webview.html = buildTreeViewerHtml(report, this._rows, getNonce());
  }
}

export function buildTreeViewerHtml(
  report: DiffiniteReport,
  rows: DiffiniteReport["results"],
  nonce: string,
): string {
  const view = buildReportViewModel(report);
  const summary = buildReviewSummary(report);

  const bannersHtml = view.banners.map((banner) => `
      <div class="banner ${banner.kind}" role="${banner.kind === "warning" ? "alert" : "note"}">
        <strong>${escHtml(banner.title)}</strong><br>${escHtml(banner.message)}
      </div>`).join("");

  const factsHtml = summary.facts.map((f) => `
        <div class="fact${f.attention ? " attention" : ""}"><dt>${escHtml(f.label)}</dt><dd>${escHtml(f.value)}</dd></div>`).join("");
  const settingsHtml = summary.settings.map((s) => `<li>${escHtml(s)}</li>`).join("");

  let rowsHtml = "";
  rows.forEach((r, idx) => {
    const ratioPct = similarityText(r);
    const nameSimPct = r.name_similarity.toFixed(1) + "%";
    // Pre-selection (unchanged from earlier versions): pairs whose content
    // similarity is above 0%. The user can change any of them.
    const defaultChecked = r.ratio > 0.0 ? "checked" : "";
    const status = r.error ? `Error: ${r.error}` : r.binary ? "Hash only" : "";
    const kind = r.error ? "error" : r.binary ? "binary" : "ok";
    rowsHtml += `
        <tr data-kind="${kind}" data-search="${escHtml((r.file_a + "\n" + r.file_b).toLowerCase())}">
          <td class="c-inc"><input type="checkbox" class="file-cb" value="${escHtml(r.file_a)}" ${defaultChecked}
              aria-label="Include ${escHtml(r.file_a)} in the report"></td>
          <td class="c-path mono">${escHtml(r.file_a)}</td>
          <td class="c-path mono">${escHtml(r.file_b)}</td>
          <td class="c-num">${nameSimPct}</td>
          <td class="c-num"><strong>${escHtml(ratioPct)}</strong></td>
          <td class="c-num"><span class="added">+${r.additions}</span> <span class="deleted">&minus;${r.deletions}</span></td>
          <td class="c-status${r.error ? " error" : ""}">${escHtml(status)}</td>
          <td class="c-act"><button type="button" class="btn-link open-diff" data-index="${idx}"
              title="Open the two original files in VS Code's diff editor">Diff</button></td>
        </tr>`;
  });

  const emptyHtml = rows.length === 0
    ? `<p class="empty">No matched file pairs. There is nothing to select for a pair-by-pair report.</p>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>Review &amp; Select</title>
  <style>${THEME_CSS}${TREE_CSS}</style>
</head>
<body>
  <main>
    <h1>Review results and select files for the report</h1>
    <p class="dim">Analysis finished. Check the summary, then choose which pairs the report will include.</p>

    <section aria-labelledby="sum-h">
      <h2 id="sum-h">Summary</h2>
      <dl class="facts">${factsHtml}
      </dl>
      <details>
        <summary>Settings used for this analysis</summary>
        <ul class="settings">${settingsHtml}</ul>
      </details>
      ${bannersHtml}
      <p class="dim note">Values are measurements of textual similarity. They do not say whether code was copied or whether any right was infringed.</p>
    </section>

    <section aria-labelledby="sel-h">
      <h2 id="sel-h">Select pairs</h2>
      <div class="selection-note">
        <strong>How the selection is used:</strong>
        the report renders only the checked pairs (matched by the file in A).
        Lists of unmatched files are omitted from a selective report.
        Pre-selected: pairs with content similarity above 0%, and hash-only pairs whose SHA-256 hashes are identical.
        <em>Diff</em> opens the original files in VS Code's diff editor, without Diffinite's preprocessing.
      </div>
      <div class="toolbar" role="toolbar" aria-label="Filter and select">
        <input type="search" id="search" placeholder="Search file names in A or B" aria-label="Search file names">
        <select id="filter" aria-label="Show">
          <option value="all">Show: all pairs</option>
          <option value="checked">Show: selected</option>
          <option value="unchecked">Show: not selected</option>
          <option value="error">Show: errors (${summary.errorPairs})</option>
          <option value="binary">Show: hash only (${summary.binaryPairs})</option>
        </select>
        <button type="button" class="btn-secondary" id="btn-all">Select shown</button>
        <button type="button" class="btn-secondary" id="btn-none">Clear shown</button>
        <span id="shown-count" class="dim" aria-live="polite"></span>
      </div>
      ${emptyHtml}
      <div class="table-wrap">
        <table>
          <colgroup>
            <col style="width:40px"><col><col><col style="width:68px"><col style="width:96px">
            <col style="width:92px"><col style="width:96px"><col style="width:48px">
          </colgroup>
          <thead>
            <tr>
              <th scope="col" class="c-inc">Inc.</th>
              <th scope="col">File A (original)</th>
              <th scope="col">File B (compared)</th>
              <th scope="col" class="c-num" title="Similarity of the file names (0–100)">Name sim.</th>
              <th scope="col" class="c-num" title="Share of matching lines (or words). Hash-only pairs show only whether the SHA-256 hashes are identical.">Content sim.</th>
              <th scope="col" class="c-num" title="+ lines only in B, − lines only in A">Changes</th>
              <th scope="col">Status</th>
              <th scope="col"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody id="file-list">${rowsHtml}
          </tbody>
        </table>
      </div>
    </section>
  </main>

  <footer class="footer">
    <div aria-live="polite"><strong id="sel-count">0</strong> of ${rows.length} pairs selected</div>
    <div class="footer-actions">
      <button type="button" class="btn-secondary" id="btn-cancel">Close</button>
      <button type="button" class="btn-primary" id="btn-generate">Generate report</button>
    </div>
  </footer>

  <script nonce="${nonce}">${TREE_JS}</script>
</body>
</html>`;
}

const TREE_CSS = `
  * { box-sizing: border-box; }
  body { margin: 0; font-size: 13px; }
  main { padding: 16px 20px 8px; }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
  h2 { font-size: 14px; font-weight: 600; margin: 18px 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--border); }
  .dim { color: var(--fg-dim); }
  .note { font-size: 12px; margin: 8px 0 0; }
  .facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 6px; margin: 0; }
  .fact { border: 1px solid var(--border); background: var(--bg-surface); border-radius: 4px; padding: 5px 8px;
          display: flex; flex-direction: column-reverse; justify-content: flex-end; }
  .fact dt { color: var(--fg-dim); font-size: 11px; line-height: 1.3; }
  .fact dd { margin: 0; font-size: 15px; font-weight: 600; overflow-wrap: anywhere; }
  .fact.attention { border-color: var(--warning); border-left-width: 4px; }
  details { margin: 10px 0; }
  summary { cursor: pointer; color: var(--accent); }
  .settings { margin: 6px 0 0; padding-left: 20px; color: var(--fg-dim); font-size: 12px; }
  .banner { margin: 8px 0; padding: 8px 10px; border-radius: 4px; border: 1px solid var(--info); border-left-width: 4px; }
  .banner.warning { border-color: var(--warning); }
  .selection-note { font-size: 12px; padding: 8px 10px; border-left: 3px solid var(--accent); background: var(--bg-surface); margin-bottom: 10px; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
  .toolbar input[type=search] { flex: 1 1 220px; min-width: 0; padding: 4px 6px; }
  .toolbar select { padding: 3px 4px; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; min-width: 600px; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
  th, td { border: 1px solid var(--border); padding: 5px 6px; text-align: left; vertical-align: top; }
  th { background: var(--bg-surface); position: sticky; top: 0; z-index: 1; font-weight: 600; }
  tbody tr:hover { background: var(--hover-bg); }
  .c-inc { text-align: center; }
  .c-num { text-align: right; }
  .c-path { overflow-wrap: anywhere; word-break: break-word; }
  .c-status { font-size: 11px; overflow-wrap: anywhere; }
  .c-status.error { color: var(--error); }
  .added { color: var(--added-fg); }
  .deleted { color: var(--deleted-fg); }
  .empty { padding: 12px; border: 1px dashed var(--border); }
  tr[hidden] { display: none; }
  button { border-radius: 2px; padding: 4px 12px; cursor: pointer; border: 1px solid transparent; }
  .btn-primary { background: var(--btn-bg); color: var(--btn-fg); font-weight: 600; }
  .btn-primary:hover:not(:disabled) { background: var(--btn-hover); }
  .btn-secondary { background: var(--btn2-bg); color: var(--btn2-fg); border-color: var(--border); }
  .btn-secondary:hover:not(:disabled) { background: var(--btn2-hover); }
  .btn-link { background: none; color: var(--accent); padding: 0 2px; text-decoration: underline; }
  .footer { position: sticky; bottom: 0; display: flex; justify-content: space-between; align-items: center; gap: 12px;
            padding: 10px 20px; background: var(--bg-surface); border-top: 1px solid var(--border); }
  .footer-actions { display: flex; gap: 8px; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
`;

const TREE_JS = `
(function () {
  const vscode = acquireVsCodeApi();
  const rows = Array.from(document.querySelectorAll('#file-list tr'));
  const boxes = rows.map(r => r.querySelector('.file-cb'));
  const countLabel = document.getElementById('sel-count');
  const shownLabel = document.getElementById('shown-count');
  const genBtn = document.getElementById('btn-generate');
  const search = document.getElementById('search');
  const filter = document.getElementById('filter');

  function updateCount() {
    let count = 0;
    boxes.forEach(cb => { if (cb.checked) count++; });
    countLabel.textContent = String(count);
    genBtn.textContent = 'Generate report (' + count + ' pairs)';
    genBtn.disabled = count === 0;
  }

  function applyFilter() {
    const q = search.value.trim().toLowerCase();
    const mode = filter.value;
    let shown = 0;
    rows.forEach((row, i) => {
      const cb = boxes[i];
      let visible = !q || row.dataset.search.indexOf(q) !== -1;
      if (visible && mode === 'checked') visible = cb.checked;
      if (visible && mode === 'unchecked') visible = !cb.checked;
      if (visible && (mode === 'error' || mode === 'binary')) visible = row.dataset.kind === mode;
      row.hidden = !visible;
      if (visible) shown++;
    });
    const hiddenSelected = boxes.filter((cb, i) => cb.checked && rows[i].hidden).length;
    shownLabel.textContent = 'Showing ' + shown + ' of ' + rows.length +
      (hiddenSelected ? ' · ' + hiddenSelected + ' selected pair(s) hidden by the filter' : '');
  }

  function setShown(checked) {
    rows.forEach((row, i) => { if (!row.hidden) boxes[i].checked = checked; });
    updateCount();
    applyFilter();
  }

  document.getElementById('file-list').addEventListener('change', () => { updateCount(); applyFilter(); });
  document.getElementById('file-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.open-diff');
    if (btn) vscode.postMessage({ command: 'openDiff', index: Number(btn.dataset.index) });
  });
  search.addEventListener('input', applyFilter);
  filter.addEventListener('change', applyFilter);
  document.getElementById('btn-all').addEventListener('click', () => setShown(true));
  document.getElementById('btn-none').addEventListener('click', () => setShown(false));
  document.getElementById('btn-cancel').addEventListener('click', () => vscode.postMessage({ command: 'cancel' }));
  genBtn.addEventListener('click', () => {
    genBtn.disabled = true;
    const selected = [];
    boxes.forEach(cb => { if (cb.checked) selected.push(cb.value); });
    vscode.postMessage({ command: 'generate', files: selected });
  });

  updateCount();
  applyFilter();
})();
`;
