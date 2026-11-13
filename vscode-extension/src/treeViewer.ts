/**
 * Tree Viewer (Phase 1 review and selection UI)
 *
 * Shows the metrics-only JSON report: a summary of what was analyzed, the
 * analysis caveats, and a filterable table of matched pairs. The user picks
 * the pairs to render in the final report, and can open any pair in VS
 * Code's own diff editor without leaving this panel.
 */
import * as vscode from "vscode";
import * as path from "path";
import { DiffiniteReport } from "./runner";
import { buildReportViewModel, hasLineCounts, similarityText } from "./analysisModel";
import {
  addedCountLabel, changeUnit, countLabel, deletedCountLabel, matchMetricName, nameSimilarityLabel, overlapLabel, plural,
} from "./labels";
import { buildReviewSummary } from "./reviewSummary";
import { INCONCLUSIVE_NOTICE, SCREEN_NOTICES } from "./notices";
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

/** Same order as the table: line (or word) match, then name similarity, both descending. */
export function sortForReview(report: DiffiniteReport): DiffiniteReport["results"] {
  return [...report.results].sort((a, b) => {
    if (b.ratio !== a.ratio) { return b.ratio - a.ratio; }
    return b.name_similarity - a.name_similarity;
  });
}

/**
 * A file in A that has no 1:1 pair but that Phase 2 can still analyze: it has
 * Deep Compare (N:M) matches, or it is unmatched. Without a row of its own it
 * could not be selected, and its cross-file matches would drop out of the
 * final report.
 */
export interface UnpairedFileRow {
  file_a: string;
  /** Best Deep Compare match in B (highest Jaccard), if any. */
  best: { file_b: string; jaccard: number } | null;
  deepMatchCount: number;
  hasCandidate: boolean;
}

/** A files with a Deep Compare match at or above the threshold that is not marked inconclusive. */
export function deepCandidateFiles(report: DiffiniteReport): Set<string> {
  return new Set(buildReportViewModel(report).deepRows
    .filter((row) => row.kind === "candidate").map((row) => row.file_a));
}

export function buildUnpairedRows(report: DiffiniteReport): UnpairedFileRow[] {
  const paired = new Set(report.results.map((row) => row.file_a));
  const candidates = deepCandidateFiles(report);
  const rows = new Map<string, UnpairedFileRow>();
  for (const deep of report.deep_results) {
    if (paired.has(deep.file_a) || rows.has(deep.file_a)) { continue; }
    const best = [...deep.matches].sort((x, y) => y.jaccard - x.jaccard)[0];
    rows.set(deep.file_a, {
      file_a: deep.file_a,
      best: best ? { file_b: best.file_b, jaccard: best.jaccard } : null,
      deepMatchCount: deep.matches.length,
      hasCandidate: candidates.has(deep.file_a),
    });
  }
  for (const fileA of report.unmatched_a) {
    if (paired.has(fileA) || rows.has(fileA)) { continue; }
    rows.set(fileA, { file_a: fileA, best: null, deepMatchCount: 0, hasCandidate: false });
  }
  return [...rows.values()].sort((x, y) =>
    Number(y.hasCandidate) - Number(x.hasCandidate)
    || (y.best?.jaccard ?? -1) - (x.best?.jaccard ?? -1)
    || x.file_a.localeCompare(y.file_a));
}

/** Every A path the Phase-2 filter may contain for this report. */
export function selectableFilesA(report: DiffiniteReport): Set<string> {
  return new Set([
    ...report.results.map((row) => row.file_a),
    ...report.deep_results.map((row) => row.file_a),
    ...report.unmatched_a,
  ]);
}

