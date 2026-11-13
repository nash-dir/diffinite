/**
 * Options Panel — collects target directories & analysis options via a Webview form.
 *
 * Renders CLI options as checkboxes, dropdowns, and number inputs.
 * Acts as the "Home Base" UI that triggers the pipeline logic.
 */
import * as vscode from "vscode";
import { DiffiniteOptions, defaultOptions } from "./runner";
import { batesLabelError, migratePersistedOptions, validateRunOptions } from "./analysisModel";
import { readIgnoreSnapshot } from "./inputFreeze";
import { getDefaultMode, getBatesPresets, BatesPreset, getPdfFont, getPdfLang } from "./config";
import { escHtml, getNonce, THEME_CSS } from "./webviewUtils";

export interface TaskHistoryEntry {
  id: string;
  label: string;
  dirA: string;
  dirB: string;
  options: DiffiniteOptions;
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
    "Diffinite: Analysis",
    vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  const lastDirs = context.globalState.get<{ dirA: string; dirB: string }>("diffinite.lastDirs") || { dirA: "", dirB: "" };
  const lastRunOptions = context.globalState.get<Partial<DiffiniteOptions>>("diffinite.lastRunOptions");

  const config = vscode.workspace.getConfiguration("diffinite");
  const migration = lastRunOptions
    ? migratePersistedOptions(lastRunOptions)
    : { options: defaultOptions(), warnings: [] as string[] };
  const defaults = migration.options;
  defaults.mode = lastRunOptions?.mode || getDefaultMode() as "simple" | "deep";
  defaults.workers = lastRunOptions?.workers || config.get<number>("workers", 4);
  defaults.noMerge = lastRunOptions?.noMerge ?? config.get<boolean>("noMerge", false);
  defaults.preserveTree = lastRunOptions?.preserveTree ?? config.get<boolean>("preserveTree", true);
  defaults.pdfFont = lastRunOptions?.pdfFont || getPdfFont();
  defaults.pdfLang = lastRunOptions?.pdfLang || getPdfLang();
  
  const presets = getBatesPresets();
  const taskHistory = context.globalState.get<TaskHistoryEntry[]>("diffinite.taskHistory") || [];

  if (migration.warnings.length) {
    void vscode.window.showWarningMessage(`Diffinite: ${migration.warnings.join(" ")}`);
  }
  panel.webview.html = buildOptionsHtml(
    defaults, presets, lastDirs, taskHistory, migration.warnings, describeIgnoreStatus(),
  );

  // A closed panel's webview getter throws; never let that replace a real
  // run error or skip the rest of a handler.
  let disposed = false;
  panel.onDidDispose(() => { disposed = true; }, undefined, context.subscriptions);
  const post = (message: unknown): void => {
    if (disposed) { return; }
    try { void panel.webview.postMessage(message); } catch { /* disposed meanwhile */ }
  };
  // ~/.diffignore applies to every run: refresh its status whenever the panel
  // is shown again (the user may have edited the file in the meantime).
  panel.onDidChangeViewState((event) => {
    if (event.webviewPanel.visible) {
      post({ command: "ignoreStatus", text: describeIgnoreStatus() });
    }
  }, undefined, context.subscriptions);

