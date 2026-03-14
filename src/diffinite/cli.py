"""CLI entry point for Diffinite.

Provides the ``diffinite`` console command via ``argparse``.

Execution Modes
===============
- ``--mode simple`` : 1:1 file matching only (fast, no Winnowing).
- ``--mode deep``   : 1:1 + N:M Winnowing cross-matching (default).

Parameter 3-Tier System (Deep mode)
====================================
- Tier 1 — **Profile** (``--profile``): preset K/W/T values.
- Tier 2 — **Manual Override** (``--k-gram``, ``--window``, ``--threshold-deep``):
  expert knobs that override the profile.
- Tier 3 — **Grid Search** (``--grid-search``): sensitivity sweep over K×W
  combinations, output a Jaccard robustness matrix.
"""

from __future__ import annotations

import argparse
import logging
import sys

from diffinite.collector import FUZZY_THRESHOLD
from diffinite.fingerprint import DEFAULT_K, DEFAULT_W
from diffinite.models import AnalysisMetadata
from diffinite.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ---------------------------------------------------------------------------
# Profile presets (Tier 1)
# ---------------------------------------------------------------------------
PROFILES: dict[str, dict[str, int | float]] = {
    "industrial": {"k": 5, "w": 4, "t": 0.10},
    "academic":   {"k": 2, "w": 3, "t": 0.40},
}

