"""Diffinite CLI 진입점.

``diffinite`` 콘솔 커맨드의 인자 파싱 및 파이프라인 오케스트레이션.
``argparse`` 기반 CLI로, ``pipeline.run_pipeline()``을 호출한다.

의존:
    - ``pipeline.py``: 실제 분석 실행
    - ``models.AnalysisMetadata``: 보고서 재현성 메타데이터

호출관계:
    ``diffinite`` console_script -> ``main(argv)`` -> ``pipeline.run_pipeline()``
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
    format_group.add_argument(
        "--report-json",
        metavar="PATH",
        default=None,
        help="Generate a JSON report at the given path (for programmatic use)",
    )

    # ── Deep compare options ──────────────────────────────────────────
    deep_group = parser.add_argument_group(
        "Deep Compare",
        "Winnowing-based N:M cross-matching options (only active in "
        "'--mode deep').",
    )
    deep_group.add_argument(
        "--k-gram", "--kgram-size",
        type=int,
        default=DEFAULT_K,
        dest="k_gram",
        help=(
            f"K-gram token window size (default: {DEFAULT_K}). "
            "Schleimer 2003, §4.2."
        ),
    )
    deep_group.add_argument(
        "--window", "--window-size",
        type=int,
        default=DEFAULT_W,
        dest="window",
        help=(
            f"Winnowing window size (default: {DEFAULT_W}). "
            "Density guarantee: >=(W+K-1) shared tokens always detected."
        ),
    )
    deep_group.add_argument(
        "--threshold-deep", "--min-jaccard",
        type=float,
        default=0.05,
        dest="threshold_deep",
        help=(
            "Minimum Jaccard similarity to report (default: 0.05). "
            "Below 5%% is considered noise."
        ),
    )
    deep_group.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel worker processes for fingerprint extraction (default: 4)",
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

    # ── Forensic options ──────────────────────────────────────────────
    forensic_group = parser.add_argument_group(
        "Forensic",
        "Options for forensic precision analysis.",
    )
    forensic_group.add_argument(
        "--no-autojunk",
        action="store_true",
        default=False,
        help=(
            "Disable SequenceMatcher's autojunk heuristic. "
            "All tokens are treated equally — slower but more precise "
            "for forensic analysis."
        ),
    )
    forensic_group.add_argument(
        "--max-index-entries",
        type=int,
        default=10_000_000,
        dest="max_index_entries",
        help=(
            "Maximum entries in the inverted index for Deep Compare. "
            "Prevents OOM on massive corpora (default: 10,000,000)."
        ),
    )
    forensic_group.add_argument(
        "--hash",
        action="store_true",
        default=False,
        dest="embed_hash",
        help=(
            "Embed SHA-256 hash table in PDF/HTML report cover page. "
            "A manifest.sha256.json is always generated regardless of this flag."
        ),
    )
    forensic_group.add_argument(
        "--bundle",
        metavar="PATH",
        default=None,
        dest="bundle_path",
        help=(
            "Create evidence bundle zip at PATH. Includes source files, "
            "generated reports, and integrity manifest."
        ),
    )

    args = parser.parse_args(argv)

    # Build analysis metadata (embedded in every report for transparency)
    metadata = AnalysisMetadata(
        exec_mode=args.mode,
        k=args.k_gram,
        w=args.window,
        threshold=args.threshold_deep,
        autojunk=not args.no_autojunk,
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
        kgram_size=args.k_gram,
        window_size=args.window,
        min_jaccard=args.threshold_deep,
        normalize=args.normalize,
        metadata=metadata,
        # Forensic options
        autojunk=not args.no_autojunk,
        max_index_entries=args.max_index_entries,
        # Evidence integrity
        embed_hash=args.embed_hash,
        bundle_path=args.bundle_path,
        # Multi-format output
        report_pdf=args.report_pdf,
        report_html=args.report_html,
        report_md=args.report_md,
        report_json=args.report_json,
    )


if __name__ == "__main__":
    main()