  let runPending = false;
  panel.webview.onDidReceiveMessage(
    async (msg: { command: string; target?: string; options?: DiffiniteOptions; dirA?: string; dirB?: string; saveHistory?: boolean }) => {
      if (
        msg.command === "run" &&
        typeof msg.options === "object" && msg.options !== null &&
        typeof msg.dirA === "string" && msg.dirA &&
        typeof msg.dirB === "string" && msg.dirB
      ) {
        if (runPending) {
          void vscode.window.showWarningMessage("Diffinite: An analysis is already starting from this panel.");
          return;
        }
        runPending = true;

        try {
          // Number("") is 0, a valid but extreme threshold: never run (or save)
          // a value the user did not enter. Same ranges as cli.py.
          const invalid = validateRunOptions(msg.options);
          if (invalid) {
            void vscode.window.showErrorMessage(`Diffinite: ${invalid}`);
            return;
          }
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
          // It stays open so users can tweak paths/options and run again safely.
          await onRun(msg.dirA, msg.dirB, msg.options);
        } finally {
          runPending = false;
          post({ command: 'runComplete' });
          post({ command: "ignoreStatus", text: describeIgnoreStatus() });
        }
      } else if (msg.command === "browse" && (msg.target === "dirA" || msg.target === "dirB")) {
        // Open native directory selection dialog
        const isDirA = msg.target === "dirA";
        const uri = await vscode.window.showOpenDialog({
          canSelectFolders: true,
          canSelectFiles: false,
          canSelectMany: false,
          openLabel: `Select Directory ${isDirA ? 'A' : 'B'}`,
          title: `Diffinite: Select Directory ${isDirA ? 'A' : 'B'}`,
        });
        if (uri && uri.length > 0) {
          // Send selected path back to update the webview input
          post({ command: "setPath", target: msg.target, path: uri[0].fsPath });
        }
      } else if (msg.command === "cancel") {
        panel.dispose();
      } else if (msg.command === "editIgnore") {
        vscode.commands.executeCommand("diffinite.editIgnoreList");
      } else if (msg.command === "flushHistory") {
        await context.globalState.update("diffinite.taskHistory", []);
        vscode.window.showInformationMessage("Diffinite: Task history cleared.");
        panel.dispose();
        vscode.commands.executeCommand("diffinite.compare");
      }
    },
    undefined,
    context.subscriptions
  );
}

/**
 * One-line disclosure of the exclusion list every run will apply. The file is
 * passed to the analyzer whenever it exists, so the user must see that it does.
 */
export function describeIgnoreStatus(): string {
  try {
    const snapshot = readIgnoreSnapshot();
    if (!snapshot) {
      return "No exclusion list: ~/.diffignore does not exist.";
    }
    return snapshot.ruleCount === 0
      ? `~/.diffignore exists but has no active rules (${snapshot.sourcePath}).`
      : `Exclusion list in use: ~/.diffignore has ${snapshot.ruleCount === 1 ? "1 rule" : `${snapshot.ruleCount} rules`} (${snapshot.sourcePath}). ` +
        "Matching files are excluded from comparison. The report can list them under Excluded Inputs.";
  } catch (err) {
    return `~/.diffignore could not be read (${err}). The analysis will stop until it can be read or is removed.`;
  }
}

