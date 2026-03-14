"""CLI entry point for Diffinite.

Provides the ``diffinite`` console command via ``argparse``.
"""

from __future__ import annotations

import argparse
import logging
import sys

from diffinite.collector import FUZZY_THRESHOLD
from diffinite.fingerprint import DEFAULT_K, DEFAULT_W
from diffinite.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        prog="diffinite",
        description=(
            "Diffinite — Forensic source-code diff tool.\n"
            "Compare two directories and generate a syntax-highlighted PDF report "
            "with optional N:M deep cross-matching."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Positional
    parser.add_argument("dir_a", help="Path to the original source directory (A)")
    parser.add_argument("dir_b", help="Path to the comparison source directory (B)")

    # Output
    parser.add_argument(
        "--output-pdf", "-o",
        default="report.pdf",
        help="Output PDF file path (default: report.pdf). "
             "Ignored when any --report-* option is specified.",
    )

    # Comparison options
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

    # Output modes
    parser.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        help="Generate individual PDFs per file instead of one merged PDF",
    )

    # Annotations
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

    # Report format options
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

    # Deep compare options
    deep_group = parser.add_argument_group(
        "Deep Compare",
        "Winnowing-based N:M cross-matching options",
    )
    deep_group.add_argument(
        "--deep",
        action="store_true",
        default=False,
        help="Enable N:M deep cross-matching via Winnowing fingerprinting",
    )
    deep_group.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel worker processes for fingerprint extraction (default: 4)",
    )
    deep_group.add_argument(
        "--kgram-size",
        type=int,
        default=DEFAULT_K,
        help=f"K-gram token window size (default: {DEFAULT_K})",
    )
    deep_group.add_argument(
        "--window-size",
        type=int,
        default=DEFAULT_W,
        help=f"Winnowing window size (default: {DEFAULT_W})",
    )
    deep_group.add_argument(
        "--min-jaccard",
        type=float,
        default=0.05,
        help="Minimum Jaccard similarity to report (default: 0.05)",
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
        "--mode",
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
        "--multi-channel",
        action="store_true",
        default=False,
        help=(
            "Enable multi-evidence channel analysis: raw/normalised/AST "
            "Winnowing, identifier cosine similarity, comment/string overlap. "
            "Produces a comprehensive evidence matrix in the report."
        ),
    )
    deep_group.add_argument(
        "--profile",
        choices=["industrial", "academic"],
        default="industrial",
        help=(
            "Detection profile: 'industrial' uses defaults tuned for "
            "large-scale codebases (K=5, W=4); 'academic' uses parameters "
            "optimised for short student submissions (K=2, W=3, higher "
            "threshold). Default: industrial."
        ),
    )

    args = parser.parse_args(argv)

    # Academic profile overrides
    kgram_size = args.kgram_size
    window_size = args.window_size
    min_jaccard = args.min_jaccard
    if args.profile == "academic":
        # Only override if user hasn't explicitly set values
        if args.kgram_size == DEFAULT_K:
            kgram_size = 2
        if args.window_size == DEFAULT_W:
            window_size = 3
        if args.min_jaccard == 0.05:
            min_jaccard = 0.40

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
        deep=args.deep,
        workers=args.workers,
        kgram_size=kgram_size,
        window_size=window_size,
        min_jaccard=min_jaccard,
        normalize=args.normalize,
        mode=args.mode,
        multi_channel=args.multi_channel,
        collapse_identical=args.collapse_identical,
        profile=args.profile,
        report_pdf=args.report_pdf,
        report_html=args.report_html,
        report_md=args.report_md,
    )


if __name__ == "__main__":
    main()
