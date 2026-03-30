/**
 * Help Viewer — renders a detailed English manual for Diffinite options.
 */
import * as vscode from "vscode";

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
    :root {
      --bg: #1e1e1e;
      --bg-surface: #252526;
      --fg: #cccccc;
      --fg-dim: #888;
      --accent: #0078d4;
      --red: #f14c4c;
      --border: #3c3c3c;
    }
    body {
      font-family: "Segoe UI", -apple-system, sans-serif;
      font-size: 14px;
      color: var(--fg);
      background: var(--bg);
      padding: 24px;
      line-height: 1.6;
      max-width: 800px;
      margin: 0 auto;
    }
    h1 { color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 8px; }
    h2 { color: #fff; margin-top: 30px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
    h3 { color: var(--accent); margin-top: 20px; }
    ul { padding-left: 20px; list-style-type: square; }
    li { margin-bottom: 8px; }
    code { background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-family: "Consolas", monospace; font-size: 13px; color: #dcdcaa; }
    .important { border-left: 4px solid var(--red); padding-left: 12px; background: rgba(241, 76, 76, 0.1); margin: 16px 0; padding-top: 8px; padding-bottom: 8px; }
    .param { font-weight: bold; color: #fff; }
  </style>
</head>
<body>
  <h1>Diffinite User Manual</h1>
  <p>Diffinite is a forensic source-code comparison tool designed for IP litigation and code audits. This guide explains how to configure parameters to ensure your results are accurate, explainable, and legally sound.</p>

  <h2>1. Execution Modes</h2>
  <p>Diffinite operates in two primary modes:</p>
  <ul>
    <li><span class="param">Simple (1:1 only):</span> Compares files directly by matching their names or relative paths. Best for standardized projects where file structures are identical.</li>
    <li><span class="param">Deep (1:1 + N:M Winnowing):</span> Recommended for litigation. Even if an author renames files, splits classes, or merges modules, the Stanford MOSS Winnowing algorithm will cross-match every single file in Directory A against every file in Directory B to find stolen code fragments.</li>
  </ul>

  <h2>2. Forensic Precision Options</h2>
  <div class="important">
    <strong>CRITICAL: Disable Autojunk (Default: Enabled)</strong><br>
    The standard Python diff library uses a "junk" heuristic to speed up processing by ignoring highly repetitive lines (like <code>return;</code> or <code>}</code>). In legal forensics, ignoring any line is unacceptable. Diffinite defaults this to <b>True</b> to force a precise, 100% line-by-line comparison, eliminating false positives at the cost of processing speed.
  </div>
  <ul>
    <li><span class="param">Strip comments:</span> Removes comments before comparison. Crucial if the plagiarist translated or deleted original comments.</li>
    <li><span class="param">Compare by word:</span> Highlights exact word changes within a line. Useful for tracking variable name changes. <strong>Note:</strong> When enabled, tabs are automatically replaced with spaces before line matching to prevent tab-vs-space indentation from causing block misalignment.</li>
    <li><span class="param">Normalize whitespace:</span> Replaces all tabs with spaces and collapses multiple consecutive spaces into one before comparison. Enable this when the original and copied code use different indentation styles (e.g., tabs vs 4 spaces) and this difference is polluting the diff output. Works in both line and word comparison modes.</li>
    <li><span class="param">Detect moved code blocks:</span> Identifies sections of code that were cut and pasted elsewhere within the same file. Highlighted in purple/blue to distinguish them from simple deletions/additions.</li>
    <li><span class="param">Binary files:</span> "Hash compare only" will ensure images and compiled binaries are tracked in the cryptographic chain of custody without crashing the text differ.</li>
  </ul>

  <h2>3. Deep Compare (Winnowing) Parameters</h2>
  <p>These settings govern the mathematical threshold for N:M cross-matching. Because they dictate what is identified as a "clone", <b>you must be able to justify these numbers in court.</b></p>
  <ul>
    <li><span class="param">Normalize identifiers:</span> Converts variables to <code>ID</code> and numbers to <code>LIT</code>. Turn this ON if you suspect the plagiarist used "Find and Replace" to change variable names globally (Type-2 Clone Detection).</li>
    <li><span class="param">K-gram size:</span> (Default: 5). The sliding window size for token generation. A smaller K-gram finds more matches (higher recall) but increases noise. K=5 is academically cited (Schleimer 2003) as optimal for source code.</li>
    <li><span class="param">Window size:</span> (Default: 4). The Winnowing density guarantee. A window of 4 means that any shared sequence of <code>(W + K - 1) = 8</code> tokens is <strong>mathematically guaranteed</strong> to be detected. </li>
    <li><span class="param">Min Jaccard threshold:</span> (Default: 5). Discards cross-matches that share less than 5% of their fingerprints. Setting this lower than 5% usually yields false positives (boilerplates, standard library imports).</li>
  </ul>

  <h2>4. Chain of Custody & Reporting</h2>
  <ul>
    <li><span class="param">Embed SHA-256 file hashes:</span> Always leave this enabled. It stamps the cryptographic hash of every source file onto the report's cover page, proving the evidence was not tampered with.</li>
    <li><span class="param">Bates numbers:</span> Automatically stamps unique, sequential alphanumeric identifiers at the bottom of every page (e.g., <code>PLAINTIFF-0001-CONFIDENTIAL</code>). You can save format presets for different cases directly in the VS Code settings (Settings &gt; Diffinite &gt; Bates Presets).</li>
  </ul>
</body>
</html>`;
}
