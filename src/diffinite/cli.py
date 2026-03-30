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

    # ── Comparison options ────────────────────────────────────────────
    parser.add_argument(
        "--by-word",
        action="store_true",
        default=False,
        help="Compare by word instead of by line",
    )
    parser.add_argument(
        "--normalize-whitespace",
        action="store_true",
        default=False,
        help=(
            "Normalize whitespace before comparison: replace tabs with spaces "
            "and collapse multiple consecutive spaces into one. "
            "Useful when tab-vs-space indentation differences cause "
            "block misalignment in word comparison."
        ),
    )
    parser.add_argument(
        "--strip-comments",
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
            "Only effective with --strip-comments. WARNING: changes line "
            "numbers — do not use for forensic line-tracing."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=FUZZY_THRESHOLD,
        help=f"Fuzzy matching threshold 0–100 (default: {FUZZY_THRESHOLD})",
    )
    parser.add_argument(
        "--encoding",
        default="auto",
        help=(
            "Source file encoding. 'auto' (default) uses charset-normalizer "
            "auto-detection with Korean-optimized fallback (utf-8 -> euc-kr -> cp949). "
            "Specify an explicit encoding (e.g. euc-kr, utf-8, cp949, shift_jis, "
            "gb2312) to force-decode all files with that encoding."
        ),
    )
    parser.add_argument(
        "--sort-by",
        choices=["filename", "path", "similarity", "ratio"],
        default=None,
        dest="sort_by",
        help=(
            "Sort matched file pairs in the report. "
            "'filename' sorts by file basename, 'path' by full path, "
            "'similarity' by name match score, 'ratio' by content "
            "similarity. Default: insertion order (no sort)."
        ),
    )
    parser.add_argument(
        "--sort-order",
        choices=["asc", "desc"],
        default="asc",
        dest="sort_order",
        help="Sort direction (default: asc). Only effective with --sort-by.",
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
        "--bates-prefix",
        type=str,
        default="",
        help=(
            "Bates number prefix (e.g. 'PLAINTIFF-'). "
            "Combined as: {prefix}{number}{suffix}"
        ),
    )
    parser.add_argument(
        "--bates-suffix",
        type=str,
        default="",
        help=(
            "Bates number suffix (e.g. '-CONFIDENTIAL'). "
            "Combined as: {prefix}{number}{suffix}"
        ),
    )
    parser.add_argument(
        "--bates-start",
        type=int,
        default=1,
        help=(
            "Starting Bates number (default: 1). "
            "Useful for continuing numbering across multiple reports."
        ),
    )
    parser.add_argument(
        "--filename",
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
    parser.add_argument(
        "--detect-moved",
        action="store_true",
        default=False,
        help=(
            "Detect moved code blocks and highlight them with distinct colors "
            "(purple=original position, blue=moved position) instead of "
            "plain delete/add. Works in both simple and deep modes."
        ),
    )
    parser.add_argument(
        "--uncompared-files",
        choices=["inline", "separate", "none"],
        default="inline",
        dest="uncompared_files",
        help=(
            "How to handle the uncompared file list: "
            "'inline' (default) embeds it in the report body, "
            "'separate' saves it as a standalone text file, "
            "'none' omits it entirely."
        ),
    )
    parser.add_argument(
        "--binary-handling",
        choices=["exclude", "hash", "error"],
        default="hash",
        dest="binary_handling",
        help=(
            "How to handle binary (non-decodable) files: "
            "'exclude' skips them entirely, 'hash' shows SHA-256 match "
            "status, 'error' shows decode error (default: hash)."
        ),
    )
    parser.add_argument(
        "--ignore-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to a .diffignore text file containing glob patterns "
            "(e.g. node_modules, *.pyc) to completely exclude from analysis."
        ),
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Phase 1: Compute similarities and output JSON but skip HTML rendering and PDF generation.",
    )
    parser.add_argument(
        "--filter-json",
        metavar="PATH",
        default=None,
        help="Phase 2: Path to a JSON array of specific file A paths to restrict the output to.",
    )
    parser.add_argument(
        "--unreadable-log",
        metavar="PATH",
        default=None,
        help="Path to save the list of completely unreadable files (Permission errors).",
    )
    # 10.0MB is roughly 10M chars; difflib's O(N^2) complexity on >10MB causes OOM/CPU lock.
    parser.add_argument(
        "--max-file-size",
        type=float,
        default=10.0,
        help="Maximum file size in MB. Files larger than this will bypass memory decode and fall back to hash comparison (default: 10.0 MB).",
    )
    parser.add_argument(
        "--dir-alias-a",
        metavar="ALIAS",
        default=None,
        help="Alias for Directory A to display in reports (prevents absolute path exposure).",
    )
    parser.add_argument(
        "--dir-alias-b",
        metavar="ALIAS",
        default=None,
        help="Alias for Directory B to display in reports.",
    )

    # ── Output control ────────────────────────────────────────────────
    # 4 is the standard optimal default for CPU-bound tasks on modern 4+ core consumer hardware to avoid heavy context switching.
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel CPU workers for rendering (default: 4).",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        dest="no_merge",
        help=(
            "Save individual report files instead of merging into a "
            "single document. Creates a directory with per-file outputs."
        ),
    )
    parser.add_argument(
        "--preserve-tree",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="preserve_tree",
        help=(
            "When --no-merge is active, preserve the original directory "
            "tree structure in the output. Use --no-preserve-tree to "
            "flatten all files into the output root with an index.html."
        ),
    )

    # ── Report format options ─────────────────────────────────────────
    format_group = parser.add_argument_group(
        "Report Format",
        "Output format(s). Multiple can be combined. "
        "If none specified, defaults to PDF (report.pdf).",
    )
    format_group.add_argument(
        "--report-pdf", "-o",
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
    format_group.add_argument(
        "--pdf-font",
        metavar="PATH",
        default=None,
        dest="pdf_font",
        help=(
            "Absolute path to a .ttf/.otf font file for PDF text rendering. "
            "When specified, the font is embedded via @font-face and used as "
            "the primary typeface. When omitted, the built-in xhtml2pdf CJK "
            "font (HYGothic-Medium) is used as fallback."
        ),
    )
    format_group.add_argument(
        "--pdf-lang",
        metavar="LANG_CODE",
        default=None,
        dest="pdf_lang",
        help=(
            "Major language code (e.g. 'ko', 'ja', 'zh-cn') to automatically "
            "resolve the best OS-specific font from pdf_fonts.json. "
            "Ignored if --pdf-font is explicitly provided."
        ),
    )

    # ── Deep compare options ──────────────────────────────────────────
    deep_group = parser.add_argument_group(
        "Deep Compare",
        "Winnowing-based N:M cross-matching options (only active in "
        "'--mode deep').",
    )
    deep_group.add_argument(
        "--k-gram",
        type=int,
        default=DEFAULT_K,
        dest="k_gram",
        help=(
            f"K-gram token window size (default: {DEFAULT_K}). "
            "Schleimer 2003, §4.2."
        ),
    )
    deep_group.add_argument(
        "--window",
        type=int,
        default=DEFAULT_W,
        dest="window",
        help=(
            f"Winnowing window size (default: {DEFAULT_W}). "
            "Density guarantee: >=(W+K-1) shared tokens always detected."
        ),
    )
    deep_group.add_argument(
        "--threshold-deep",
        type=float,
        default=5,
        dest="threshold_deep",
        help=(
            "Minimum Jaccard similarity 0–100 to report (default: 5). "
            "Below 5%% is considered noise."
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

    # Convert threshold-deep from 0-100 (user-facing) to 0-1 (internal)
    min_jaccard_internal = args.threshold_deep / 100.0

    # Build analysis metadata (embedded in every report for transparency)
    metadata = AnalysisMetadata(
        exec_mode=args.mode,
        k=args.k_gram,
        w=args.window,
        threshold=args.threshold_deep,  # 0-100 scale in metadata
        autojunk=not args.no_autojunk,
    )

    # Resolve encoding
    encoding = args.encoding if args.encoding.lower() != "auto" else None

    # Resolve default PDF output if no --report-* specified
    report_pdf = args.report_pdf
    if report_pdf is None and args.report_html is None and args.report_md is None and args.report_json is None:
        report_pdf = "report.pdf"

    run_pipeline(
        dir_a=args.dir_a,
        dir_b=args.dir_b,
        by_word=args.by_word,
        strip_comments=args.strip_comments,
        squash_blanks=args.squash_blanks,
        threshold=args.threshold,
        no_merge=args.no_merge,
        show_page_number=args.page_number,
        show_file_number=args.file_number,
        show_bates_number=args.bates_number,
        show_filename=args.filename,
        collapse_identical=args.collapse_identical,
        # Execution mode & deep compare
        exec_mode=args.mode,
        workers=args.workers,
        kgram_size=args.k_gram,
        window_size=args.window,
        min_jaccard=min_jaccard_internal,
        normalize=args.normalize,
        metadata=metadata,
        # Forensic options
        autojunk=not args.no_autojunk,
        max_index_entries=args.max_index_entries,
        # Evidence integrity
        embed_hash=args.embed_hash,
        bundle_path=args.bundle_path,
        # Multi-format output
        report_pdf=report_pdf,
        report_html=args.report_html,
        report_md=args.report_md,
        report_json=args.report_json,
        # Encoding
        encoding=encoding,
        # Sorting
        sort_by=args.sort_by,
        sort_order=args.sort_order,
        # Moved block detection
        detect_moved=args.detect_moved,
        # Uncompared files
        uncompared_mode=args.uncompared_files,
        # Bates prefix/suffix
        bates_prefix=args.bates_prefix,
        bates_suffix=args.bates_suffix,
        bates_start=args.bates_start,
        # Binary handling
        binary_handling=args.binary_handling,
        # Ignore list
        ignore_file=getattr(args, "ignore_file", None),
        # Phase 1/2 Architecture
        metrics_only=getattr(args, "metrics_only", False),
        filter_json=getattr(args, "filter_json", None),
        # Stability & Forensics
        unreadable_log=getattr(args, "unreadable_log", None),
        max_file_size_mb=getattr(args, "max_file_size", 10.0),
        dir_alias_a=getattr(args, "dir_alias_a", None),
        dir_alias_b=getattr(args, "dir_alias_b", None),
        # Individual output
        preserve_tree=args.preserve_tree,
        # Whitespace normalization
        normalize_ws=args.normalize_whitespace,
        # PDF font
        pdf_font=getattr(args, "pdf_font", None),
        pdf_lang=getattr(args, "pdf_lang", None),
    )


if __name__ == "__main__":
    main()