# Sentinel value used to detect whether the user explicitly set --k-gram etc.
_SENTINEL = -1.0


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        prog="diffinite",
        description=(
            "Diffinite — Forensic source-code diff tool.\n"
            "Compare two directories and generate a syntax-highlighted report "
            "with optional N:M deep cross-matching.\n\n"
            "Modes:\n"
            "  simple  Fast 1:1 file matching only.\n"
            "  deep    1:1 + N:M Winnowing cross-matching (default)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Positional
    parser.add_argument("dir_a", help="Path to the original source directory (A)")
    parser.add_argument("dir_b", help="Path to the comparison source directory (B)")

    # ── Execution mode ────────────────────────────────────────────────
    parser.add_argument(
        "--mode",
        choices=["simple", "deep"],
        default="deep",
        help=(
            "Execution mode: 'simple' performs 1:1 file matching only; "
            "'deep' (default) adds N:M Winnowing cross-matching."
        ),
    )

    # ── Output ────────────────────────────────────────────────────────
    parser.add_argument(
        "--output-pdf", "-o",
        default="report.pdf",
        help="Output PDF file path (default: report.pdf). "
             "Ignored when any --report-* option is specified.",
    )

    # ── Comparison options ────────────────────────────────────────────
    parser.add_argument(
        "--by-word",
        action="store_true",
        default=False,
        help="Compare by word instead of by line",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        default=False,
        help="Strip comments before comparison (uses 2-pass parser)",
    )
    parser.add_argument(
        "--squash-blanks",
        action="store_true",
        default=False,
        help=(
            "Collapse runs of 3+ blank lines after comment stripping. "
            "Only effective with --no-comments. WARNING: changes line "
            "numbers — do not use for forensic line-tracing."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=FUZZY_THRESHOLD,
        help=f"Fuzzy matching threshold 0–100 (default: {FUZZY_THRESHOLD})",
    )

    # ── Output modes ──────────────────────────────────────────────────
    parser.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        help="Generate individual PDFs per file instead of one merged PDF",
    )

    # ── Annotations ───────────────────────────────────────────────────
    parser.add_argument(
        "--page-number",
        action="store_true",
        default=False,
        help="Show 'Page n / N' at the bottom-right of each page",
    )
    parser.add_argument(
        "--file-number",
        action="store_true",
        default=False,
        help="Show 'File n / N' at the bottom-left of each page",
    )
    parser.add_argument(
        "--bates-number",
        action="store_true",
        default=False,
        help="Stamp Bates numbers at the bottom-center of each page",
    )
    parser.add_argument(
        "--show-filename",
        action="store_true",
        default=False,
        help="Show the filename at the top-right of each page",
    )
    parser.add_argument(
        "--collapse-identical",
        action="store_true",
        default=False,
        help=(
            "Collapse unchanged code blocks into a summary row "
            "(shows 3 context lines around each change). "
            "Without this flag, the full diff is shown."
        ),
    )

    # ── Report format options ─────────────────────────────────────────
    format_group = parser.add_argument_group(
        "Report Format",
        "Output format(s). Multiple can be combined. "
        "If none specified, defaults to --output-pdf.",
    )
    format_group.add_argument(
        "--report-pdf",
        metavar="PATH",
        default=None,
        help="Generate a merged PDF report at the given path",
    )
    format_group.add_argument(
        "--report-html",
        metavar="PATH",
        default=None,
        help="Generate a standalone HTML report at the given path",
    )
    format_group.add_argument(
        "--report-md",
        metavar="PATH",
        default=None,
        help="Generate a Markdown summary report at the given path",
    )

    # ── Deep compare options (3-Tier parameter system) ────────────────
    deep_group = parser.add_argument_group(
        "Deep Compare",
        "Winnowing-based N:M cross-matching options (only active in "
        "'--mode deep').\n\n"
        "Tier 1 — Profile: preset K/W/T via --profile.\n"
        "Tier 2 — Manual Override: --k-gram, --window, --threshold-deep.\n"
        "Tier 3 — Grid Search: --grid-search sweeps K×W combinations.",
    )
    deep_group.add_argument(
        "--profile",
        choices=["industrial", "academic"],
        default="industrial",
        help=(
            "Detection profile (Tier 1). "
            "'industrial' (default): K=5, W=4, T=0.10 (substantial similarity). "
            "'academic': K=2, W=3, T=0.40 (strict snippet detection)."
        ),
    )
    deep_group.add_argument(
        "--k-gram", "--kgram-size",
        type=int,
        default=None,
        dest="k_gram",
        help=(
            "K-gram token window size (Tier 2 override). "
            "Overrides the profile default."
        ),
    )
    deep_group.add_argument(
        "--window", "--window-size",
        type=int,
        default=None,
        dest="window",
        help=(
            "Winnowing window size (Tier 2 override). "
            "Overrides the profile default."
        ),
    )
    deep_group.add_argument(
        "--threshold-deep", "--min-jaccard",
        type=float,
        default=None,
        dest="threshold_deep",
        help=(
            "Minimum Jaccard similarity to report (Tier 2 override). "
            "Overrides the profile default."
        ),
    )
    deep_group.add_argument(
        "--grid-search",
        action="store_true",
        default=False,
        help=(
            "Enable parameter sensitivity analysis (Tier 3). "
            "Sweeps K=[2..7] × W=[2..6] and outputs a Jaccard "
            "robustness matrix. Only active in '--mode deep'."
        ),
    )
    deep_group.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel worker processes for fingerprint extraction (default: 4)",
    )
    deep_group.add_argument(
        "--tokenizer",
        choices=["token", "ast", "pdg"],
        default="token",
        help=(
            "Fingerprint tokenisation strategy: "
            "'token' (Phase 1 flat tokens, default), "
            "'ast' (Phase 2 tree-sitter AST linearization), "
            "'pdg' (Phase 4 PDG normalization). "
            "Falls back to 'token' when tree-sitter is unavailable."
        ),
    )
    deep_group.add_argument(
        "--normalize",
        action="store_true",
        default=False,
        help=(
            "Normalize identifiers to ID and literals to LIT before "
            "fingerprinting (improves Type-2 clone detection)"
        ),
    )
    deep_group.add_argument(
        "--multi-channel",
        action="store_true",
        default=False,
        help=(
            "Enable multi-evidence channel analysis: raw/normalised/AST "
            "Winnowing, identifier cosine similarity, comment/string overlap. "
            "Produces a comprehensive evidence matrix in the report."
        ),
    )

    args = parser.parse_args(argv)

    # ── Tier cascade: resolve K, W, T ─────────────────────────────────
    profile_vals = PROFILES[args.profile]
    resolved_k = args.k_gram if args.k_gram is not None else int(profile_vals["k"])
    resolved_w = args.window if args.window is not None else int(profile_vals["w"])
    resolved_t = args.threshold_deep if args.threshold_deep is not None else float(profile_vals["t"])

    # Build analysis metadata (embedded in every report for transparency)
    metadata = AnalysisMetadata(
        exec_mode=args.mode,
        profile=args.profile,
        k=resolved_k,
        w=resolved_w,
        threshold=resolved_t,
        tokenizer=args.tokenizer,
        grid_search=args.grid_search,
    )

    run_pipeline(
        dir_a=args.dir_a,
        dir_b=args.dir_b,
        by_word=args.by_word,
        compare_comment=not args.no_comments,
        squash_blanks=args.squash_blanks,
        output_pdf=args.output_pdf,
        threshold=args.threshold,
        no_merge=args.no_merge,
        show_page_number=args.page_number,
        show_file_number=args.file_number,
        show_bates_number=args.bates_number,
        show_filename=args.show_filename,
        collapse_identical=args.collapse_identical,
        # Execution mode & deep compare
        exec_mode=args.mode,
        workers=args.workers,
        kgram_size=resolved_k,
        window_size=resolved_w,
        min_jaccard=resolved_t,
        normalize=args.normalize,
        tokenizer=args.tokenizer,
        multi_channel=args.multi_channel,
        profile=args.profile,
        grid_search=args.grid_search,
        metadata=metadata,
        # Multi-format output
        report_pdf=args.report_pdf,
        report_html=args.report_html,
        report_md=args.report_md,
    )


if __name__ == "__main__":
    main()
