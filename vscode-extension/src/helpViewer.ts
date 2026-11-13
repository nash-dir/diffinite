/**
 * Help Viewer — renders a detailed English manual for Diffinite options.
 */
import * as vscode from "vscode";
import { escHtml, THEME_CSS } from "./webviewUtils";
import { INTEGRITY_NOTICE, SCREEN_NOTICES } from "./notices";

export function showHelp(context: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "diffiniteHelp",
    "Diffinite: Help",
    vscode.ViewColumn.Beside, // Open next to the current editor
    { enableScripts: false }
  );

  panel.webview.html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Diffinite Help</title>
  <style>
    ${THEME_CSS}
    html, body { overflow-x: hidden; }
    body {
      padding: var(--sp-5);
      line-height: 1.55;
      max-width: 720px;
      margin: 0 auto;
    }
    @media (max-width: 600px) { body { padding: var(--sp-4); } }
    h1 { font-size: 18px; font-weight: 600; margin: 0 0 var(--sp-3); padding-bottom: var(--sp-2); border-bottom: 1px solid var(--border); }
    h2 { font-size: 14px; font-weight: 600; margin: var(--sp-6) 0 var(--sp-3); padding-bottom: var(--sp-1); border-bottom: 1px solid var(--border); }
    h3 { font-size: var(--fs-base); font-weight: 600; margin: var(--sp-4) 0 var(--sp-2); }
    p { margin: 0 0 var(--sp-3); }
    ul { margin: 0 0 var(--sp-3); padding-left: var(--sp-5); list-style-type: disc; }
    li { margin-bottom: var(--sp-2); }
    code { font-family: var(--code-font); background: var(--vscode-textCodeBlock-background, rgba(128,128,128,.15)); padding: 0 4px; border-radius: 2px; font-size: 0.95em; white-space: nowrap; }
    .param { font-weight: 600; color: var(--fg); }
  </style>
</head>
<body>
  <h1>Diffinite User Manual</h1>
  <p>Diffinite compares two source-code folders and reports how much, and where, their files are similar. It does not decide whether copying occurred or what kind of copying it was. Every setting described here is recorded in the report.</p>

  <h2>1. Scope and Limitations</h2>
  <ul>
    ${SCREEN_NOTICES.map((n) => `<li>${escHtml(n)}</li>`).join("\n    ")}
  </ul>

  <h2>2. Execution Modes</h2>
  <ul>
    <li><span class="param">Simple (1:1 only):</span> Pairs files by relative path or by file name similarity and compares each pair line by line.</li>
    <li><span class="param">Deep (1:1 and cross-file Winnowing):</span> Also compares every file in Directory A with every file in Directory B by token fingerprints, so renamed and moved files are found. For each listed pair, the <em>A in B</em> and <em>B in A</em> columns show the share of each file's fingerprints found in the other. A small file copied into a much larger one can fall below the Jaccard threshold and not be listed.</li>
  </ul>

  <h2>3. Comparison Options</h2>
  <ul>
    <li><span class="param">Strip comments:</span> Removes comments before comparison. The report states which comment handling was applied.</li>
    <li><span class="param">Compare by word:</span> Marks word changes within a line. Tabs are replaced with spaces before line matching, so a tab and spaces used for the same indentation do not misalign blocks.</li>
    <li><span class="param">Normalize whitespace:</span> Replaces tabs with spaces and collapses repeated spaces before comparison. Use it when the two folders use different indentation styles. It applies in line and word modes.</li>
    <li><span class="param">Detect moved code blocks:</span> Marks sections that appear at a different position in the paired file.</li>
    <li><span class="param">Disable autojunk:</span> Python's line differ can treat very frequent lines as uninformative. The extension disables this behavior by default, so those lines are matched like any other line. The report records the setting.</li>
    <li><span class="param">Binary files:</span> "Hash compare only" records whether two binary files have the same SHA-256 digest, without a line comparison.</li>
  </ul>

  <h2>4. Deep Compare Parameters</h2>
  <ul>
    <li><span class="param">Normalize identifiers:</span> Replaces identifiers with <code>ID</code> and literals with <code>LIT</code> before fingerprinting. Renamed identifiers then still match, and independently written code in the same domain also scores higher. The report states the measured false-positive rate and the profile it applies to.</li>
    <li><span class="param">K-gram size:</span> Default 5. The number of consecutive tokens in each fingerprint. A smaller value finds more matches and more coincidental ones. K = 5 is the value of the measured profile; the Winnowing paper (Schleimer et al., 2003) prescribes no value for source code.</li>
    <li><span class="param">Window size:</span> Default 4. With W = 4 and K = 5, any shared run of at least <code>W + K - 1 = 8</code> tokens produces at least one shared fingerprint. Whether the pair is listed still depends on the Jaccard threshold.</li>
    <li><span class="param">Jaccard threshold:</span> Unless you enter a value, the analyzer uses its default for the comparison you chose (normalized or not). The report records the value and its source; a value you enter is recorded as set by user.</li>
  </ul>

  <h2>5. Integrity and Report Options</h2>
  <ul>
    <li><span class="param">SHA-256 table:</span> Lists the SHA-256 digest of every analyzed file. ${escHtml(INTEGRITY_NOTICE)}</li>
    <li><span class="param">Bates numbers:</span> Stamps a sequential identifier at the bottom of every page, for example <code>PLAINTIFF-0001-CONFIDENTIAL</code>. Presets are saved in the VS Code settings (Settings &gt; Diffinite &gt; Bates Presets). A preset fills in the starting number but is not updated after an export, so enter the next unused number before each export.</li>
  </ul>
</body>
</html>`;
}
