/**
 * Help Viewer — renders a detailed English manual for Diffinite options.
 */
import * as vscode from "vscode";
import { THEME_CSS } from "./webviewUtils";

export function showHelp(context: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "diffiniteHelp",
    "Diffinite — Help & Manual",
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
    body {
      font-size: 14px;
      padding: 24px;
      line-height: 1.6;
      max-width: 800px;
      margin: 0 auto;
    }
    h1 { color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 8px; }
    h2 { color: var(--fg); margin-top: 30px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
    h3 { color: var(--accent); margin-top: 20px; }
    ul { padding-left: 20px; list-style-type: square; }
    li { margin-bottom: 8px; }
    code { background: var(--vscode-textCodeBlock-background, rgba(128,128,128,.15)); padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    .important { border-left: 4px solid var(--error); padding-left: 12px; background: var(--vscode-inputValidation-errorBackground, rgba(241, 76, 76, 0.1)); margin: 16px 0; padding-top: 8px; padding-bottom: 8px; }
    .param { font-weight: bold; color: var(--fg); }
  </style>
</head>
<body>
  <h1>Diffinite User Manual</h1>
  <p>Diffinite is a forensic source-code comparison tool designed for IP litigation and code audits. This guide explains how to configure parameters and how each setting is recorded in the report, so the results can be explained. It reports how much and where code is similar; it does not decide whether copying occurred or what kind.</p>

  <h2>1. Execution Modes</h2>
  <p>Diffinite operates in two primary modes:</p>
  <ul>
    <li><span class="param">Simple (1:1 only):</span> Compares files directly by matching their names or relative paths. Best for standardized projects where file structures are identical.</li>
    <li><span class="param">Deep (1:1 + N:M Winnowing):</span> Cross-matches every file in Directory A against every file in Directory B and reports shared fingerprint similarity candidates, including across renamed files. For listed pairs, the <em>A in B / B in A</em> columns show how much of each file was carried over; a small file copied into a much larger one can still fall below the Jaccard threshold and not be listed.</li>
  </ul>

  <h2>2. Forensic Precision Options</h2>
  <div class="important">
    <strong>Autojunk disclosure</strong><br>
    Python's line differ can treat very frequent lines as low-information for sequence matching. Diffinite disables that heuristic by default so those lines remain eligible; this changes matching behavior but does not eliminate false positives or constitute a legal determination.
  </div>
  <ul>
    <li><span class="param">Strip comments:</span> Removes comments before comparison so the report can show similarity with comment text excluded. The applied preprocessing is recorded in the report.</li>
    <li><span class="param">Compare by word:</span> Highlights exact word changes within a line. Useful for tracking variable name changes. <strong>Note:</strong> When enabled, tabs are automatically replaced with spaces before line matching to prevent tab-vs-space indentation from causing block misalignment.</li>
    <li><span class="param">Normalize whitespace:</span> Replaces all tabs with spaces and collapses multiple consecutive spaces into one before comparison. Enable this when the original and copied code use different indentation styles (e.g., tabs vs 4 spaces) and this difference is polluting the diff output. Works in both line and word comparison modes.</li>
    <li><span class="param">Detect moved code blocks:</span> Highlights candidate sections that appear at a different location within the paired file. This is a similarity aid, not a finding about how the change occurred.</li>
    <li><span class="param">Binary files:</span> "Hash compare only" records whether binary bytes have the same SHA-256 digest without sending them through the text differ. A digest is an integrity check, not chain-of-custody proof.</li>
  </ul>

  <h2>3. Deep Compare (Winnowing) Parameters</h2>
  <p>These settings govern which N:M fingerprint similarities are surfaced as candidates. The effective values and provenance are recorded so they can be explained.</p>
  <ul>
    <li><span class="param">Normalize identifiers:</span> Converts identifiers to <code>ID</code> and literals to <code>LIT</code> before fingerprinting, making the channel less sensitive to renamed identifiers while also increasing false-positive risk.</li>
    <li><span class="param">K-gram size:</span> (Default: 5). The sliding window size for token generation. A smaller K-gram finds more matches (higher recall) but increases noise. K=5 is the value frozen in the measured calibration profile; the Winnowing paper (Schleimer 2003) prescribes no K for source code.</li>
    <li><span class="param">Window size:</span> (Default: 4). With W=4 and K=5, any shared run of at least <code>(W + K - 1) = 8</code> tokens always yields at least one shared fingerprint. Whether the pair is listed still depends on the Deep threshold.</li>
    <li><span class="param">Min Jaccard threshold:</span> Auto mode does not send a numeric override; Python selects and records the effective threshold and provenance. The historical raw default is uncalibrated, and low-threshold results are manual-review similarity candidates rather than legal copying determinations.</li>
  </ul>

  <h2>4. Integrity Checks & Reporting</h2>
  <ul>
    <li><span class="param">Embed SHA-256 file hashes:</span> Records a reproducible digest of every analyzed source file. It can reveal a byte mismatch against the manifest, but by itself does not prove custody history or absence of prior tampering.</li>
    <li><span class="param">Bates numbers:</span> Stamps sequential identifiers at the bottom of every page (e.g., <code>PLAINTIFF-0001-CONFIDENTIAL</code>). You can save format presets for different cases directly in the VS Code settings (Settings &gt; Diffinite &gt; Bates Presets). A preset pre-fills the start number; it is not updated after export, so set the next unused number yourself before each export.</li>
  </ul>
</body>
</html>`;
}