export class TreeViewerPanel {
  public static currentPanel: TreeViewerPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];
  private _disposed = false;
  private _rows: DiffiniteReport["results"] = [];
  private _unpaired: UnpairedFileRow[] = [];
  private _selectable = new Set<string>();
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
      "Diffinite: Review and Select",
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
            // Only accept file-A paths this report lists (1:1 rows, Deep
            // Compare rows and unmatched A files).
            const known = this._selectable;
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
          case "openDeepDiff": {
            const index = message.index;
            if (!Number.isInteger(index) || index < 0 || index >= this._unpaired.length) { return; }
            const row = this._unpaired[index];
            if (row.best) {
              await this.openDiff({ file_a: row.file_a, file_b: row.best.file_b }, "best Deep Compare match");
            }
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

  private async openDiff(
    row: { file_a: string; file_b: string },
    relation = "original files",
  ): Promise<void> {
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
      `A: ${row.file_a} vs. B: ${row.file_b} (${relation})`,
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
    this._unpaired = buildUnpairedRows(report);
    this._selectable = selectableFilesA(report);
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
      <div class="notice ${banner.kind}" role="${banner.kind === "warning" ? "alert" : "note"}">
        <span class="notice-title">${escHtml(banner.title)}</span>
        <span class="notice-body">${escHtml(banner.message)}</span>
      </div>`).join("");

  const factsHtml = summary.facts.map((f) => `
        <div class="fact"><dt>${escHtml(f.label)}</dt><dd class="num">${escHtml(f.value)}</dd></div>`).join("");
  const settingsHtml = summary.settings.map((s) => `<li>${escHtml(s)}</li>`).join("");
  // The inconclusive notice is stated only when a match on this screen is marked inconclusive.
  const anyInconclusive = view.deepRows.some((row) => row.kind === "inconclusive");
  const noticesHtml = [...SCREEN_NOTICES, ...(anyInconclusive ? [INCONCLUSIVE_NOTICE] : [])]
    .map((n) => `<li>${escHtml(n)}</li>`).join("");
  const unit = changeUnit(report.comparison_unit);

  const metric = matchMetricName(report.comparison_unit);
  const deepCandidates = deepCandidateFiles(report);
  const unpaired = buildUnpairedRows(report);
  let rowsHtml = "";
  rows.forEach((r, idx) => {
    const ratioPct = similarityText(r);
    const nameSimPct = nameSimilarityLabel(r.name_similarity);
    // Pre-selection: pairs whose line (or word) match is above 0%, and A files
    // with a Deep Compare match not marked inconclusive. The user can change any of them.
    const defaultChecked = r.ratio > 0.0 || deepCandidates.has(r.file_a) ? "checked" : "";
    const status = r.error ? `Error: ${r.error}` : r.binary ? "Hash only" : "";
    const kind = r.error ? "error" : r.binary ? "binary" : "ok";
    rowsHtml += `
        <tr data-kind="${kind}" data-search="${escHtml((r.file_a + "\n" + r.file_b).toLowerCase())}">
          <td class="c-inc"><input type="checkbox" class="file-cb" value="${escHtml(r.file_a)}" ${defaultChecked}
              aria-label="Include ${escHtml(r.file_a)} in the report"></td>
          <td class="c-path mono">${escHtml(r.file_a)}</td>
          <td class="c-path mono">${escHtml(r.file_b)}</td>
          <td class="c-num num">${nameSimPct}</td>
          <td class="c-num num c-primary">${escHtml(ratioPct)}</td>
          <td class="c-num num">${hasLineCounts(r)
            ? `<span class="added">${addedCountLabel(r.additions)}</span> <span class="deleted">${deletedCountLabel(r.deletions)}</span>`
            : `<span class="dim" title="Not compared line by line">n/a</span>`}</td>
          <td class="c-status${r.error ? " error" : ""}">${escHtml(status)}</td>
          <td class="c-act"><button type="button" class="btn-link open-diff" data-index="${idx}"
              title="Open the two original files in VS Code's diff editor"
              aria-label="Open ${escHtml(r.file_a)} and ${escHtml(r.file_b)} in the diff editor">Open</button></td>
        </tr>`;
  });

  unpaired.forEach((u, idx) => {
    const target = u.best
      ? `Deep Compare: ${u.best.file_b}${u.deepMatchCount > 1 ? ` and ${countLabel(u.deepMatchCount - 1)} more` : ""}`
      : "No 1:1 pair";
    const status = u.deepMatchCount > 0
      ? `No 1:1 pair; ${plural(u.deepMatchCount, "Deep Compare match", "Deep Compare matches")}${u.hasCandidate ? "" : " (inconclusive)"}`
      : "Only in A (no match)";
    const jaccard = u.best ? `Jaccard ${overlapLabel(u.best.jaccard)}` : "n/a";
    rowsHtml += `
        <tr data-kind="nopair" data-search="${escHtml((u.file_a + "\n" + (u.best?.file_b ?? "")).toLowerCase())}">
          <td class="c-inc"><input type="checkbox" class="file-cb" value="${escHtml(u.file_a)}" ${u.hasCandidate ? "checked" : ""}
              aria-label="Include ${escHtml(u.file_a)} in the report"></td>
          <td class="c-path mono">${escHtml(u.file_a)}</td>
          <td class="c-path mono dim">${escHtml(target)}</td>
          <td class="c-num num dim">n/a</td>
          <td class="c-num num c-primary">${escHtml(jaccard)}</td>
          <td class="c-num num dim">n/a</td>
          <td class="c-status">${escHtml(status)}</td>
          <td class="c-act">${u.best ? `<button type="button" class="btn-link open-deep-diff" data-index="${idx}"
              title="Open A and its best Deep Compare match in VS Code's diff editor"
              aria-label="Open ${escHtml(u.file_a)} and ${escHtml(u.best.file_b)} in the diff editor">Open</button>` : ""}</td>
        </tr>`;
  });
  const totalRows = rows.length + unpaired.length;

  const emptyHtml = totalRows === 0
    ? `<p class="empty">No matched file pairs and no other files in A. There is nothing to select.</p>`
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
    <header class="page-head">
      <h1>Review results and select files for the report</h1>
      <p class="dim">Check the summary, then select the pairs the report will include.</p>
    </header>

    <section aria-labelledby="sum-h">
      <h2 id="sum-h">Summary</h2>
      ${bannersHtml}
      <dl class="facts">${factsHtml}
      </dl>
      <details>
        <summary>Settings used for this analysis</summary>
        <ul class="settings">${settingsHtml}</ul>
      </details>
      <h3 class="notices-h">Scope and limitations</h3>
      <ol class="notices">${noticesHtml}</ol>
    </section>

    <section aria-labelledby="sel-h">
      <h2 id="sel-h">Select pairs</h2>
      <div class="selection-note">
        The report covers only the checked files in A, with their 1:1 pair and their Deep Compare matches.
        Files in A without a 1:1 pair are listed after the pairs, so renamed or moved files can be included.
        Deep Compare matches of unchecked files are not in the report.
        In a selective report, the list of files only in B is omitted and the list of files only in A shows only the selected A files;
        the report states how many unmatched files were omitted.
        Pre-selected: pairs with ${metric.toLowerCase()} above 0%, hash-only pairs with identical SHA-256 digests,
        and files in A with a Deep Compare match that is not marked inconclusive.
        Open, in the Diff column, shows the original files in the VS Code diff editor, without preprocessing.
      </div>
      <div class="toolbar" role="toolbar" aria-label="Filter and select">
        <input type="search" id="search" placeholder="Search file names in A or B" aria-label="Search file names">
        <select id="filter" aria-label="Show">
          <option value="all">Show: all pairs</option>
          <option value="checked">Show: selected</option>
          <option value="unchecked">Show: not selected</option>
          <option value="error">Show: errors (${summary.errorPairs})</option>
          <option value="binary">Show: hash only (${summary.binaryPairs})</option>
          <option value="nopair">Show: no 1:1 pair (${unpaired.length})</option>
        </select>
        <span class="toolbar-group">
          <button type="button" class="btn-secondary" id="btn-all">Select shown</button>
          <button type="button" class="btn-secondary" id="btn-none">Clear shown</button>
        </span>
        <span id="shown-count" class="dim shown-count" aria-live="polite"></span>
      </div>
      ${emptyHtml}
      <div class="table-wrap">
        <table class="pairs">
          <colgroup>
            <col class="w-inc"><col><col><col class="w-num"><col class="w-num-l">
            <col class="w-num-l"><col class="w-status"><col class="w-act">
          </colgroup>
          <thead>
            <tr>
              <th scope="col" class="c-inc">Include</th>
              <th scope="col">File A (original)</th>
              <th scope="col">File B (compared)</th>
              <th scope="col" class="c-num" title="Similarity of the file names">Name similarity</th>
              <th scope="col" class="c-num" title="Share of matching ${report.comparison_unit === "word" ? "words" : "lines"}. Hash-only pairs show only whether the SHA-256 digests are identical.">${escHtml(metric)}</th>
              <th scope="col" class="c-num" title="${escHtml(`+: ${unit} only in B. −: ${unit} only in A.`)}">Changes</th>
              <th scope="col">Status</th>
              <th scope="col" class="c-act">Diff</th>
            </tr>
          </thead>
          <tbody id="file-list">${rowsHtml}
          </tbody>
        </table>
      </div>
    </section>
  </main>

  <footer class="footer">
    <div class="footer-status" aria-live="polite"><span id="sel-count" class="sel-count">0</span> of ${plural(totalRows, "A file")} selected</div>
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
  html, body { overflow-x: hidden; }
  body { margin: 0; min-height: 100vh; display: flex; flex-direction: column; }
  main { flex: 1; padding: var(--sp-4) var(--sp-5) var(--sp-4); max-width: 1400px; width: 100%; }
  .page-head { margin-bottom: var(--sp-4); }
  h1 { font-size: var(--fs-h1); font-weight: 600; margin: 0 0 var(--sp-1); line-height: 1.3; }
  .page-head p { margin: 0; }
  h2 { font-size: var(--fs-h2); font-weight: 600; margin: var(--sp-5) 0 var(--sp-2);
       padding-bottom: var(--sp-1); border-bottom: 1px solid var(--border); }
  section:first-of-type h2 { margin-top: 0; }
  .note { font-size: var(--fs-sm); margin: var(--sp-2) 0 0; }

  /* Summary facts: one label | value ledger, figures right-aligned. A single
     column keeps every rule aligned when a long label wraps. */
  .facts { margin: var(--sp-3) 0 0; max-width: 760px; border-top: 1px solid var(--border); }
  .fact { display: grid; grid-template-columns: minmax(0, 1fr) minmax(8ch, max-content); column-gap: var(--sp-5);
          align-items: baseline; padding: 3px var(--sp-2); border-bottom: 1px solid var(--border); }
  .fact dt { color: var(--fg-dim); min-width: 0; overflow-wrap: anywhere; }
  .fact dd { margin: 0; overflow-wrap: anywhere; white-space: normal; }
  .notices-h { font-size: var(--fs-sm); font-weight: 600; margin: var(--sp-4) 0 var(--sp-1); }
  .notices { margin: 0; padding-left: var(--sp-5); font-size: var(--fs-sm); color: var(--fg-dim); max-width: 120ch; }
  .notices li { margin: 2px 0; }

  details { margin: var(--sp-3) 0 0; }
  summary { cursor: pointer; color: var(--fg); width: fit-content; }
  summary:hover { color: var(--accent); }
  .settings { margin: var(--sp-2) 0 0; padding-left: var(--sp-5); color: var(--fg-dim); font-size: var(--fs-sm); overflow-wrap: anywhere; }
  .settings li { margin: 2px 0; }

  .selection-note { font-size: var(--fs-sm); color: var(--fg-dim); max-width: 120ch; margin: 0 0 var(--sp-3); }

  .toolbar { display: flex; flex-wrap: wrap; gap: var(--sp-2); align-items: center; margin-bottom: var(--sp-2); }
  .toolbar input[type=search] { flex: 1 1 240px; min-width: 0; height: var(--control-h); padding: 2px 6px; }
  .toolbar select { height: var(--control-h); padding: 0 4px; max-width: 100%; }
  .toolbar-group { display: inline-flex; gap: var(--sp-1); }
  .shown-count { font-size: var(--fs-sm); margin-left: auto; }

  /* Pair table: rules between rows only, as in VS Code lists and tables. */
  .table-wrap { overflow-x: auto; border-top: 1px solid var(--border); }
  table.pairs { width: 100%; min-width: 780px; border-collapse: collapse; table-layout: fixed; }
  .w-inc { width: 64px; } .w-num { width: 120px; } .w-num-l { width: 104px; } .w-status { width: 136px; } .w-act { width: 56px; }
  .pairs th, .pairs td { padding: 4px var(--sp-2); text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); }
  .pairs th { position: sticky; top: 0; z-index: 1; background: var(--bg); font-size: var(--fs-sm); font-weight: 600;
              color: var(--fg-dim); vertical-align: bottom; }
  .pairs tbody tr:hover { background: var(--hover-bg); }
  .pairs td.mono { font-size: var(--fs-sm); }
  .c-inc { text-align: center !important; }
  .c-inc input { vertical-align: middle; }
  .c-num { text-align: right !important; }
  .c-primary { color: var(--fg); }
  .c-path { overflow-wrap: anywhere; word-break: break-word; }
  .c-status { font-size: var(--fs-sm); color: var(--fg-dim); overflow-wrap: anywhere; }
  .c-status.error { color: var(--error); }
  .c-act { text-align: right !important; }
  .added, .deleted { color: inherit; }
  .empty { padding: var(--sp-3); border: 1px dashed var(--border); color: var(--fg-dim); }
  tr[hidden] { display: none; }

  .footer { position: sticky; bottom: 0; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
            gap: var(--sp-2) var(--sp-3); padding: var(--sp-2) var(--sp-5); background: var(--bg-surface); border-top: 1px solid var(--border); }
  .sel-count { font-variant-numeric: tabular-nums; font-weight: 600; }
  .footer-actions { display: flex; gap: var(--sp-2); margin-left: auto; }
  @media (max-width: 600px) {
    main { padding: var(--sp-3) var(--sp-4); }
    .footer { padding: var(--sp-2) var(--sp-4); }
    .shown-count { margin-left: 0; flex-basis: 100%; }
  }
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
    genBtn.textContent = 'Generate report (' + count + (count === 1 ? ' file)' : ' files)');
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
      if (visible && (mode === 'error' || mode === 'binary' || mode === 'nopair')) visible = row.dataset.kind === mode;
      row.hidden = !visible;
      if (visible) shown++;
    });
    const hiddenSelected = boxes.filter((cb, i) => cb.checked && rows[i].hidden).length;
    shownLabel.textContent = 'Showing ' + shown + ' of ' + rows.length +
      (hiddenSelected ? '; ' + hiddenSelected + (hiddenSelected === 1 ? ' selected row is' : ' selected rows are') + ' hidden by the filter' : '');
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
    const deepBtn = e.target.closest('.open-deep-diff');
    if (deepBtn) vscode.postMessage({ command: 'openDeepDiff', index: Number(deepBtn.dataset.index) });
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