function buildOptionsHtml(
  defaults: DiffiniteOptions,
  presets: BatesPreset[],
  lastDirs: { dirA: string; dirB: string },
  taskHistory: TaskHistoryEntry[],
  migrationWarnings: string[],
  ignoreStatus: string,
): string {
  const nonce = getNonce();
  const presetOptions = presets.map((p) => {
    const label = `${escHtml(p.name)} (${escHtml(p.prefix)}nnnn${escHtml(p.suffix || "")})`;
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
  <style>${THEME_CSS}${OPTIONS_CSS}</style>
</head>
<body>
  <header class="page-head">
    <h1>Diffinite: Code Comparison</h1>
  </header>

  <form id="optForm">
    <section aria-labelledby="h-dirs">
      <h2 id="h-dirs">Target Directories</h2>
      <div class="field">
        <label for="dirA">Directory A</label>
        <div class="input-row">
          <input type="text" id="dirA" class="path-input" placeholder="e.g. C:/source/project_v1" value="${escHtml(lastDirs.dirA || '')}">
          <button type="button" id="btnBrowseA" class="btn-secondary">Browse</button>
        </div>
      </div>
      <div class="field">
        <label for="dirB">Directory B</label>
        <div class="input-row">
          <input type="text" id="dirB" class="path-input" placeholder="e.g. C:/source/project_v2" value="${escHtml(lastDirs.dirB || '')}">
          <button type="button" id="btnBrowseB" class="btn-secondary">Browse</button>
        </div>
      </div>
      <div id="dirError" class="field-error" style="display:none;">Enter both directories.</div>
    </section>

    <section aria-labelledby="h-exec">
      <h2 id="h-exec">Execution</h2>
      <div class="field">
        <label for="mode">Mode</label>
        <select id="mode" name="mode">
          <option value="deep" ${defaults.mode === "deep" ? "selected" : ""}>Deep (1:1 and cross-file Winnowing)</option>
          <option value="simple" ${defaults.mode === "simple" ? "selected" : ""}>Simple (1:1 only)</option>
        </select>
      </div>
      <div class="field">
        <label for="workers">Worker processes</label>
        <input type="number" id="workers" class="input-num" value="${defaults.workers}" min="1" max="32" step="1">
      </div>
    </section>

    <section aria-labelledby="h-cmp">
      <h2 id="h-cmp">Comparison</h2>
      <div class="field checkbox">
        <input type="checkbox" id="stripComments" ${defaults.stripComments ? "checked" : ""}>
        <label for="stripComments">Strip comments before comparison</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="byWord" ${defaults.byWord ? "checked" : ""}>
        <label for="byWord">Compare by word (instead of by line)</label>
      </div>
      <div class="field checkbox sub">
        <input type="checkbox" id="normalizeWhitespace" ${defaults.normalizeWhitespace ? "checked" : ""}>
        <label for="normalizeWhitespace">Normalize whitespace (tabs to spaces, collapse repeated spaces)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="collapseIdentical" ${defaults.collapseIdentical ? "checked" : ""}>
        <label for="collapseIdentical">Collapse identical blocks (3 context lines)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="detectMoved" ${defaults.detectMoved ? "checked" : ""}>
        <label for="detectMoved">Detect moved code blocks</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="noAutojunk" ${defaults.noAutojunk ? "checked" : ""}>
        <label for="noAutojunk">Disable autojunk (slower on large files)</label>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="threshold">File name matching threshold (0 to 100)</label>
          <input type="number" id="threshold" class="input-num" value="${defaults.threshold}" min="0" max="100" step="1">
        </div>
        <div class="field">
          <label for="binaryHandling">Binary files</label>
          <select id="binaryHandling">
            <option value="exclude" ${defaults.binaryHandling === "exclude" ? "selected" : ""}>Exclude</option>
            <option value="hash" ${defaults.binaryHandling === "hash" ? "selected" : ""}>Hash compare only</option>
            <option value="error" ${defaults.binaryHandling === "error" ? "selected" : ""}>Report as error</option>
          </select>
        </div>
      </div>
    </section>

    <section class="deep-section" id="deepSection" aria-labelledby="h-deep">
      <h2 id="h-deep">Deep Compare</h2>
      <div class="field checkbox">
        <input type="checkbox" id="normalize" ${defaults.normalize ? "checked" : ""}>
        <label for="normalize">Normalize identifiers and literals for fingerprinting</label>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="kGram">K-gram size</label>
          <input type="number" id="kGram" class="input-num" value="${defaults.kGram}" min="2" max="20" step="1">
        </div>
        <div class="field">
          <label for="window">Window size</label>
          <input type="number" id="window" class="input-num" value="${defaults.window}" min="1" max="20" step="1">
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="thresholdMode">Deep threshold</label>
          <select id="thresholdMode">
            <option value="auto" ${defaults.thresholdMode === "auto" ? "selected" : ""}>Default for the chosen comparison</option>
            <option value="manual" ${defaults.thresholdMode === "manual" ? "selected" : ""}>Manual value</option>
          </select>
        </div>
        <div class="field">
          <label for="thresholdDeep">Manual Jaccard threshold (0 to 100)</label>
          <input type="number" id="thresholdDeep" class="input-num" value="${defaults.thresholdDeep}" min="0" max="100" step="1" ${defaults.thresholdMode === "auto" ? "disabled" : ""}>
        </div>
      </div>
      <div id="thresholdWarning" class="hint">${escHtml(migrationWarnings.join(" "))}</div>
    </section>

    <section aria-labelledby="h-report">
      <h2 id="h-report">Report Options</h2>
      <div class="field checkbox">
        <input type="checkbox" id="noMerge" ${defaults.noMerge ? "checked" : ""}>
        <label for="noMerge">Save one report per file pair (No Merge)</label>
      </div>
      <div class="field checkbox sub">
        <input type="checkbox" id="preserveTree" ${defaults.preserveTree ? "checked" : ""} ${!defaults.noMerge ? "disabled" : ""}>
        <label for="preserveTree">Keep the original folder structure (clear for a flat folder with index.html)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="pageNumber" ${defaults.pageNumber ? "checked" : ""}>
        <label for="pageNumber">Page numbers (Page n of N)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="fileNumber" ${defaults.fileNumber ? "checked" : ""}>
        <label for="fileNumber">File numbers (File n of N)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="batesNumber" ${defaults.batesNumber ? "checked" : ""}>
        <label for="batesNumber">Stamp Bates numbers</label>
      </div>
      <div class="bates-details" id="batesDetails">
        <div class="field">
          <label for="batesPreset">Preset</label>
          <select id="batesPreset">
            <option value="">Manual entry</option>
            ${presetOptions}
          </select>
        </div>
        <div class="field-row">
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
            <input type="number" id="batesStart" class="input-num" value="${defaults.batesStart}" min="1" step="1">
          </div>
        </div>
        <div id="batesError" role="alert" class="field-error" style="display:none;"></div>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="hash" ${defaults.hash ? "checked" : ""}>
        <label for="hash">Include the SHA-256 table of input files</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="allowPartial" ${defaults.allowPartial ? "checked" : ""}>
        <label for="allowPartial">Allow a report marked incomplete after a worker or file failure</label>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="uncomparedFiles">Uncompared files list</label>
          <select id="uncomparedFiles">
            <option value="inline" ${defaults.uncomparedFiles === "inline" || !defaults.uncomparedFiles ? "selected" : ""}>Include in report (inline)</option>
            <option value="separate" ${defaults.uncomparedFiles === "separate" ? "selected" : ""}>Save as separate file</option>
            <option value="none" ${defaults.uncomparedFiles === "none" ? "selected" : ""}>Omit</option>
          </select>
        </div>
        <div class="field">
          <label for="sortBy">Sort by</label>
          <select id="sortBy">
            <option value="" ${!defaults.sortBy ? "selected" : ""}>None (analysis order)</option>
            <option value="filename" ${defaults.sortBy === "filename" ? "selected" : ""}>Filename (basename)</option>
            <option value="path" ${defaults.sortBy === "path" ? "selected" : ""}>Path (full)</option>
            <option value="similarity" ${defaults.sortBy === "similarity" ? "selected" : ""}>Name similarity</option>
            <option value="ratio" ${defaults.sortBy === "ratio" ? "selected" : ""}>Line or word match</option>
          </select>
        </div>
        <div class="field">
          <label for="sortOrder">Sort order</label>
          <select id="sortOrder">
            <option value="asc" ${defaults.sortOrder === "asc" || !defaults.sortOrder ? "selected" : ""}>Ascending</option>
            <option value="desc" ${defaults.sortOrder === "desc" ? "selected" : ""}>Descending</option>
          </select>
        </div>
      </div>
    </section>

    <section aria-labelledby="h-dict">
      <h2 id="h-dict">Excluded Inputs and PDF Fonts</h2>
      <div class="field">
        <span class="field-label" id="lbl-ignore">Exclusion dictionary (.diffignore)</span>
        <div class="input-row">
          <span class="hint" id="ignoreHelp">Patterns for files to exclude, such as frameworks, virtual environments or generated code.</span>
          <button type="button" id="btnEditIgnore" class="btn-secondary" aria-describedby="lbl-ignore ignoreHelp">Edit Dictionary</button>
        </div>
        <div id="ignoreStatus" role="status" class="notice status-note">${escHtml(ignoreStatus)}</div>
      </div>
      <div class="field">
        <label for="sensitiveFiles">Sensitive files (.env, private keys, credential files)</label>
        <select id="sensitiveFiles" aria-describedby="sensitiveHelp">
          <option value="exclude" ${defaults.sensitiveFiles === "exclude" || !defaults.sensitiveFiles ? "selected" : ""}>Exclude and list in the report</option>
          <option value="include" ${defaults.sensitiveFiles === "include" ? "selected" : ""}>Include (compare like any other file)</option>
          <option value="error" ${defaults.sensitiveFiles === "error" ? "selected" : ""}>Stop the analysis when found</option>
        </select>
        <span class="hint" id="sensitiveHelp">Included files are copied into the reports in full. Choose Include only when these files are in dispute.</span>
      </div>
      <div class="field">
        <label for="includePatterns">Include only files matching</label>
        <input type="text" id="includePatterns" class="path-input" aria-describedby="includeHelp" placeholder="e.g. *.java, src/**" value="${escHtml(defaults.includePatterns || '')}">
        <span class="hint" id="includeHelp">Comma-separated patterns, same syntax as .diffignore. Leave empty to apply no include filter. The report counts excluded files and lists them according to the Uncompared files list setting.</span>
      </div>
      <div class="field">
        <label for="pdfFont" title="Absolute path to a TrueType (.ttf) font file">PDF font path</label>
        <input type="text" id="pdfFont" class="path-input" placeholder="e.g. C:/Windows/Fonts/malgun.ttf" value="${escHtml(defaults.pdfFont || '')}">
      </div>
      <div class="field">
        <label for="pdfLang">PDF fallback language</label>
        <select id="pdfLang">
          <option value="ko" ${defaults.pdfLang === 'ko' ? 'selected' : ''}>Korean (ko)</option>
          <option value="ja" ${defaults.pdfLang === 'ja' ? 'selected' : ''}>Japanese (ja)</option>
          <option value="zh-cn" ${defaults.pdfLang === 'zh-cn' ? 'selected' : ''}>Chinese (zh-cn)</option>
          <option value="en" ${defaults.pdfLang === 'en' ? 'selected' : ''}>English (en)</option>
        </select>
      </div>
    </section>

    <section aria-labelledby="h-hist">
      <h2 id="h-hist">Task History</h2>
      <div class="field">
        <label for="historySelect" class="sr-only">Previous task</label>
        <div class="input-row">
          <select id="historySelect" class="grow">
            <option value="">Select a previous task</option>
            ${historyOptions}
          </select>
          <button type="button" id="btnLoadHistory" class="btn-secondary" ${taskHistory.length===0?'disabled':''}>Load Task</button>
          <button type="button" id="btnFlushHistory" class="btn-secondary" ${taskHistory.length===0?'disabled':''}>Clear All</button>
        </div>
      </div>
    </section>

    <div class="actions">
      <div class="field checkbox">
        <input type="checkbox" id="saveHistory">
        <label for="saveHistory">Save to task history</label>
      </div>
      <button type="submit" class="btn-primary btn-run">Run Analysis</button>
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
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { overflow-x: hidden; }

  /* Settings-editor layout: one readable column, sections divided by rules. */
  body { padding: var(--sp-5) var(--sp-5) 0; max-width: 760px; margin: 0 auto; }
  @media (max-width: 600px) { body { padding: var(--sp-4) var(--sp-4) 0; } }

  .page-head { margin-bottom: var(--sp-2); }
  h1 { font-size: var(--fs-h1); font-weight: 600; line-height: 1.3; }

  section { padding: var(--sp-4) 0 var(--sp-2); border-top: 1px solid var(--border); }
  .page-head + form section:first-child { border-top: 0; padding-top: var(--sp-2); }
  h2 { font-size: var(--fs-h2); font-weight: 600; margin-bottom: var(--sp-3); }

  .field { margin-bottom: var(--sp-3); display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .field.checkbox { flex-direction: row; align-items: flex-start; gap: var(--sp-2); margin-bottom: var(--sp-2); }
  .field.checkbox input { margin-top: 2px; flex: none; }
  .field.checkbox label { cursor: pointer; color: var(--fg); font-weight: 400; font-size: var(--fs-base); }
  .field.checkbox input:disabled + label { color: var(--fg-dim); cursor: default; }
  .field.sub { margin-left: var(--sp-5); }

  /* Short related controls share a row and wrap on narrow panels. */
  .field-row { display: flex; flex-wrap: wrap; gap: 0 var(--sp-5); }
  .field-row > .field { flex: 0 1 auto; }

  label, .field-label { font-size: var(--fs-sm); color: var(--fg); font-weight: 600; }

  select, input[type="number"], input[type="text"] {
    height: var(--control-h); padding: 2px 6px; width: 100%; max-width: 320px; min-width: 0;
  }
  select { padding: 0 4px; }
  input.input-num { max-width: 96px; font-variant-numeric: tabular-nums; }
  .path-input { font-family: var(--code-font); max-width: none; }
  select:focus, input[type="number"]:focus, input[type="text"]:focus { border-color: var(--focus); }

  .input-row { display: flex; gap: var(--sp-2); align-items: center; min-width: 0; }
  .input-row > input, .input-row > .grow { flex: 1 1 auto; max-width: none; }
  .input-row > button { flex: none; }
  .input-row > .hint { flex: 1 1 auto; margin: 0; }

  .hint { color: var(--fg-dim); font-size: var(--fs-sm); margin: 0 0 var(--sp-3); max-width: 70ch; }
  .hint:empty { display: none; }
  .field-error { color: var(--error); font-size: var(--fs-sm); margin: var(--sp-1) 0 var(--sp-2); }
  .status-note { margin: var(--sp-1) 0 0; font-size: var(--fs-sm); overflow-wrap: anywhere; }

  .hidden { display: none; }
  .deep-section.hidden { display: none; }

  .bates-details { margin: 0 0 var(--sp-3) var(--sp-5); padding-left: var(--sp-3); border-left: 1px solid var(--border); }
  .bates-details.hidden { display: none; }

  /* Primary action bar stays in reach at the bottom of the panel. */
  .actions {
    position: sticky; bottom: 0; z-index: 1;
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--sp-2) var(--sp-4);
    margin: var(--sp-2) calc(-1 * var(--sp-5)) 0; padding: var(--sp-3) var(--sp-5);
    background: var(--bg); border-top: 1px solid var(--border);
  }
  @media (max-width: 600px) { .actions { margin: var(--sp-2) calc(-1 * var(--sp-4)) 0; padding: var(--sp-3) var(--sp-4); } }
  .actions .field.checkbox { margin: 0; }
  .btn-run { min-width: 140px; }
`;

const OPTIONS_JS = `
  // Same rule as analysisModel.batesLabelError (and the CLI's bates_font_for).
  const batesLabelError = ${batesLabelError.toString()};
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
    } else if (msg.command === 'ignoreStatus' && typeof msg.text === 'string') {
      document.getElementById('ignoreStatus').textContent = msg.text;
    } else if (msg.command === 'runComplete') {
      // Revert loading text when the extension host acknowledges completion (or TreeViewer is blocked)
      btnRun.disabled = false;
      btnRun.textContent = 'Run Analysis';
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

  // "Preserve folder tree" only applies to No Merge output.
  const noMergeCb = document.getElementById('noMerge');
  const preserveTreeCb = document.getElementById('preserveTree');
  function updatePreserveTree() {
    preserveTreeCb.disabled = !noMergeCb.checked;
  }
  noMergeCb.addEventListener('change', updatePreserveTree);
  updatePreserveTree();

  const normalizeCheckbox = document.getElementById('normalize');
  const thresholdModeSelect = document.getElementById('thresholdMode');
  const thresholdDeepInput = document.getElementById('thresholdDeep');
  const thresholdWarning = document.getElementById('thresholdWarning');
  let legacyThresholdWarning = thresholdWarning.textContent || '';
  function updateThresholdMode() {
    const manual = thresholdModeSelect.value === 'manual';
    thresholdDeepInput.disabled = !manual;
    if (legacyThresholdWarning) {
      thresholdWarning.textContent = legacyThresholdWarning;
    } else if (manual && normalizeCheckbox.checked) {
      thresholdWarning.textContent = 'Manual threshold with normalization: the report states whether the measured false-positive rate applies at this value.';
    } else if (manual) {
      thresholdWarning.textContent = 'Manual threshold: no false-positive rate has been measured for this value.';
    } else {
      thresholdWarning.textContent = 'The analyzer applies its default threshold for the chosen comparison (normalized or not) and records it in the report.';
    }
  }
  thresholdModeSelect.addEventListener('change', () => { legacyThresholdWarning = ''; updateThresholdMode(); });
  normalizeCheckbox.addEventListener('change', () => { legacyThresholdWarning = ''; updateThresholdMode(); });
  updateThresholdMode();

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

  // Bates prefix/suffix: the stamp fonts draw only Windows-1252 or Hangul, and
  // the CLI refuses anything else, so say so next to the fields.
  const batesError = document.getElementById('batesError');
  function checkBatesLabel() {
    const message = batesLabelError(
      document.getElementById('batesPrefix').value + document.getElementById('batesSuffix').value);
    batesError.textContent = message || '';
    batesError.style.display = message ? 'block' : 'none';
    return message;
  }
  document.getElementById('batesPrefix').addEventListener('input', checkBatesLabel);
  document.getElementById('batesSuffix').addEventListener('input', checkBatesLabel);
  checkBatesLabel();

  // Preset selection auto-fills prefix/suffix/start
  const presetSelect = document.getElementById('batesPreset');
  presetSelect.addEventListener('change', () => {
    const opt = presetSelect.options[presetSelect.selectedIndex];
    if (opt.value) {
      document.getElementById('batesPrefix').value = opt.getAttribute('data-prefix') || '';
      document.getElementById('batesSuffix').value = opt.getAttribute('data-suffix') || '';
      checkBatesLabel();
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
          document.getElementById('threshold').value = typeof o.threshold === 'number' ? o.threshold : 60;
          document.getElementById('kGram').value = o.kGram || 5;
          document.getElementById('window').value = o.window || 4;
          document.getElementById('thresholdDeep').value = typeof o.thresholdDeep === 'number' ? o.thresholdDeep : 5;
          if (o.thresholdMode === 'auto' || o.thresholdMode === 'manual') {
            thresholdModeSelect.value = o.thresholdMode;
            legacyThresholdWarning = '';
          } else {
            thresholdModeSelect.value = 'manual';
            legacyThresholdWarning = 'A saved threshold from an earlier version was kept as a manual value. Choose the default to use the analyzer default.';
          }
          document.getElementById('pageNumber').checked = !!o.pageNumber;
          document.getElementById('fileNumber').checked = !!o.fileNumber;
          document.getElementById('batesNumber').checked = !!o.batesNumber;
          document.getElementById('hash').checked = !!o.hash;
          document.getElementById('allowPartial').checked = !!o.allowPartial;
          document.getElementById('uncomparedFiles').value = o.uncomparedFiles || 'inline';
          document.getElementById('binaryHandling').value = o.binaryHandling || 'hash';
          document.getElementById('sensitiveFiles').value = o.sensitiveFiles || 'exclude';
          document.getElementById('includePatterns').value = o.includePatterns || '';
          document.getElementById('sortBy').value = o.sortBy || '';
          document.getElementById('sortOrder').value = o.sortOrder || 'asc';
          document.getElementById('batesPrefix').value = o.batesPrefix || '';
          document.getElementById('batesSuffix').value = o.batesSuffix || '';
          checkBatesLabel();
          document.getElementById('batesStart').value = o.batesStart || 1;
          document.getElementById('workers').value = o.workers || 4;
          document.getElementById('noMerge').checked = !!o.noMerge;
          document.getElementById('preserveTree').checked = !!o.preserveTree;
          document.getElementById('pdfFont').value = o.pdfFont || '';
          document.getElementById('pdfLang').value = o.pdfLang || 'ko';
          presetSelect.value = o._batesPresetName || '';
          
          updateDeepVisibility();
          updateThresholdMode();
          updateBatesVisibility();
          updatePreserveTree();
        }
      }
    });

    btnFlushHistory.addEventListener('click', () => {
      if (confirm('Delete all saved task history?')) {
        vscode.postMessage({ command: 'flushHistory' });
      }
    });
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (btnRun.disabled) return;
    dirError.style.display = 'none';
    dirError.textContent = 'Enter both directories.';

    const dirA = dirAEl.value.trim();
    const dirB = dirBEl.value.trim();

    if (!dirA || !dirB) {
      dirError.style.display = 'block';
      return;
    }

    // An empty number field reads as 0 through Number(''). Refuse instead of
    // running with a value the user never entered.
    const numberFields = ['threshold', 'kGram', 'window', 'workers', 'batesStart'];
    if (document.getElementById('thresholdMode').value === 'manual') numberFields.push('thresholdDeep');
    for (const id of numberFields) {
      const el = document.getElementById(id);
      if (!Number.isFinite(el.valueAsNumber) || !el.checkValidity()) {
        dirError.textContent = 'Enter a valid number for "' + (el.labels && el.labels[0] ? el.labels[0].textContent : id) + '".';
        dirError.style.display = 'block';
        el.focus();
        return;
      }
    }

    // Only a label that will be stamped can block the run; Bates numbering stays as chosen.
    const batesMessage = batesCheckbox.checked ? checkBatesLabel() : '';
    if (batesMessage) {
      updateBatesVisibility();
      dirError.textContent = batesMessage;
      dirError.style.display = 'block';
      document.getElementById('batesPrefix').focus();
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
      threshold: document.getElementById('threshold').valueAsNumber,
      kGram: document.getElementById('kGram').valueAsNumber,
      window: document.getElementById('window').valueAsNumber,
      thresholdMode: document.getElementById('thresholdMode').value,
      // Not sent to Python in Auto mode; an empty field is simply not saved.
      thresholdDeep: Number.isFinite(document.getElementById('thresholdDeep').valueAsNumber)
        ? document.getElementById('thresholdDeep').valueAsNumber : undefined,
      pageNumber: document.getElementById('pageNumber').checked,
      fileNumber: document.getElementById('fileNumber').checked,
      batesNumber: document.getElementById('batesNumber').checked,
      hash: document.getElementById('hash').checked,
      allowPartial: document.getElementById('allowPartial').checked,
      uncomparedFiles: document.getElementById('uncomparedFiles').value,
      binaryHandling: document.getElementById('binaryHandling').value,
      sensitiveFiles: document.getElementById('sensitiveFiles').value,
      includePatterns: document.getElementById('includePatterns').value,
      encoding: 'auto',
      sortBy: document.getElementById('sortBy').value,
      sortOrder: document.getElementById('sortOrder').value,
      batesPrefix: document.getElementById('batesPrefix').value,
      batesSuffix: document.getElementById('batesSuffix').value,
      batesStart: document.getElementById('batesStart').valueAsNumber,
      _batesPresetName: presetSelect.value,
      workers: document.getElementById('workers').valueAsNumber,
      noMerge: document.getElementById('noMerge').checked,
      preserveTree: document.getElementById('preserveTree').checked,
      pdfFont: document.getElementById('pdfFont').value.trim(),
      pdfLang: document.getElementById('pdfLang').value,
    };
    
    // Prevent duplicate messages while the extension host owns this run.
    btnRun.disabled = true;
    btnRun.textContent = 'Running';
    
    const saveHistory = document.getElementById('saveHistory').checked;

    // Broadcast run event back to main extension process
    vscode.postMessage({ command: 'run', dirA, dirB, options, saveHistory });
  });

})();
`;
