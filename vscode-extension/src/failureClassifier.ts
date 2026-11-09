/**
 * Turn a failed analysis/export error into a short, actionable message.
 *
 * The CLI exits 1 for almost every failure and the only distinguishing
 * signal is the text it prints (exception type and message on the last
 * lines of stderr). The patterns below match messages that exist verbatim
 * in the Python source and runner.ts; anything else is reported as
 * "unknown" with the raw text kept for the details view.
 */

export type FailureKind =
  | "cancelled"
  | "cancelled-incomplete"
  | "runtime-missing"
  | "unreadable-input"
  | "partial-refused"
  | "pdf-failed"
  | "out-of-memory"
  | "invalid-argument"
  | "integrity"
  | "invalid-report"
  | "unknown";

export interface ClassifiedFailure {
  kind: FailureKind;
  title: string;
  action: string;
  /** The original error text, untouched, for the details view. */
  details: string;
}

interface Rule {
  kind: FailureKind;
  test: RegExp;
  title: string;
  action: string;
}

// Order matters: the first match wins. Cancellation is checked first because
// a cancelled run can also leave partial stderr from the killed process.
const RULES: readonly Rule[] = [
  {
    kind: "cancelled-incomplete",
    // runner.ts cancellationError() when the process tree could not be confirmed dead.
    test: /cancelled; the analyzer did not emit a close event|cancelled, but analyzer PID/,
    title: "Cancelled, but the analyzer may still be running",
    action: "Close the analyzer process (see details for its PID) with the operating system's process manager. " +
      "Output files may still change until it exits; check them before use.",
  },
  {
    kind: "cancelled",
    // runner.ts clean cancellation messages.
    test: /cancelled by user/,
    title: "Cancelled",
    action: "No report was written. Existing output files were left as they were.",
  },
  {
    kind: "runtime-missing",
    // runner.ts spawn error, or a Python without the diffinite package.
    // (A bare "ENOENT" is not enough: Node file errors while reading results carry it too.)
    test: /Failed to start diffinite|No module named '?diffinite/,
    title: "Diffinite runtime not found",
    action: "Check the diffinite.pythonPath setting, or install the package with: pip install -U diffinite",
  },
  {
    kind: "out-of-memory",
    // Python MemoryError (bare or inside a worker/PDF log line).
    test: /MemoryError/,
    title: "Out of memory",
    action: "Select fewer files, lower the worker count, or exclude very large files (.diffignore).",
  },
  {
    kind: "pdf-failed",
    // pipeline.py / pdf_gen.py PDF rendering failures.
    test: /PDF rendering failed|PDF conversion failed/,
    title: "PDF rendering failed",
    action: "The analysis itself finished. Try HTML export, select fewer files, or set a different PDF font.",
  },
  {
    kind: "unreadable-input",
    // pipeline.py collection/hashing refusals and per-file PermissionError.
    test: /Input collection was incomplete|Input hashing failed|PermissionError|Access Denied/,
    title: "Some input files could not be read",
    action: "Check file permissions or exclude the files (.diffignore). " +
      "\"Allow partial analysis\" produces a report marked incomplete instead.",
  },
  {
    kind: "partial-refused",
    // pipeline.py / deep_compare.py refusals without --allow-partial.
    test: /refusing a partial|worker\(s\) crashed|Deep Compare worker\/file failure|reached --max-index-entries/,
    title: "Analysis stopped: part of the comparison failed",
    action: "No partial result was reported. Re-run, lower the worker count, or enable \"Allow partial analysis\" " +
      "to get a report that is marked incomplete.",
  },
  {
    kind: "integrity",
    // evidence.py SourceIntegrityError (unsafe paths, links, unresolvable roots).
    test: /SourceIntegrityError/,
    title: "Source or output path rejected by integrity checks",
    action: "Check that both folders exist, are not links, and that the output is not inside a source folder.",
  },
  {
    kind: "invalid-argument",
    // argparse usage errors exit with code 2.
    test: /exited with code 2|failed \(code 2\)|diffinite: error:/,
    title: "An option value was rejected",
    action: "Check the values in the Options panel.",
  },
  {
    kind: "invalid-report",
    // runner.ts / analysisModel.ts JSON validation.
    test: /Failed to parse JSON report|Invalid live report/,
    title: "The analyzer's result could not be read",
    action: "The Python package and the extension may be different versions. Update both.",
  },
];

/**
 * The last "SomeError: message" line of a Python traceback names the
 * exception that actually stopped the run. Earlier WARNING log lines in the
 * same stderr tail can mention other problems (e.g. a skipped file), so the
 * final exception line is matched first.
 */
function finalExceptionLine(details: string): string | null {
  const matches = details.match(/^[\w.]*(?:Error|Exception|Interrupt)\b.*$/gm);
  return matches ? matches[matches.length - 1] : null;
}

export function classifyFailure(error: unknown): ClassifiedFailure {
  const details = error instanceof Error ? error.message : String(error);
  // With a traceback, only its final exception line decides: earlier log
  // lines may mention unrelated problems. Without one, use the whole text.
  const finalLine = finalExceptionLine(details);
  const candidates = finalLine !== null ? [finalLine] : [details];
  for (const candidate of candidates) {
    for (const rule of RULES) {
      if (rule.test.test(candidate)) {
        return { kind: rule.kind, title: rule.title, action: rule.action, details };
      }
    }
  }
  return {
    kind: "unknown",
    title: "Unexpected error",
    action: "Open the details to see the analyzer output.",
    details,
  };
}
