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
import { buildReportViewModel, hasLineCounts, similarityText } from "./analysisModel";
import {
  addedCountLabel, changeUnit, countLabel, deletedCountLabel, matchMetricName, nameSimilarityLabel, overlapLabel, plural,
  thresholdLabel, thresholdSourceLabel,
} from "./labels";
import { RunGate } from "./runGate";
import { escHtml, getNonce, THEME_CSS } from "./webviewUtils";
import {
  REPORT_PRESETS, ReportFormat, applyReportPreset, describeReportOutput,
  isReportFormat, isReportPresetId,
} from "./reportPresets";
import { showFailure } from "./failureNotice";
import { INCONCLUSIVE_NOTICE, SCREEN_NOTICES, STATUS_LABELS } from "./notices";

const exportRunGate = new RunGate();

/**
 * Show the analysis results in a Webview panel.
 */
export function showResults(
  context: vscode.ExtensionContext,
  report: DiffiniteReport,
  options: DiffiniteOptions,
  sourceDirs: { dirA: string; dirB: string },
  reviewWarnings: readonly string[] = [],
): void {
  const panel = vscode.window.createWebviewPanel(
    "diffiniteResults",
    `Diffinite: Results (${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })})`,
    vscode.ViewColumn.Active,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  panel.webview.html = buildResultHtml(report, options, getNonce(), reviewWarnings);

  // A closed panel's webview getter throws; an export that finishes after the
  // user closed the tab must still report "saved" instead of failing here.
  let disposed = false;
  panel.onDidDispose(() => { disposed = true; }, undefined, context.subscriptions);
  const notifyExportComplete = (): void => {
    if (disposed) { return; }
    try {
      void panel.webview.postMessage({ command: "exportComplete" });
    } catch {
      // Disposed between the check and the call; nothing left to update.
    }
  };

  // Handle messages from the Webview (export buttons)
  panel.webview.onDidReceiveMessage(
    async (msg: { command?: unknown; format?: unknown; preset?: unknown }) => {
      if (msg?.command === "export" && isReportFormat(msg.format) && isReportPresetId(msg.preset)) {
        const format = msg.format;
        const presetOptions = applyReportPreset(options, msg.preset);
        if (!exportRunGate.tryEnter()) {
          notifyExportComplete();
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
            defaultUri: vscode.Uri.file(defaultExportPath(
              defaultFilename,
              vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
              sourceDirs,
            )),
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
          notifyExportComplete();
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
        notifyExportComplete();
      }
    },
    undefined,
    context.subscriptions
  );
}

function isWithinDirectory(candidate: string, root: string): boolean {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  return relative === "" || (!path.isAbsolute(relative) && relative !== ".." && !relative.startsWith(`..${path.sep}`));
}

/**
 * Folder the save dialog starts in. A bare file name would resolve to the
 * drive root. Prefer the workspace folder unless it is (inside) a compared
 * folder, where the export would be refused; otherwise use A's parent folder.
 */
export function defaultExportPath(
  defaultFilename: string,
  workspaceFolder: string | undefined,
  sourceDirs: { dirA: string; dirB: string },
): string {
  const sources = [sourceDirs.dirA, sourceDirs.dirB];
  const usable = (folder: string): boolean =>
    !sources.some((source) => isWithinDirectory(folder, source));
  const candidates = [workspaceFolder, path.dirname(path.resolve(sourceDirs.dirA))]
    .filter((folder): folder is string => !!folder);
  const baseDir = candidates.find(usable) ?? path.dirname(path.resolve(sourceDirs.dirA));
  return path.join(baseDir, defaultFilename);
}

/* ------------------------------------------------------------------ */
/* HTML Builder                                                        */
/* ------------------------------------------------------------------ */

/** Shown in place of the Deep Compare table when Deep Compare reported 0 pairs. */
export const NO_DEEP_PAIR_SENTENCE = "No file pair reached the Jaccard threshold.";

// A wrapped code line continues two characters in from its own indentation,
// and indentation beyond 32 columns (four 8-column tab stops) is not followed
// further: the values of _HANG_EXTRA_CHARS, _HANG_MAX_INDENT and _TAB_SIZE in
// pdf_gen.py, so the Results view wraps lines as the HTML report does.
const HANG_EXTRA_CHARS = 2;
const HANG_MAX_INDENT = 32;
const TAB_SIZE = 8;

/** Columns of leading whitespace in a code cell's markup (tabs to 8-column stops). */
export function leadingColumns(preInner: string): number {
  const textOnly = preInner.replace(/<[^>]*>/g, "");
  let col = 0;
  let i = 0;
  while (i < textOnly.length) {
    let ch = textOnly[i];
    let len = 1;
    if (ch === "&") {
      const m = /^&(?:nbsp|#160|#x0*a0|#32|#x0*20|#9|#x0*9|Tab);/i.exec(textOnly.slice(i));
      if (!m) { break; }
      const ent = m[0].toLowerCase();
      ch = ent === "&#9;" || /^&#x0*9;$/.test(ent) || ent === "&tab;" ? "\t" : " ";
      len = m[0].length;
    }
    if (ch === "\t") { col += TAB_SIZE - (col % TAB_SIZE); }
    else if (ch === " " || ch === "\u00a0") { col += 1; }
    else { break; }
    i += len;
  }
  return col;
}

/**
 * Give each indented code line a hanging indent of its own indentation plus
 * two characters, in ch, as pdf_gen._hanging_indent_style does for the HTML
 * report. Unindented lines keep the stylesheet's two-character indent.
 */
export function hangingIndentDiff(htmlDiff: string): string {
  return htmlDiff.replace(/<pre>([\s\S]*?)<\/pre>/g, (whole, inner: string) => {
    const indent = Math.min(leadingColumns(inner), HANG_MAX_INDENT);
    if (!indent) { return whole; }
    const width = `${indent + HANG_EXTRA_CHARS}ch`;
    return `<pre style="padding-left: ${width}; text-indent: -${width};">${inner}</pre>`;
  });
}

export function buildResultHtml(
  report: DiffiniteReport,
  options: DiffiniteOptions,
  nonce: string,
  reviewWarnings: readonly string[] = [],
): string {
  const meta = report.metadata;
  const summary = report.summary;
  const view = buildReportViewModel(report);
  const reviewBanner = reviewWarnings.length
    ? [{
      kind: "warning" as const,
      title: "This report does not match the analysis you reviewed",
      message: reviewWarnings.join(" "),
    }]
    : [];
  const bannersHtml = [...reviewBanner, ...view.banners].map((banner) => `
    <div class="notice ${banner.kind}" role="${banner.kind === "warning" ? "alert" : "note"}">
      <span class="notice-title">${escHtml(banner.title)}</span>
      <span class="notice-body">${escHtml(banner.message)}</span>
    </div>
  `).join("");

  // --- Summary section ---
  // Each figure is a count followed by its noun, singular for 1.
  const stat = (n: number, singular: string, pluralForm: string, rest = ""): string =>
    `<span class="stat"><strong>${countLabel(n)}</strong> ${n === 1 ? singular : pluralForm}${rest}</span>`;
  const excludedPairs = report.analysis_status.diff.excluded_pair_count;
  let summaryHtml = `
    <div class="summary-bar">
      ${stat(summary.matched_pairs, "matched pair", "matched pairs")}
      ${stat(summary.unmatched_a_count, "file", "files", " only in A")}
      ${stat(summary.unmatched_b_count, "file", "files", " only in B")}${
        excludedPairs
          ? `
      ${stat(excludedPairs, "matched pair", "matched pairs", " not compared (binary-file policy)")}`
          : ""}
    </div>
  `;
  const metric = matchMetricName(report.comparison_unit);
  const unit = changeUnit(report.comparison_unit);
  const unitTitle = unit.charAt(0).toUpperCase() + unit.slice(1);

  if (meta.exec_mode !== "unknown") {
    // Fingerprint settings (K, W, Jaccard threshold, normalize) describe Deep
    // Compare only; Simple mode never fingerprints, so they are not shown.
    const deepSettings = meta.exec_mode === "deep" ? `
        <span>K: ${meta.k ?? "unknown"}</span>
        <span>W: ${meta.w ?? "unknown"}</span>
        <span>Jaccard threshold: ${meta.threshold === null ? "unknown" : escHtml(thresholdLabel(meta.threshold))}</span>
        <span>Threshold source: ${escHtml(thresholdSourceLabel(meta.threshold_provenance))}</span>
        <span>Identifier normalization: ${meta.normalize === null ? "unknown" : meta.normalize ? "on" : "off"}</span>
        <span>Comments (line diff / Deep Compare): ${escHtml(String(report.preprocessing.line_diff_comments ?? "unknown"))} / ${escHtml(String(report.preprocessing.deep_compare_comments ?? "unknown"))}</span>`
      : `
        <span>Comments: ${escHtml(String(report.preprocessing.line_diff_comments ?? "unknown"))}</span>`;
    // The full SHA-256 is in the review summary settings and the report; the
    // header shows a 12-hex-digit prefix (display only) to stay on one line.
    const excludedCountValue = report.analysis_status.exclusion.excluded_count;
    const excludedCount = excludedCountValue === null ? "unknown" : countLabel(excludedCountValue);
    const sensitiveMode = { exclude: "excluded", include: "included", error: "stop when found" }[meta.sensitive_files] ?? "unknown";
    const includeFilter = meta.include_patterns.length
      ? `\n        <span>Include filter: ${escHtml(meta.include_patterns.join("; "))}</span>` : "";
    const exclusion = meta.ignore_file_sha256 === null
      ? "none"
      : `${plural(meta.ignore_patterns.length, "rule")}, SHA-256 prefix ${meta.ignore_file_sha256.slice(0, 12)}`;
    summaryHtml += `
      <div class="meta-bar">
        <span>Mode: ${escHtml(meta.exec_mode)}</span>${deepSettings}
        <span title="${escHtml(meta.ignore_patterns.join("\n"))}">Exclusion list (.diffignore): ${escHtml(exclusion)}</span>
        <span>${escHtml(STATUS_LABELS.inputsExcluded)}: ${escHtml(excludedCount)}</span>
        <span>Sensitive files: ${escHtml(sensitiveMode)}</span>${includeFilter}
      </div>
    `;
  }

  // --- Diff blocks ---
  let blocksHtml = "";
  report.results.forEach((r, i) => {

    blocksHtml += `
      <section class="diff-block" id="block-${i}" aria-label="Pair ${i + 1} of ${report.results.length}">
        <div class="block-header">
          <span class="block-index num">Pair ${countLabel(i + 1)} of ${countLabel(report.results.length)}</span>
          <span class="block-files">
            ${escHtml(r.file_a)} vs. ${escHtml(r.file_b)}
          </span>
          <span class="block-sim num">${hasLineCounts(r) ? `${escHtml(metric)}: ` : ""}${escHtml(similarityText(r))}</span>
        </div>
        <div class="block-stats">${
          // +/- counts exist only for pairs difflib compared; never print +0/-0
          // for a hash-only or failed pair.
          hasLineCounts(r)
            ? `
          <span class="stat-add" title="${unitTitle} only in B">${addedCountLabel(r.additions)}</span>
          <span class="stat-del" title="${unitTitle} only in A">${deletedCountLabel(r.deletions)}</span>`
            : `
          <span class="stat-add">Not compared line by line; no line counts</span>`}
          <span class="stat-sim">Name similarity: ${nameSimilarityLabel(r.name_similarity)}</span>
        </div>
        ${
          r.error
            ? `<div class="block-error">Error: ${escHtml(r.error)}</div>`
            : `<div class="block-diff">${hangingIndentDiff(r.html_diff)}</div>`
        }
      </section>
    `;
  });

  // --- Deep Compare section ---
  let deepHtml = "";
  if (view.deepRows.length > 0) {
    // overlapLabel: two decimals, 100.00% only for an exact 1.0 (Jaccard is stored unrounded).
    const pct = (v: number | null): string => (v === null ? "n/a" : overlapLabel(v));
    let deepRows = "";
    for (const m of view.deepRows) {
        const jpct = overlapLabel(m.jaccard);
        const jClass = m.kind === "inconclusive" ? "jlabel-inconclusive" : "";
        deepRows += `
          <tr>
            <td>${escHtml(m.file_a)}</td>
            <td>${escHtml(m.file_b)}</td>
            <td>${countLabel(m.shared_hashes)}</td>
            <td><span class="jlabel ${jClass}">${jpct}${m.kind === "candidate" ? "" : ` (${escHtml(m.label.toLowerCase())})`}</span></td>
            <td>${pct(m.containment_a_in_b)}</td>
            <td>${pct(m.containment_b_in_a)}</td>
          </tr>
        `;
    }

    deepHtml = `
      <section class="deep-section" id="block-deep">
        <h2>Deep Compare: Cross-Match Results</h2>
        <div class="table-wrap">
        <table class="deep-table">
          <colgroup><col><col><col class="w-shared"><col class="w-jac"><col class="w-num"><col class="w-num"></colgroup>
          <thead>
            <tr><th scope="col">File A</th><th scope="col">File B</th><th scope="col" title="Fingerprint hashes found in both files">Shared hashes</th><th scope="col">Jaccard</th><th scope="col" title="Shared hashes divided by the unique hashes of the A file">A in B</th><th scope="col" title="Shared hashes divided by the unique hashes of the B file">B in A</th></tr>
          </thead>
          <tbody>${deepRows}</tbody>
        </table>
        </div>${view.deepRows.some((m) => m.kind === "inconclusive") ? `
        <p class="deep-note">${escHtml(INCONCLUSIVE_NOTICE)}</p>` : ""}
      </section>
    `;
  } else if (report.analysis_status.deep.reported_pair_count === 0) {
    // Deep Compare ran and reported no pair (null: it did not run, so nothing is said).
    deepHtml = `
      <section class="deep-section" id="block-deep">
        <h2>Deep Compare: Cross-Match Results</h2>
        <p class="deep-empty">${escHtml(NO_DEEP_PAIR_SENTENCE)}</p>
      </section>
    `;
  }

  // --- Unmatched files ---
  let unmatchedHtml = "";
  if (report.unmatched_a.length > 0 || report.unmatched_b.length > 0) {
    unmatchedHtml = `<section class="unmatched-section">`;
    if (report.unmatched_a.length > 0) {
      unmatchedHtml += `<h3>Unmatched in A</h3><ul>${report.unmatched_a.map(f => `<li>${escHtml(f)}</li>`).join("")}</ul>`;
    }
    if (report.unmatched_b.length > 0) {
      unmatchedHtml += `<h3>Unmatched in B</h3><ul>${report.unmatched_b.map(f => `<li>${escHtml(f)}</li>`).join("")}</ul>`;
    }
    unmatchedHtml += `</section>`;
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
  <div class="page" id="page" tabindex="-1">
  <header>
    <h1>Diffinite: Results</h1>
    <dl class="dirs">
      <dt>A:</dt><dd class="mono">${escHtml(report.dir_a)}</dd>
      <dt>B:</dt><dd class="mono">${escHtml(report.dir_b)}</dd>
    </dl>
    ${bannersHtml}
    ${summaryHtml}
    <h2 class="notices-h">Scope and limitations</h2>
    <ol class="notices">${SCREEN_NOTICES.map((n) => `<li>${escHtml(n)}</li>`).join("")}</ol>
  </header>

  ${buildExportSection(options)}

  <main>
    ${blocksHtml}
    ${deepHtml}
    ${unmatchedHtml}
  </main>
  </div>

  <!-- Navigation bar, docked below the scrolling page so it never covers content -->
  <nav class="dock-nav" id="dockNav" aria-label="Pair navigation">
    <button type="button" class="btn-secondary" id="btnPrev" title="Previous pair (K)">Previous</button>
    <span class="nav-pos num" id="navPos">0 of 0</span>
    <button type="button" class="btn-secondary" id="btnNext" title="Next pair (J)">Next</button>
    <span class="nav-divider" aria-hidden="true"></span>
    <button type="button" class="btn-secondary" id="btnGoExport" title="Go to the export settings (E)">Export settings</button>
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
        <button type="button" class="btn-primary" id="btnExport">Export</button>
        <p class="dim small">You choose the file name and folder next. Presets change only the layout of the report.</p>
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
  /* The page scrolls in .page and the navigation bar is a separate row below
     it, so the bar can never sit on top of a diff line. */
  html, body { height: 100%; overflow: hidden; }
  body { display: flex; flex-direction: column; font-synthesis: none; }
  .page { flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden; }

  header { padding: var(--sp-4) var(--sp-5) var(--sp-3); border-bottom: 1px solid var(--border); }
  h1 { font-size: var(--fs-h1); font-weight: 600; line-height: 1.3; margin-bottom: var(--sp-2); }
  h2 { font-size: var(--fs-h2); font-weight: 600; margin: var(--sp-5) 0 var(--sp-3); padding-bottom: var(--sp-1); border-bottom: 1px solid var(--border); }
  h3 { font-size: var(--fs-sm); font-weight: 600; color: var(--fg-dim); margin: var(--sp-3) 0 var(--sp-1); }

  .dirs { display: grid; grid-template-columns: auto 1fr; gap: 0 var(--sp-2); font-size: var(--fs-sm); color: var(--fg-dim); margin-bottom: var(--sp-2); }
  .dirs dd { overflow-wrap: anywhere; min-width: 0; }
  .small { font-size: var(--fs-xs); margin-top: var(--sp-2); }

  .summary-bar, .meta-bar { display: flex; flex-wrap: wrap; gap: var(--sp-1) var(--sp-4); margin-top: var(--sp-2); }
  .summary-bar { font-size: var(--fs-base); }
  .summary-bar strong { font-weight: 600; font-variant-numeric: tabular-nums; }
  .meta-bar { color: var(--fg-dim); font-size: var(--fs-xs); font-family: var(--code-font); }
  .meta-bar span { overflow-wrap: anywhere; }

  main { padding: var(--sp-4) var(--sp-5); }
  .notices-h { font-size: var(--fs-sm); color: var(--fg-dim); margin: var(--sp-3) 0 var(--sp-1); padding: 0; border: 0; }
  .notices { padding-left: var(--sp-5); font-size: var(--fs-sm); color: var(--fg-dim); max-width: 120ch; }
  .notices li { margin: 2px 0; }

  /* Export */
  .export-section { margin: 0 var(--sp-5); padding: 0 0 var(--sp-4); border-bottom: 1px solid var(--border); }
  .export-grid { display: grid; grid-template-columns: minmax(220px, 1fr) 2fr; gap: var(--sp-4) var(--sp-5); }
  @media (max-width: 640px) {
    .export-grid { grid-template-columns: 1fr; }
    header, main { padding-left: var(--sp-4); padding-right: var(--sp-4); }
    .export-section { margin: 0 var(--sp-4); }
  }
  .field-label { display: block; font-weight: 600; font-size: var(--fs-sm); margin-bottom: var(--sp-1); }
  #presetSelect { height: var(--control-h); padding: 0 4px; width: 100%; max-width: 320px; }
  .preset-help { color: var(--fg-dim); font-size: var(--fs-sm); margin: var(--sp-1) 0 var(--sp-3); max-width: 60ch; }
  .formats { border: none; margin: 0 0 var(--sp-3); }
  .radio { display: flex; align-items: center; gap: var(--sp-2); margin: var(--sp-1) 0; cursor: pointer; }
  .contents { padding-left: var(--sp-4); font-size: var(--fs-sm); max-width: 90ch; }
  .contents li { margin: var(--sp-1) 0; overflow-wrap: anywhere; }
  ul[hidden], p[hidden] { display: none; }

  /* Diff blocks */
  .diff-block { background: var(--bg); border: 1px solid var(--border); margin-bottom: var(--sp-4); overflow: hidden; scroll-margin-top: var(--sp-2); }
  /* The current pair is named in the navigation bar; its header text is set
     in the full text color rather than drawn with a colored frame. */
  .diff-block.active .block-index { color: var(--fg); }
  .block-header { display: flex; align-items: baseline; gap: var(--sp-3); padding: 6px var(--sp-3); background: var(--bg-surface); border-bottom: 1px solid var(--border); }
  .block-index { color: var(--fg-dim); font-size: var(--fs-sm); flex: none; }
  .block-files { flex: 1; min-width: 0; font-family: var(--code-font); font-size: var(--fs-sm); overflow-wrap: anywhere; }
  .block-sim { flex: none; font-weight: 600; }
  .block-stats { display: flex; gap: var(--sp-3); padding: var(--sp-1) var(--sp-3); font-size: var(--fs-xs); color: var(--fg-dim);
                 border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }
  .stat-add, .stat-del { color: var(--fg-dim); }
  .block-error { padding: var(--sp-3); color: var(--error); }
  .block-diff { overflow-x: auto; }

  /* Diff table (HTML produced by differ.py): a quiet code view with a single
     rule after each line-number gutter and between the two sides. */
  .difftbl { width: 100%; border-collapse: collapse; font-size: var(--fs-xs); table-layout: fixed; }
  .difftbl th, .difftbl td { border: 0; padding: 0 var(--sp-1); vertical-align: top; }
  /* File names in the pane headers are set in regular weight: many CJK fonts
     have no bold face, and a synthesized one smears the glyphs. */
  .difftbl thead th { background: var(--bg-surface); color: var(--fg-dim); font-weight: normal; padding: var(--sp-1) 6px;
                      border-bottom: 1px solid var(--border); text-align: left; }
  .difftbl .ln { color: var(--fg-dim); text-align: right; font-size: 10px; font-variant-numeric: tabular-nums;
                 border-right: 1px solid var(--border); user-select: none; }
  .difftbl td.code + td.ln, .difftbl th.code + th.ln { border-left: 1px solid var(--border); }
  .difftbl .code { white-space: pre-wrap; word-wrap: break-word; font-family: var(--code-font); }
  .difftbl .code pre { margin: 0; padding: 0; font-size: inherit; font-family: inherit; white-space: pre-wrap; tab-size: 8; }
  /* A wrapped source line continues 2 characters in from the line's own
     indentation, so it is not read as a new line (the same hanging indent as
     the PDF and HTML reports). Indented lines carry their width inline. */
  .difftbl td.code pre { padding-left: 2ch; text-indent: -2ch; }
  .difftbl .del { background: var(--diff-del-line); }
  .difftbl .add { background: var(--diff-add-line); }
  /* High Contrast themes have no line background; the theme's diff border
     color marks a changed line with one solid bar at the line number. In
     other themes that border color is transparent, so nothing is drawn. */
  .difftbl td.ln.del { box-shadow: inset 3px 0 0 var(--diff-del-border); }
  .difftbl td.ln.add { box-shadow: inset 3px 0 0 var(--diff-add-border); }
  .difftbl .empty { background: repeating-linear-gradient(135deg, transparent 0 4px, var(--hover-bg) 4px 6px); }
  /* Placeholder rows keep their hatch in High Contrast, where --hover-bg is transparent. */
  body.vscode-high-contrast .difftbl .empty,
  body.vscode-high-contrast-light .difftbl .empty {
    background: repeating-linear-gradient(135deg, transparent 0 7px, var(--border) 7px 8px);
  }
  /* Line changed (word level): its own neutral tint, so a changed A line is
     not read as a B-only line. High Contrast marks it with a bar instead. */
  .difftbl .chg { background: var(--diff-chg-line); }
  body.vscode-high-contrast .difftbl .chg,
  body.vscode-high-contrast-light .difftbl .chg { background: transparent; }
  body.vscode-high-contrast .difftbl td.ln.chg,
  body.vscode-high-contrast-light .difftbl td.ln.chg { box-shadow: inset 3px 0 0 var(--fg); }
  .difftbl .moved-del { background: var(--diff-del-line); box-shadow: inset 3px 0 0 var(--diff-move-border); }
  .difftbl .moved-add { background: var(--diff-add-line); box-shadow: inset 3px 0 0 var(--diff-move-border); }
  .word-del { background: var(--diff-del-text); text-decoration: line-through; padding: 0 1px; }
  .word-add { background: var(--diff-add-text); text-decoration: underline; padding: 0 1px; }
  /* Changed whitespace: a light tint only, as in the reports. A struck or
     underlined run of spaces would read as dash characters in the source. */
  .word-del.ws, .word-add.ws { background: var(--diff-ws-text); text-decoration: none; }
  body.vscode-high-contrast .word-del.ws, body.vscode-high-contrast .word-add.ws,
  body.vscode-high-contrast-light .word-del.ws, body.vscode-high-contrast-light .word-add.ws {
    outline: 1px dotted var(--fg-dim); outline-offset: -1px;
  }
  /* differ.py sets an inline light background on fold rows; override it for every theme. */
  .difftbl tr.fold td { text-align: center; color: var(--fg-dim) !important; background: var(--bg-surface) !important;
                        border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 2px; }

  /* Source text is shown upright and in regular weight whatever the token type:
     Pygments sets italic comments and bold keywords inline, and CJK fonts have
     no italic or bold face, so the browser would slant or smear them. */
  .block-diff .code span[style] { font-style: normal !important; font-weight: normal !important; }

  /* Pygments token colors (inline styles from differ.py) are designed for light
     backgrounds. In dark and high-contrast themes they become unreadable, so the
     text falls back to the theme color there. VS Code sets these body classes. */
  body.vscode-dark .block-diff .code span[style],
  body.vscode-high-contrast .block-diff .code span[style] { color: inherit !important; background: none !important; }

  /* Override Pygments error token red border (inline style: border: 1px solid #F00) */
  .block-diff span[style*="border"] { border: none !important; }

  /* Deep Compare label: plain text; a color scale would read as a verdict. */
  .jlabel { white-space: nowrap; }
  .jlabel-inconclusive { color: var(--fg-dim); }
  .deep-empty { font-size: var(--fs-sm); max-width: 120ch; }
  .deep-note { margin: var(--sp-2) 0 0; font-size: var(--fs-sm); color: var(--fg-dim); max-width: 120ch; }

  /* Deep Compare */
  .deep-section { margin-top: var(--sp-5); }
  .table-wrap { overflow-x: auto; }
  .deep-table { width: 100%; min-width: 560px; border-collapse: collapse; table-layout: fixed; }
  .deep-table .w-num { width: 92px; } .deep-table .w-shared { width: 120px; } .deep-table .w-jac { width: 200px; }
  .deep-table th, .deep-table td { border-bottom: 1px solid var(--border); padding: 4px var(--sp-2); text-align: left; vertical-align: top; overflow-wrap: anywhere; }
  .deep-table thead th { font-size: var(--fs-sm); font-weight: 600; color: var(--fg-dim); border-top: 1px solid var(--border); vertical-align: bottom; }
  .deep-table td:nth-child(-n+2) { font-family: var(--code-font); font-size: var(--fs-sm); }
  .deep-table th:nth-child(n+3), .deep-table td:nth-child(n+3) { text-align: right; font-variant-numeric: tabular-nums; }
  .deep-table tbody tr:hover { background: var(--hover-bg); }

  /* Unmatched */
  .unmatched-section { margin-top: var(--sp-4); font-size: var(--fs-sm); }
  .unmatched-section ul { list-style: none; border-top: 1px solid var(--border); }
  .unmatched-section li { padding: 2px 0; border-bottom: 1px solid var(--border); font-family: var(--code-font); overflow-wrap: anywhere; }

  /* Docked navigation: its own row under the page, full width, never overlapping. */
  .dock-nav { flex: none; display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: var(--sp-2);
              padding: 6px var(--sp-5); background: var(--bg-surface); border-top: 1px solid var(--border); }
  .nav-pos { color: var(--fg-dim); font-size: var(--fs-sm); min-width: 64px; text-align: center; }
  .nav-divider { width: 1px; height: 18px; background: var(--border); }
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

  function goTo(idx, scroll) {
    if (blocks.length === 0) return;
    idx = Math.max(0, Math.min(idx, blocks.length - 1));
    blocks.forEach(b => b.classList.remove('active'));
    blocks[idx].classList.add('active');
    if (scroll !== false) blocks[idx].scrollIntoView({ behavior: 'smooth', block: 'start' });
    currentBlock = idx;
    navPos.textContent = (idx + 1) + ' of ' + blocks.length;
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
  // Start on the first block without scrolling past the header, so the
  // notices and summary are the first thing read.
  if (blocks.length > 0) goTo(0, false);
  // The page scrolls inside #page (the navigation bar is docked below it);
  // focus it so the arrow, Page Up/Down and Space keys scroll the page.
  document.getElementById('page').focus({ preventScroll: true });
})();
`;
