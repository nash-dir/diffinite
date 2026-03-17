/**
 * Options Panel — collects analysis options via a Webview form.
 *
 * Renders CLI options as checkboxes, dropdowns, and number inputs.
 * Returns the collected options via a Promise.
 */
import * as vscode from "vscode";
import { DiffiniteOptions, defaultOptions } from "./runner";
import { getDefaultMode } from "./config";

/**
 * Show an options panel and return the user's choices.
 * Resolves with the options, or undefined if cancelled.
 */
export function collectOptions(
  context: vscode.ExtensionContext
): Promise<DiffiniteOptions | undefined> {
  return new Promise((resolve) => {
    const panel = vscode.window.createWebviewPanel(
      "diffiniteOptions",
      "Diffinite — Options",
      vscode.ViewColumn.One,
      { enableScripts: true }
    );

    const defaults = defaultOptions();
    defaults.mode = getDefaultMode() as "simple" | "deep";

    panel.webview.html = buildOptionsHtml(defaults);

    panel.webview.onDidReceiveMessage(
      (msg: { command: string; options?: DiffiniteOptions }) => {
        if (msg.command === "run" && msg.options) {
          resolve(msg.options);  // resolve BEFORE dispose
          panel.dispose();
        } else if (msg.command === "cancel") {
          panel.dispose();
          resolve(undefined);
        }
      },
      undefined,
      context.subscriptions
    );

    panel.onDidDispose(() => resolve(undefined));
  });
}

function buildOptionsHtml(defaults: DiffiniteOptions): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Diffinite Options</title>
  <style>${OPTIONS_CSS}</style>
</head>
<body>
  <h1>Diffinite — Analysis Options</h1>

  <form id="optForm">
    <section>
      <h2>Execution</h2>
      <div class="field">
        <label for="mode">Mode</label>
        <select id="mode" name="mode">
          <option value="deep" ${defaults.mode === "deep" ? "selected" : ""}>Deep (1:1 + N:M Winnowing)</option>
          <option value="simple" ${defaults.mode === "simple" ? "selected" : ""}>Simple (1:1 only)</option>
        </select>
      </div>
    </section>

    <section>
      <h2>Comparison</h2>
      <div class="field checkbox">
        <input type="checkbox" id="noComments" ${defaults.noComments ? "checked" : ""}>
        <label for="noComments">Strip comments before comparison</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="byWord" ${defaults.byWord ? "checked" : ""}>
        <label for="byWord">Compare by word (instead of by line)</label>
      </div>
      <div class="field checkbox">
        <input type="checkbox" id="collapseIdentical" ${defaults.collapseIdentical ? "checked" : ""}>
        <label for="collapseIdentical">Collapse identical blocks (3 context lines)</label>
      </div>
      <div class="field">
        <label for="threshold">File name matching threshold (0–100)</label>
        <input type="number" id="threshold" value="${defaults.threshold}" min="0" max="100" step="1">
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
        <label for="thresholdDeep">Min Jaccard threshold</label>
        <input type="number" id="thresholdDeep" value="${defaults.thresholdDeep}" min="0" max="1" step="0.01">
      </div>
    </section>

    <section>
      <h2>Report Options</h2>
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
      <div class="field checkbox">
        <input type="checkbox" id="hash" ${defaults.hash ? "checked" : ""}>
        <label for="hash">Embed SHA-256 file hashes in report</label>
      </div>
    </section>

    <section>
      <h2>Forensic</h2>
      <div class="field checkbox">
        <input type="checkbox" id="noAutojunk" ${defaults.noAutojunk ? "checked" : ""}>
        <label for="noAutojunk">Disable autojunk (precise but slower)</label>
      </div>
    </section>

    <div class="actions">
      <button type="button" id="btnCancel" class="btn-secondary">Cancel</button>
      <button type="submit" class="btn-primary">&#9654; Run Analysis</button>
    </div>
  </form>

  <script>${OPTIONS_JS}</script>
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
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: "Segoe UI", "Noto Sans KR", sans-serif;
    font-size: 13px;
    color: var(--fg);
    background: var(--bg);
    padding: 24px;
    max-width: 560px;
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

  select, input[type="number"] {
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    width: 100%;
    max-width: 200px;
  }

  select:focus, input[type="number"]:focus {
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

  .deep-section.hidden { display: none; }
`;

const OPTIONS_JS = `
(function() {
  const vscode = acquireVsCodeApi();
  const form = document.getElementById('optForm');
  const modeSelect = document.getElementById('mode');
  const deepSection = document.getElementById('deepSection');

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

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const options = {
      mode: modeSelect.value,
      noComments: document.getElementById('noComments').checked,
      byWord: document.getElementById('byWord').checked,
      normalize: document.getElementById('normalize').checked,
      collapseIdentical: document.getElementById('collapseIdentical').checked,
      noAutojunk: document.getElementById('noAutojunk').checked,
      threshold: Number(document.getElementById('threshold').value),
      kGram: Number(document.getElementById('kGram').value),
      window: Number(document.getElementById('window').value),
      thresholdDeep: Number(document.getElementById('thresholdDeep').value),
      pageNumber: document.getElementById('pageNumber').checked,
      fileNumber: document.getElementById('fileNumber').checked,
      batesNumber: document.getElementById('batesNumber').checked,
      hash: document.getElementById('hash').checked,
    };
    vscode.postMessage({ command: 'run', options });
  });

  document.getElementById('btnCancel').addEventListener('click', () => {
    vscode.postMessage({ command: 'cancel' });
  });
})();
`;
