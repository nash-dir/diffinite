/**
 * Options Panel — collects target directories & analysis options via a Webview form.
 *
 * Renders CLI options as checkboxes, dropdowns, and number inputs.
 * Acts as the "Home Base" UI that triggers the pipeline logic.
 */
import * as vscode from "vscode";
import { DiffiniteOptions, defaultOptions } from "./runner";
import { getDefaultMode, getBatesPresets, BatesPreset, getPdfFont, getPdfLang } from "./config";

export interface TaskHistoryEntry {
  id: string;
  label: string;
  dirA: string;
  dirB: string;
  options: DiffiniteOptions;
}

/** Escape a value for safe interpolation into HTML text or a double-quoted attribute. */
function escHtml(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Random nonce for the webview Content-Security-Policy (allows our inline script only). */
function getNonce(): string {
  let s = "";
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) s += chars.charAt(Math.floor(Math.random() * chars.length));
  return s;
}

/**
 * Open the main options panel.
 * @param context VSCode extension context
 * @param onRun Callback triggered when user clicks "Run Analysis"
 */
export function showOptionsPanel(
  context: vscode.ExtensionContext,
  onRun: (dirA: string, dirB: string, options: DiffiniteOptions) => Promise<void>
): void {
  const panel = vscode.window.createWebviewPanel(
    "diffiniteOptions",
    "Diffinite — Analysis",
    vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  const lastDirs = context.globalState.get<{ dirA: string; dirB: string }>("diffinite.lastDirs") || { dirA: "", dirB: "" };
  const lastRunOptions = context.globalState.get<Partial<DiffiniteOptions>>("diffinite.lastRunOptions");

  const config = vscode.workspace.getConfiguration("diffinite");
  const defaults = { ...defaultOptions(), ...(lastRunOptions || {}) };
  defaults.mode = lastRunOptions?.mode || getDefaultMode() as "simple" | "deep";
  defaults.workers = lastRunOptions?.workers || config.get<number>("workers", 4);
  defaults.noMerge = lastRunOptions?.noMerge ?? config.get<boolean>("noMerge", false);
  defaults.preserveTree = lastRunOptions?.preserveTree ?? config.get<boolean>("preserveTree", true);
  defaults.pdfFont = lastRunOptions?.pdfFont || getPdfFont();
  defaults.pdfLang = lastRunOptions?.pdfLang || getPdfLang();
  
  const presets = getBatesPresets();
  const taskHistory = context.globalState.get<TaskHistoryEntry[]>("diffinite.taskHistory") || [];

  panel.webview.html = buildOptionsHtml(defaults, presets, lastDirs, taskHistory);

  panel.webview.onDidReceiveMessage(
    async (msg: { command: string; target?: string; options?: DiffiniteOptions; dirA?: string; dirB?: string; saveHistory?: boolean }) => {
      if (msg.command === "run" && msg.options && msg.dirA && msg.dirB) {
        
        // Save Persistence
        await context.globalState.update("diffinite.lastRunOptions", msg.options);
        await context.globalState.update("diffinite.lastDirs", { dirA: msg.dirA, dirB: msg.dirB });

        // Save History if requested
        if (msg.saveHistory) {
          const history = context.globalState.get<TaskHistoryEntry[]>("diffinite.taskHistory") || [];
          const now = new Date();
          const baseA = msg.dirA.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "A";
          const baseB = msg.dirB.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "B";
          const label = `${now.toLocaleDateString()} ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} | ${baseA} vs ${baseB}`;
          
          history.push({ id: now.getTime().toString(), label, dirA: msg.dirA, dirB: msg.dirB, options: msg.options });
          if (history.length > 50) history.shift(); // Cap history size
          await context.globalState.update("diffinite.taskHistory", history);
        }
        // Save Presentation options automatically to Global Settings
        if (msg.options.pdfFont !== undefined) {
          await config.update("pdfFont", msg.options.pdfFont, vscode.ConfigurationTarget.Global);
        }
        if (msg.options.pdfLang !== undefined) {
          await config.update("pdfLang", msg.options.pdfLang, vscode.ConfigurationTarget.Global);
        }

        // Trigger the pipeline but DO NOT dispose the panel.
        // It stays open so users can tweak paths/options and run again safely!
        try {
          await onRun(msg.dirA, msg.dirB, msg.options);
        } finally {
          panel.webview.postMessage({ command: 'runComplete' });
        }
      } else if (msg.command === "browse" && msg.target) {
        // Open native directory selection dialog
        const isDirA = msg.target === "dirA";
        const uri = await vscode.window.showOpenDialog({
          canSelectFolders: true,
          canSelectFiles: false,
          canSelectMany: false,
          openLabel: `Select Directory ${isDirA ? 'A (Original)' : 'B (Suspect)'}`,
          title: `Diffinite — Select Directory ${isDirA ? 'A' : 'B'}`,
        });
        if (uri && uri.length > 0) {
          // Send selected path back to update the webview input
          panel.webview.postMessage({ command: "setPath", target: msg.target, path: uri[0].fsPath });
        }
      } else if (msg.command === "cancel") {
        panel.dispose();
      } else if (msg.command === "editIgnore") {
        vscode.commands.executeCommand("diffinite.editIgnoreList");
      } else if (msg.command === "flushHistory") {
        await context.globalState.update("diffinite.taskHistory", []);
        vscode.window.showInformationMessage("Task History flushed.");
        panel.dispose();
        vscode.commands.executeCommand("diffinite.compare");
      }
    },
    undefined,
    context.subscriptions
  );
}

function buildOptionsHtml(defaults: DiffiniteOptions, presets: BatesPreset[], lastDirs: { dirA: string; dirB: string }, taskHistory: TaskHistoryEntry[]): string {
  const nonce = getNonce();
  const presetOptions = presets.map((p) => {
    const label = `${escHtml(p.name)} (${escHtml(p.prefix)}…${escHtml(p.suffix || "")})`;
    return `<option value="${escHtml(p.name)}" data-prefix="${escHtml(p.prefix || "")}" data-suffix="${escHtml(p.suffix || "")}" data-start="${escHtml(p.nextBatesNumber || 1)}">${label}</option>`;
  }).join("\n");

  const historyOptions = taskHistory.map((h) => {
    return `<option value="${escHtml(h.id)}">${escHtml(h.label)}</option>`;
  }).join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>Diffinite Options</title>
  <style>${OPTIONS_CSS}</style>
</head>
<body>
  <h1>Diffinite — Code Comparison</h1>

  <form id="optForm">
    <section>
      <h2>Task History</h2>
      <div class="field" style="display:flex; gap: 8px; align-items:center;">
        <select id="historySelect" style="flex-grow: 1;">
          <option value="">— Select a previous task to load —</option>
          ${historyOptions}
        </select>
        <button type="button" id="btnLoadHistory" class="btn-secondary" style="flex-shrink: 0;" ${taskHistory.length===0?'disabled':''}>Load Task</button>
        <button type="button" id="btnFlushHistory" class="btn-secondary" style="flex-shrink: 0; color:var(--error);" ${taskHistory.length===0?'disabled':''}>Flush All</button>
      </div>
    </section>

    <section>
      <h2>Target Directories</h2>
      <div class="field dir-input-row" style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
        <label for="dirA" style="width: 80px; flex-shrink: 0;">Dir A (Org)</label>
        <input type="text" id="dirA" class="path-input" style="flex-grow: 1; max-width: none;" placeholder="e.g. C:/source/project_v1" value="${escHtml(lastDirs.dirA || '')}">
        <button type="button" id="btnBrowseA" class="btn-secondary" style="flex-shrink: 0;">Browse</button>
      </div>
      <div class="field dir-input-row" style="display: flex; gap: 8px; align-items: center;">
        <label for="dirB" style="width: 80px; flex-shrink: 0;">Dir B (Susp)</label>
        <input type="text" id="dirB" class="path-input" style="flex-grow: 1; max-width: none;" placeholder="e.g. C:/source/project_v2" value="${escHtml(lastDirs.dirB || '')}">
        <button type="button" id="btnBrowseB" class="btn-secondary" style="flex-shrink: 0;">Browse</button>
      </div>
      <div id="dirError" style="color:var(--error); font-size:12px; margin-top:8px; display:none;">Please specify both directories!</div>
    </section>

    <section>
      <h2>Execution</h2>
      <div class="field">
        <label for="mode">Mode</label>
        <select id="mode" name="mode">
          <option value="deep" ${defaults.mode === "deep" ? "selected" : ""}>Deep (1:1 + N:M Winnowing)</option>
          <option value="simple" ${defaults.mode === "simple" ? "selected" : ""}>Simple (1:1 only)</option>
        </select>
      </div>
      <div class="field">
        <label for="workers">Parallel CPU Cores (Workers)</label>
        <input type="number" id="workers" value="${defaults.workers}" min="1" max="32" step="1">
      </div>
    </section>

    <section>
      <h2>Comparison</h2>
      <div class="field checkbox">
        <input type="checkbox" id="stripComments" ${defaults.stripComments ? "checked" : ""}>
        <label for="stripComments">Strip comments before comparison</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="byWord" ${defaults.byWord ? "checked" : ""}>
        <label for="byWord">Compare by word (instead of by line)</label>
      </div>
      <div class="field checkbox" style="margin-left:24px">
        <input type="checkbox" id="normalizeWhitespace" ${defaults.normalizeWhitespace ? "checked" : ""}>
        <label for="normalizeWhitespace">Normalize whitespace (tab→space, collapse multiple spaces)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="collapseIdentical" ${defaults.collapseIdentical ? "checked" : ""}>
        <label for="collapseIdentical">Collapse identical blocks (3 context lines)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="detectMoved" ${defaults.detectMoved ? "checked" : ""}>
        <label for="detectMoved">Detect moved code blocks (highlight in purple/blue)</label>
      </div>
      <div class="field">
        <label for="threshold">File name matching threshold (0–100)</label>
        <input type="number" id="threshold" value="${defaults.threshold}" min="0" max="100" step="1">
      </div>
      <div class="field">
        <label for="binaryHandling">Binary files</label>
        <select id="binaryHandling">
          <option value="exclude" ${defaults.binaryHandling === "exclude" ? "selected" : ""}>Exclude</option>
          <option value="hash" ${defaults.binaryHandling === "hash" ? "selected" : ""}>Hash compare only</option>
          <option value="error" ${defaults.binaryHandling === "error" ? "selected" : ""}>Show error</option>
        </select>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="noAutojunk" ${defaults.noAutojunk ? "checked" : ""}>
        <label for="noAutojunk">Disable autojunk (precise but slower)</label>
      </div>
    </section>

    <section class="deep-section" id="deepSection">
      <h2>Deep Compare (Winnowing)</h2>
      <div class="field checkbox">
        <input type="checkbox" id="normalize" ${defaults.normalize ? "checked" : ""}>
        <label for="normalize">Normalize identifiers (Type-2 clone detection)</label>
      </div>
      <div class="field">
        <label for="kGram">K-gram size</label>
        <input type="number" id="kGram" value="${defaults.kGram}" min="2" max="20" step="1">
      </div>
      <div class="field">
        <label for="window">Window size</label>
        <input type="number" id="window" value="${defaults.window}" min="1" max="20" step="1">
      </div>
      <div class="field">
        <label for="thresholdDeep">Min Jaccard threshold (0–100)</label>
        <input type="number" id="thresholdDeep" value="${defaults.thresholdDeep}" min="0" max="100" step="1">
      </div>
    </section>

    <section>
      <h2>Report Options</h2>
      <div class="field checkbox">
        <input type="checkbox" id="noMerge" ${defaults.noMerge ? "checked" : ""}>
        <label for="noMerge">Save individual PDF reports for each file (No Merge)</label>
      </div>
      <div class="field checkbox" style="margin-left:24px">
        <input type="checkbox" id="preserveTree" ${defaults.preserveTree ? "checked" : ""} ${!defaults.noMerge ? "disabled" : ""}>
        <label for="preserveTree">Preserve original folder tree structure (uncheck for flat + index.html)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="pageNumber" ${defaults.pageNumber ? "checked" : ""}>
        <label for="pageNumber">Show page numbers (Page n / N)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="fileNumber" ${defaults.fileNumber ? "checked" : ""}>
        <label for="fileNumber">Show file numbers (File n / N)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="batesNumber" ${defaults.batesNumber ? "checked" : ""}>
        <label for="batesNumber">Stamp Bates numbers</label>
      </div>
      <div class="bates-details" id="batesDetails">
        <div class="field">
          <label for="batesPreset">Preset</label>
          <select id="batesPreset">
            <option value="">— Manual —</option>
            ${presetOptions}
          </select>
        </div>
        <div class="field">
          <label for="batesPrefix">Prefix</label>
          <input type="text" id="batesPrefix" value="${escHtml(defaults.batesPrefix)}" placeholder="e.g. PLAINTIFF-">
        </div>
        <div class="field">
          <label for="batesSuffix">Suffix</label>
          <input type="text" id="batesSuffix" value="${escHtml(defaults.batesSuffix)}" placeholder="e.g. -CONFIDENTIAL">
        </div>
        <div class="field">
          <label for="batesStart">Starting number</label>
          <input type="number" id="batesStart" value="${defaults.batesStart}" min="1" step="1">
        </div>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="hash" ${defaults.hash ? "checked" : ""}>
        <label for="hash">Embed SHA-256 file hashes in report</label>
      </div>
      <div class="field">
        <label for="uncomparedFiles">Uncompared files list</label>
        <select id="uncomparedFiles">
          <option value="inline" ${defaults.uncomparedFiles === "inline" || !defaults.uncomparedFiles ? "selected" : ""}>Include in report (inline)</option>
          <option value="separate" ${defaults.uncomparedFiles === "separate" ? "selected" : ""}>Save as separate file</option>
          <option value="none" ${defaults.uncomparedFiles === "none" ? "selected" : ""}>Omit entirely</option>
        </select>
      </div>
      <div class="field">
        <label for="sortBy">Sort by</label>
        <select id="sortBy">
          <option value="" ${!defaults.sortBy ? "selected" : ""}>— None (insertion order) —</option>
          <option value="filename" ${defaults.sortBy === "filename" ? "selected" : ""}>Filename (basename)</option>
          <option value="path" ${defaults.sortBy === "path" ? "selected" : ""}>Path (full)</option>
          <option value="similarity" ${defaults.sortBy === "similarity" ? "selected" : ""}>Name similarity</option>
          <option value="ratio" ${defaults.sortBy === "ratio" ? "selected" : ""}>Content similarity</option>
        </select>
      </div>
      <div class="field">
        <label for="sortOrder">Sort order</label>
        <select id="sortOrder">
          <option value="asc" ${defaults.sortOrder === "asc" || !defaults.sortOrder ? "selected" : ""}>Ascending</option>
          <option value="desc" ${defaults.sortOrder === "desc" ? "selected" : ""}>Descending</option>
        </select>
      </div>
    </section>

    <section>
      <h2>Dictionary & Presentation</h2>
      <div class="field" style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 4px;">
        <label>Exclusion Dictionary (.diffignore)</label>
        <button type="button" id="btnEditIgnore" class="btn-secondary" style="font-size: 11px; padding: 4px 10px;">Edit Dictionary</button>
      </div>
      <div style="font-size: 11px; color: var(--fg-dim); margin-bottom: 16px; margin-left: 2px;">
        Define patterns to exclude frameworks, virtual environments, or boilerplate code.
      </div>
      
      <div class="field dir-input-row" style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
        <label for="pdfFont" style="width: 140px; flex-shrink: 0;" title="Absolute path to a TrueType(.ttf) font file">PDF Font Path</label>
        <input type="text" id="pdfFont" class="path-input" style="flex-grow: 1; max-width: none;" placeholder="e.g. C:/Windows/Fonts/malgun.ttf" value="${escHtml(defaults.pdfFont || '')}">
      </div>
      <div class="field" style="display: flex; gap: 8px; align-items: center;">
        <label for="pdfLang" style="width: 140px; flex-shrink: 0;">PDF Fallback Lang</label>
        <select id="pdfLang" style="flex-grow: 1;">
          <option value="ko" ${defaults.pdfLang === 'ko' ? 'selected' : ''}>Korean (ko)</option>
          <option value="ja" ${defaults.pdfLang === 'ja' ? 'selected' : ''}>Japanese (ja)</option>
          <option value="zh-cn" ${defaults.pdfLang === 'zh-cn' ? 'selected' : ''}>Chinese (zh-cn)</option>
          <option value="en" ${defaults.pdfLang === 'en' ? 'selected' : ''}>English (en)</option>
        </select>
      </div>
    </section>

    <div class="actions" style="justify-content: space-between; align-items: center;">
      <div class="field checkbox" style="margin-bottom:0;">
        <input type="checkbox" id="saveHistory">
        <label for="saveHistory" style="cursor:pointer; color:var(--accent); font-weight:bold;">Save to Task History</label>
      </div>
      <button type="submit" class="btn-primary" style="width:200px">&#9654; Run Analysis</button>
    </div>
  </form>

  <script nonce="${nonce}">
    window.DiffiniteHistory = ${JSON.stringify(taskHistory).replace(/</g, "\\u003c")};
    ${OPTIONS_JS}
  </script>
</body>
</html>`;
}

const OPTIONS_CSS = `
  :root {
    --bg: #1e1e1e;
    --bg-surface: #252526;
    --fg: #cccccc;
    --fg-dim: #888;
    --accent: #0078d4;
    --border: #3c3c3c;
    --error: #f48771;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: "Segoe UI", "Noto Sans KR", sans-serif;
    font-size: 13px;
    color: var(--fg);
    background: var(--bg);
    padding: 24px;
    max-width: 600px;
    margin: 0 auto;
  }

  h1 {
    font-size: 18px;
    color: var(--accent);
    margin-bottom: 20px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--accent);
  }

  h2 {
    font-size: 13px;
    color: var(--accent);
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  section {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 12px;
  }

  .field {
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .field.checkbox {
    flex-direction: row;
    align-items: center;
    gap: 8px;
  }

  .field.checkbox label { cursor: pointer; }

  label {
    font-size: 12px;
    color: var(--fg-dim);
  }

  select, input[type="number"], input[type="text"] {
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    width: 100%;
    max-width: 200px;
  }

  .path-input {
    font-family: monospace;
    max-width: none !important; /* Overrides the 200px limit for path textboxes */
  }

  select:focus, input[type="number"]:focus, input[type="text"]:focus {
    outline: none;
    border-color: var(--accent);
  }

  input[type="checkbox"] {
    accent-color: var(--accent);
    width: 16px;
    height: 16px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 20px;
  }

  button {
    border: none;
    border-radius: 4px;
    padding: 8px 20px;
    font-size: 13px;
    cursor: pointer;
    font-weight: 600;
  }

  .btn-primary {
    background: var(--accent);
    color: #fff;
  }

  .btn-primary:hover { background: #005fa3; }

  .btn-secondary {
    background: var(--bg-surface);
    color: var(--fg);
    border: 1px solid var(--border);
  }

  .btn-secondary:hover { background: var(--border); }

  .hidden { display: none; }
  .deep-section.hidden { display: none; }

  .bates-details {
    margin-left: 24px;
    padding: 8px 0;
    border-left: 2px solid var(--accent);
    padding-left: 12px;
  }

  .bates-details.hidden { display: none; }
`;

const OPTIONS_JS = `
(function() {
  const vscode = acquireVsCodeApi();
  const form = document.getElementById('optForm');
  const modeSelect = document.getElementById('mode');
  const deepSection = document.getElementById('deepSection');
  const dirAEl = document.getElementById('dirA');
  const dirBEl = document.getElementById('dirB');
  const dirError = document.getElementById('dirError');
  const btnRun = form.querySelector('.btn-primary');

  // Handle Directory Browse clicks
  document.getElementById('btnBrowseA').addEventListener('click', () => {
    vscode.postMessage({ command: 'browse', target: 'dirA' });
  });
  document.getElementById('btnBrowseB').addEventListener('click', () => {
    vscode.postMessage({ command: 'browse', target: 'dirB' });
  });

  // Handle incoming path selections from VSCode Native Dialogs
  window.addEventListener('message', event => {
    const msg = event.data;
    if (msg.command === 'setPath') {
      const el = msg.target === 'dirA' ? dirAEl : dirBEl;
      if (el) {
        el.value = msg.path;
        formatPathAndScrollEnd(el);
      }
    } else if (msg.command === 'runComplete') {
      // Revert loading text when the extension host acknowledges completion (or TreeViewer is blocked)
      btnRun.innerHTML = '&#9654; Run Analysis';
    }
  });

  // UX Requirement: Normalize path quotes/newlines and ALWAYS show trailing basename
  function formatPathAndScrollEnd(el) {
    let val = el.value || "";
    // Remove wrapping quotes ("C:\\path" -> C:\\path) and strip newlines
    val = val.replace(/^["']|["']$/g, '').replace(/[\\r\\n]+/g, '');
    el.value = val;
    
    // Defer the scroll adjustment heavily so the browser paint catches up.
    // This forces the input's scroll position strictly to the rightmost trailing string.
    setTimeout(() => { el.scrollLeft = el.scrollWidth; }, 20);
  }

  // Format paths when losing focus or instantly after user pastes raw strings
  dirAEl.addEventListener('blur', () => formatPathAndScrollEnd(dirAEl));
  dirAEl.addEventListener('input', () => formatPathAndScrollEnd(dirAEl));
  dirBEl.addEventListener('blur', () => formatPathAndScrollEnd(dirBEl));
  dirBEl.addEventListener('input', () => formatPathAndScrollEnd(dirBEl));

  // Toggle deep section visibility based on mode
  function updateDeepVisibility() {
    if (modeSelect.value === 'simple') {
      deepSection.classList.add('hidden');
    } else {
      deepSection.classList.remove('hidden');
    }
  }
  modeSelect.addEventListener('change', updateDeepVisibility);
  updateDeepVisibility();

  // Toggle Bates details visibility
  const batesCheckbox = document.getElementById('batesNumber');
  const batesDetails = document.getElementById('batesDetails');
  function updateBatesVisibility() {
    if (batesCheckbox.checked) {
      batesDetails.classList.remove('hidden');
    } else {
      batesDetails.classList.add('hidden');
    }
  }
  batesCheckbox.addEventListener('change', updateBatesVisibility);
  updateBatesVisibility();

  // Preset selection auto-fills prefix/suffix/start
  const presetSelect = document.getElementById('batesPreset');
  presetSelect.addEventListener('change', () => {
    const opt = presetSelect.options[presetSelect.selectedIndex];
    if (opt.value) {
      document.getElementById('batesPrefix').value = opt.getAttribute('data-prefix') || '';
      document.getElementById('batesSuffix').value = opt.getAttribute('data-suffix') || '';
      document.getElementById('batesStart').value = opt.getAttribute('data-start') || '1';
    }
  });

  document.getElementById('btnEditIgnore').addEventListener('click', () => {
    vscode.postMessage({ command: 'editIgnore' });
  });

  const historySelect = document.getElementById('historySelect');
  const btnLoadHistory = document.getElementById('btnLoadHistory');
  const btnFlushHistory = document.getElementById('btnFlushHistory');

  if (btnLoadHistory) {
    btnLoadHistory.addEventListener('click', () => {
      const selectedId = historySelect.value;
      if (!selectedId) return;
      const history = window.DiffiniteHistory || [];
      const entry = history.find(h => h.id === selectedId);
      if (entry) {
        dirAEl.value = entry.dirA;
        dirBEl.value = entry.dirB;
        formatPathAndScrollEnd(dirAEl);
        formatPathAndScrollEnd(dirBEl);
        
        const o = entry.options;
        if(o) {
          modeSelect.value = o.mode || 'deep';
          document.getElementById('stripComments').checked = !!o.stripComments;
          document.getElementById('byWord').checked = !!o.byWord;
          document.getElementById('normalizeWhitespace').checked = !!o.normalizeWhitespace;
          document.getElementById('normalize').checked = !!o.normalize;
          document.getElementById('collapseIdentical').checked = !!o.collapseIdentical;
          document.getElementById('detectMoved').checked = !!o.detectMoved;
          document.getElementById('noAutojunk').checked = !!o.noAutojunk;
          document.getElementById('threshold').value = o.threshold || 60;
          document.getElementById('kGram').value = o.kGram || 5;
          document.getElementById('window').value = o.window || 4;
          document.getElementById('thresholdDeep').value = o.thresholdDeep || 5;
          document.getElementById('pageNumber').checked = !!o.pageNumber;
          document.getElementById('fileNumber').checked = !!o.fileNumber;
          document.getElementById('batesNumber').checked = !!o.batesNumber;
          document.getElementById('hash').checked = !!o.hash;
          document.getElementById('uncomparedFiles').value = o.uncomparedFiles || 'inline';
          document.getElementById('binaryHandling').value = o.binaryHandling || 'hash';
          document.getElementById('sortBy').value = o.sortBy || '';
          document.getElementById('sortOrder').value = o.sortOrder || 'asc';
          document.getElementById('batesPrefix').value = o.batesPrefix || '';
          document.getElementById('batesSuffix').value = o.batesSuffix || '';
          document.getElementById('batesStart').value = o.batesStart || 1;
          document.getElementById('workers').value = o.workers || 4;
          document.getElementById('noMerge').checked = !!o.noMerge;
          document.getElementById('preserveTree').checked = !!o.preserveTree;
          document.getElementById('pdfFont').value = o.pdfFont || '';
          document.getElementById('pdfLang').value = o.pdfLang || 'ko';
          presetSelect.value = o._batesPresetName || '';
          
          updateDeepVisibility();
          updateBatesVisibility();
        }
      }
    });

    btnFlushHistory.addEventListener('click', () => {
      if (confirm('Are you sure you want to delete all saved task history?')) {
        vscode.postMessage({ command: 'flushHistory' });
      }
    });
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    dirError.style.display = 'none';

    const dirA = dirAEl.value.trim();
    const dirB = dirBEl.value.trim();

    if (!dirA || !dirB) {
      dirError.style.display = 'block';
      return;
    }

    const options = {
      mode: modeSelect.value,
      stripComments: document.getElementById('stripComments').checked,
      byWord: document.getElementById('byWord').checked,
      normalizeWhitespace: document.getElementById('normalizeWhitespace').checked,
      normalize: document.getElementById('normalize').checked,
      collapseIdentical: document.getElementById('collapseIdentical').checked,
      detectMoved: document.getElementById('detectMoved').checked,
      noAutojunk: document.getElementById('noAutojunk').checked,
      threshold: Number(document.getElementById('threshold').value),
      kGram: Number(document.getElementById('kGram').value),
      window: Number(document.getElementById('window').value),
      thresholdDeep: Number(document.getElementById('thresholdDeep').value),
      pageNumber: document.getElementById('pageNumber').checked,
      fileNumber: document.getElementById('fileNumber').checked,
      batesNumber: document.getElementById('batesNumber').checked,
      hash: document.getElementById('hash').checked,
      uncomparedFiles: document.getElementById('uncomparedFiles').value,
      binaryHandling: document.getElementById('binaryHandling').value,
      encoding: 'auto',
      sortBy: document.getElementById('sortBy').value,
      sortOrder: document.getElementById('sortOrder').value,
      batesPrefix: document.getElementById('batesPrefix').value,
      batesSuffix: document.getElementById('batesSuffix').value,
      batesStart: Number(document.getElementById('batesStart').value) || 1,
      _batesPresetName: presetSelect.value,
      workers: Number(document.getElementById('workers').value),
      noMerge: document.getElementById('noMerge').checked,
      preserveTree: document.getElementById('preserveTree').checked,
      pdfFont: document.getElementById('pdfFont').value.trim(),
      pdfLang: document.getElementById('pdfLang').value,
    };
    
    // Set UI to running state (does not disable button to allow parallel queueing test flows if desired)
    btnRun.innerHTML = '<span style="opacity:0.7">&#10227;</span> Running...';
    
    const saveHistory = document.getElementById('saveHistory').checked;

    // Broadcast run event back to main extension process
    vscode.postMessage({ command: 'run', dirA, dirB, options, saveHistory });
  });

})();
`;
