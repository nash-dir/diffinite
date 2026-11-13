/**
 * Report presets — output policies applied at export time.
 *
 * A preset only toggles CLI flags that change how a report is rendered
 * (PDF footers, Bates stamps, the cover hash table). None of these flags
 * reaches matching, diffing, fingerprinting or the JSON metrics (traced in
 * cli.py -> pipeline.py), so switching presets cannot change a similarity
 * value. `analysisArgs()` lets tests assert exactly that.
 */
import { buildCoreArgs, DiffiniteOptions } from "./analysisModel";
import { countLabel, plural } from "./labels";
import { INTEGRITY_NOTICE } from "./notices";

export type ReportPresetId = "configured" | "technical" | "evidence";
export type ReportFormat = "pdf" | "html" | "md";

type OutputKey = "pageNumber" | "fileNumber" | "batesNumber" | "hash";

export interface ReportPreset {
  id: ReportPresetId;
  label: string;
  audience: string;
  /** Output flags this preset forces; empty means "use the Options panel values". */
  overrides: Partial<Record<OutputKey, boolean>>;
}

export const REPORT_PRESETS: readonly ReportPreset[] = [
  {
    id: "configured",
    label: "As configured (Options panel)",
    audience: "Uses the output options chosen before the analysis.",
    overrides: {},
  },
  {
    id: "technical",
    label: "Technical report",
    audience: "Developers and code reviewers: side-by-side diffs with page and file numbers, no Bates stamps.",
    overrides: { pageNumber: true, fileNumber: true, batesNumber: false, hash: false },
  },
  {
    id: "evidence",
    label: "Evidence report",
    audience: "Legal teams and experts: adds Bates numbers (PDF) and the SHA-256 table of input files.",
    overrides: { pageNumber: true, fileNumber: true, batesNumber: true, hash: true },
  },
];

/** Flags that only affect rendering. Removed by `analysisArgs()`. */
const OUTPUT_FLAGS_NO_VALUE = new Set(["--page-number", "--file-number", "--bates-number", "--hash"]);
const OUTPUT_FLAGS_WITH_VALUE = new Set(["--bates-prefix", "--bates-suffix", "--bates-start"]);
/** Same flags passed as one "--flag=value" argument. */
const OUTPUT_FLAG_ASSIGNMENT = /^--bates-(prefix|suffix|start)=/;

export function isReportPresetId(value: unknown): value is ReportPresetId {
  return REPORT_PRESETS.some((preset) => preset.id === value);
}

export function isReportFormat(value: unknown): value is ReportFormat {
  return value === "pdf" || value === "html" || value === "md";
}

export function getReportPreset(id: ReportPresetId): ReportPreset {
  const preset = REPORT_PRESETS.find((p) => p.id === id);
  if (!preset) { throw new Error(`Unknown report preset: ${String(id)}`); }
  return preset;
}

/** Return a copy of `options` with the preset's output flags applied. */
export function applyReportPreset(options: DiffiniteOptions, id: ReportPresetId): DiffiniteOptions {
  return { ...options, ...getReportPreset(id).overrides };
}

/** CLI arguments with every output-only flag removed: what decides the metrics. */
export function analysisArgs(options: DiffiniteOptions): string[] {
  const args = buildCoreArgs(options);
  const kept: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (OUTPUT_FLAGS_NO_VALUE.has(args[i]) || OUTPUT_FLAG_ASSIGNMENT.test(args[i])) { continue; }
    if (OUTPUT_FLAGS_WITH_VALUE.has(args[i])) { i++; continue; }
    kept.push(args[i]);
  }
  return kept;
}

/**
 * Plain-language list of what an export will contain, for the confirmation
 * area of the Result Viewer. Every line states what the CLI will do with the
 * given options and format; nothing here interprets the results.
 */
export function describeReportOutput(
  options: DiffiniteOptions,
  format: ReportFormat,
  scope: { selectedPairs: number | null },
): string[] {
  const lines: string[] = [];
  lines.push(scope.selectedPairs === null
    ? "Scope: every matched file pair from the analysis."
    : `Scope: the ${plural(scope.selectedPairs, "file pair")} selected in the Tree Viewer. ` +
      "The list of files only in B is omitted, and the list of files only in A shows only the selected A files; " +
      "the report states how many unmatched files it left out.");
  lines.push("The export re-runs the analysis on the source folders with the same settings and the exclusion list captured when the analysis started. It is published only if every input file still has the SHA-256 recorded for the results on screen; otherwise nothing is written. The preset changes only layout options, never analysis settings.");

  if (format === "pdf") {
    const included = (on: boolean): string => (on ? "included" : "not included");
    lines.push(`Page numbers: ${included(options.pageNumber)}. File numbers: ${included(options.fileNumber)}.`);
    if (options.batesNumber) {
      const prefix = options.batesPrefix || "none";
      const suffix = options.batesSuffix || "none";
      lines.push(`Bates numbers: included, with prefix ${prefix} and suffix ${suffix}, starting at ${countLabel(options.batesStart)}.`);
    } else {
      lines.push("Bates numbers: not included.");
    }
  } else {
    lines.push(`Page, file and Bates numbers: not applicable to ${format === "html" ? "HTML" : "Markdown"}.`);
  }
  lines.push(`SHA-256 table of input files: ${options.hash ? "included" : "not included"}.`);
  lines.push("An integrity manifest (<report file>.manifest.sha256.json) listing every input and output hash is always written.");
  lines.push(INTEGRITY_NOTICE);
  if (options.noMerge && format !== "md") {
    lines.push(`Layout: one ${format.toUpperCase()} per file in a <name>_files folder (No Merge is on).`);
  }
  return lines;
}
