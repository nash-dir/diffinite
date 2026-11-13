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
import math
import sys

from diffinite.calibration import (
    NORMALIZE_CALIBRATION_K,
    NORMALIZE_CALIBRATION_W,
    NORMALIZE_DEFAULT_THRESHOLD,
    RAW_LEGACY_THRESHOLD,
    assess_normalize_calibration,
    resolve_threshold_deep,
    threshold_console_warning,
)
from diffinite.collector import FUZZY_THRESHOLD
from diffinite.fingerprint import DEFAULT_K, DEFAULT_W
from diffinite.models import AnalysisMetadata
from diffinite.pdf_gen import PdfFontError, bates_font_for, register_pdf_font
from diffinite.pipeline import run_pipeline

# CPython concurrent.futures.process._MAX_WINDOWS_WORKERS = 63 - 2: Windows
# WaitForMultipleObjects waits on at most 64 handles, and the pool uses 3.
_MAX_WINDOWS_WORKERS = 61
# --max-file-size is in MiB and becomes int(MB * 1024 * 1024) bytes downstream.
_BYTES_PER_MB = 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _resolve_threshold_deep(threshold_deep: float | None, normalize: bool) -> tuple[float, str]:
    """Resolve the deep Jaccard threshold and record its provenance.

    The raw and normalize channels have different false-positive profiles, so a
    normalize run left at the historical raw 5% has a measured ~100% false-positive
    rate on independent code. When the user did not pass --threshold-deep, the
    normalize channel substitutes the ratified normalize default; otherwise the
    explicit value wins. Returns ``(value_0_100, provenance)`` where provenance is
    one of ``"user" | "legacy-uncalibrated" | "normalize-default"``.
    """
    return resolve_threshold_deep(threshold_deep, normalize)


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and run the pipeline."""
    # Console output must never crash on non-ASCII. Report content is written to
    # UTF-8 files separately; this guards stdout/stderr (argparse --help, progress
    # logs that echo non-ASCII file names, error messages) on legacy Windows code
    # pages (e.g. cp1252) where such characters are unencodable. errors="replace"
    # degrades to '?' rather than raising UnicodeEncodeError.
    for _stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(_stream, "reconfigure")
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # captured/replaced streams (e.g. pytest) lack reconfigure

    parser = argparse.ArgumentParser(
        prog="diffinite",
        description=(
            "Diffinite: forensic source-code comparison tool.\n"
            "Compare two directories and generate a syntax-highlighted report, "
            "optionally with Deep Compare, which compares every file in A with "
            "every file in B.\n\n"
            "Modes:\n"
            "  simple  Pairs files by name and compares each pair.\n"
            "  deep    Also runs Deep Compare (default)."
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
            "Execution mode: 'simple' compares the file pairs matched by name only; "
            "'deep' (default) adds Deep Compare, which compares every file in A "
            "with every file in B using Winnowing fingerprints."
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
        help=(
            "Strip comments before comparison (uses 2-pass parser). Files whose "
            "extension has no registered comment syntax (e.g. .gradle, .vue) are "
            "compared with their comments; the report names those extensions."
        ),
    )
    parser.add_argument(
        "--squash-blanks",
        action="store_true",
        default=False,
        help=(
            "Collapse runs of 3+ blank lines after comment stripping. "
            "Only effective with --strip-comments. Warning: this changes line "
            "numbers, so do not use it when line numbers must match the source."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=FUZZY_THRESHOLD,
        help=f"Fuzzy file-name matching threshold, 0 to 100 (default: {FUZZY_THRESHOLD})",
    )
    parser.add_argument(
        "--encoding",
        default="auto",
        help=(
            "Source file encoding. 'auto' (default) uses charset-normalizer "
            "auto-detection, falling back to utf-8, then euc-kr, then cp949. "
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
            "'similarity' by name similarity, 'ratio' by line match (word match "
            "with --by-word); pairs compared by SHA-256 only or not compared follow "
            "in their existing order. Default: collection order (no sort)."
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
        help=(
            "Show 'Page n of N' at the bottom right. Pages are counted separately "
            "for the cover section and for each file pair. Use --bates-number for "
            "page identifiers that are unique across the report."
        ),
    )
    parser.add_argument(
        "--file-number",
        action="store_true",
        default=False,
        help="Show 'File n of N' at the bottom left of each page",
    )
    parser.add_argument(
        "--bates-number",
        action="store_true",
        default=False,
        help="Stamp Bates numbers at the bottom center of each page",
    )
    parser.add_argument(
        "--bates-prefix",
        type=str,
        default="",
        help=(
            "Bates number prefix (e.g. 'PLAINTIFF-'). Combined as: "
            "{prefix}{number}{suffix}. Latin (Windows-1252) characters and Hangul only."
        ),
    )
    parser.add_argument(
        "--bates-suffix",
        type=str,
        default="",
        help=(
            "Bates number suffix (e.g. '-CONFIDENTIAL'). Combined as: "
            "{prefix}{number}{suffix}. Latin (Windows-1252) characters and Hangul only."
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
        help="Show the path of File A at the top of each diff page",
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
            "(purple for the original position, blue for the moved position) instead of "
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
            "'exclude' leaves the pair uncompared and lists it in the report as "
            "excluded, 'hash' shows SHA-256 match status, 'error' records a decode "
            "error and counts the pair as failed (default: hash). Unreadable files "
            "are never excluded, and pairs over --max-file-size are always "
            "compared by SHA-256 only."
        ),
    )
    parser.add_argument(
        "--ignore-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to a .diffignore text file containing glob patterns "
            "(e.g. node_modules, *.pyc) to completely exclude from analysis. "
            "Every excluded file or directory is listed in the reports (see --uncompared-files)."
        ),
    )
    parser.add_argument(
        "--include",
        metavar="PATTERN",
        action="append",
        default=None,
        dest="include_patterns",
        help=(
            "Collect only files matching PATTERN (same syntax as the ignore file; "
            "repeatable, e.g. --include '*.java' --include 'src/**'). Applied "
            "during collection, so it also limits hashing and the evidence "
            "bundle. Every file left out is listed in the reports (see --uncompared-files)."
        ),
    )
    parser.add_argument(
        "--sensitive-files",
        choices=["exclude", "include", "error"],
        default="exclude",
        dest="sensitive_files",
        help=(
            "Files that usually hold secrets (.env, private keys, credential "
            "files; matched by name, ignoring case): 'exclude' (default) leaves "
            "them out and discloses their paths in the reports, 'include' compares "
            "them like any other file, 'error' stops before writing anything "
            "when one is found."
        ),
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help=(
            "Compute similarities and write only the JSON report; the Markdown, "
            "HTML and PDF reports are not produced."
        ),
    )
    parser.add_argument(
        "--filter-json",
        metavar="PATH",
        default=None,
        help=(
            "Path to a JSON array of File A paths. The reports cover only the "
            "matched pairs whose File A is listed."
        ),
    )
    parser.add_argument(
        "--unreadable-log",
        metavar="PATH",
        default=None,
        help="Path to save the list of files that could not be read (for example, permission errors).",
    )
    # 10.0MB is roughly 10M chars; difflib's O(N^2) complexity on >10MB causes OOM/CPU lock.
    parser.add_argument(
        "--max-file-size",
        type=float,
        default=10.0,
        help=(
            "Maximum file size in MB. Oversized pairs use SHA-256 in the line "
            "channel and are omitted from Deep Compare; the deep omission fails "
            "closed unless --allow-partial is set (default: 10.0 MB)."
        ),
    )
    # 2MB HTML is roughly ~100k DOM nodes. xhtml2pdf's html5lib parser is written in pure Python
    # and recursive traversing hits RecursionError or extreme GC pauses beyond this point.
    parser.add_argument(
        "--max-diff-html-size",
        type=float,
        default=2.0,
        dest="max_diff_html_size",
        help=(
            "Maximum size in MB of one side-by-side diff before it is left out of "
            "the HTML and PDF reports and replaced by a note (default: 2.0). Keeps "
            "PDF generation within memory limits."
        ),
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
        "Output formats. Several can be combined. "
        "If none specified, defaults to PDF (report.pdf).",
    )
    format_group.add_argument(
        "--report-pdf",
        "-o",
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
            "Path to a TrueType font file (.ttf/.ttc) for CJK text in PDF reports. "
            "The font is embedded and used for CJK runs; other text keeps the "
            "default faces. A missing or unloadable font is an error. When "
            "omitted, the built-in PDF CJK font (HYGothic-Medium) is used."
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
        "Options for Deep Compare, which compares every file in A with every file "
        "in B using Winnowing fingerprints (only with '--mode deep').",
    )
    deep_group.add_argument(
        "--k-gram",
        type=int,
        default=DEFAULT_K,
        dest="k_gram",
        help=(
            f"K-gram token window size (default: {DEFAULT_K}; the value frozen in "
            "the measured normalize calibration profile)."
        ),
    )
    deep_group.add_argument(
        "--window",
        type=int,
        default=DEFAULT_W,
        dest="window",
        help=(
            f"Winnowing window size (default: {DEFAULT_W}). "
            "Shared runs of >=(W+K-1) tokens always share a fingerprint; "
            "whether the pair is reported depends on --threshold-deep."
        ),
    )
    deep_group.add_argument(
        "--threshold-deep",
        type=float,
        default=None,
        dest="threshold_deep",
        help=(
            f"Minimum Jaccard similarity to report, 0 to 100. Default: {RAW_LEGACY_THRESHOLD:g} "
            f"(raw), or {NORMALIZE_DEFAULT_THRESHOLD:.0f} when --normalize is set. The measured "
            f"false-positive rate applies only at K={NORMALIZE_CALIBRATION_K}, "
            f"W={NORMALIZE_CALIBRATION_W}, with --strip-comments and without "
            "--lang-aware; other profiles retain the numeric default for compatibility "
            "but are unvalidated. Pass a value to override."
        ),
    )
    deep_group.add_argument(
        "--normalize",
        action="store_true",
        default=False,
        help=(
            "Normalize identifiers to ID and literals to LIT before "
            "fingerprinting; renamed-identifier similarity is easier to surface "
            "but false-positive risk increases"
        ),
    )
    deep_group.add_argument(
        "--lang-aware",
        action="store_true",
        default=False,
        dest="lang_aware",
        help=(
            "With --normalize, use language-aware normalization (Pygments lexer, "
            "falling back to per-language keyword sets) so keywords like Rust fn/pub "
            "or Go func are preserved instead of flattened to ID. Opt-in: produces "
            "fingerprints incompatible with the default channel. Pygments comment "
            "tokens are always discarded (regardless of --strip-comments), and string "
            "literals including docstrings collapse to STR. No effect without "
            "--normalize."
        ),
    )

    # ── Forensic options ──────────────────────────────────────────────
    forensic_group = parser.add_argument_group(
        "Forensic",
        "Options for forensic precision analysis.",
    )
    # 200: difflib.SequenceMatcher applies autojunk only when the second
    # sequence has 200 or more items (Python difflib documentation).
    forensic_group.add_argument(
        "--no-autojunk",
        action="store_true",
        default=False,
        help=(
            "Disable difflib's autojunk rule, which ignores very frequent lines "
            "in files of 200 or more lines. All lines are then treated equally; "
            "slower, but no line is ignored."
        ),
    )
    forensic_group.add_argument(
        "--max-index-entries",
        type=int,
        default=10_000_000,
        dest="max_index_entries",
        help=(
            "Maximum number of entries in the Deep Compare index. "
            "Reaching the cap fails closed unless --allow-partial explicitly "
            "permits an incomplete result (default: 10,000,000)."
        ),
    )
    forensic_group.add_argument(
        "--hash",
        action="store_true",
        default=False,
        dest="embed_hash",
        help=(
            "Add the table of SHA-256 digests of the input files to the PDF, HTML "
            "and Markdown reports. A manifest.sha256.json is always written "
            "regardless of this flag."
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
    forensic_group.add_argument(
        "--bundle-sources",
        choices=["full", "none"],
        default="full",
        dest="bundle_sources",
        help=(
            "Source files in the --bundle zip: 'full' (default) copies every "
            "hashed file, 'none' leaves them out (the manifest still lists each "
            "file's SHA-256), for sources that may not leave a protected copy."
        ),
    )
    forensic_group.add_argument(
        "--allow-partial",
        action="store_true",
        default=False,
        help=(
            "Allow reports marked incomplete when some workers or files fail. "
            "Without this flag, a worker or file failure stops the run."
        ),
    )

    args = parser.parse_args(argv)

    # ── Resolve the deep threshold default by channel ────────────────
    args.threshold_deep, threshold_provenance = _resolve_threshold_deep(
        args.threshold_deep, args.normalize
    )

    # ── Validate numeric ranges at the boundary ──────────────────────
    # Degenerate values must fail loudly here, not crash mid-run after the
    # rendering phase (--workers/--window) or silently fabricate forensic
    # numbers (--k-gram 0 → every file collapses to one fingerprint → 100%).
    if args.k_gram < 1:
        parser.error("--k-gram must be >= 1.")
    if args.window < 1:
        parser.error("--window must be >= 1.")
    if args.workers < 1:
        parser.error("--workers must be >= 1.")
    if sys.platform == "win32" and args.workers > _MAX_WINDOWS_WORKERS:
        parser.error(
            f"--workers must be <= {_MAX_WINDOWS_WORKERS} on Windows "
            "(ProcessPoolExecutor limit)."
        )
    if args.max_index_entries < 1:
        parser.error("--max-index-entries must be >= 1.")
    if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 100:
        parser.error("--threshold must be between 0 and 100.")
    if not math.isfinite(args.threshold_deep) or not 0 <= args.threshold_deep <= 100:
        parser.error("--threshold-deep must be between 0 and 100.")
    # Both sizes are used as int(MB * 1024 * 1024) bytes; validate that value, so a
    # tiny size cannot become a 0-byte cap (read as "no cap" by Deep Compare but
    # "everything oversized" by the line channel) and a huge one cannot overflow.
    for option, value in (
        ("--max-file-size", args.max_file_size),
        ("--max-diff-html-size", args.max_diff_html_size),
    ):
        size_bytes = value * _BYTES_PER_MB
        if not math.isfinite(size_bytes) or size_bytes < 1:
            parser.error(
                f"{option} must be at least 1 byte ({1 / _BYTES_PER_MB:.2g} MB) "
                "and finite."
            )
    if args.encoding.lower() != "auto":
        try:
            # Raises LookupError for unknown names and for non-text codecs
            # (e.g. base64), which differ.read_file would otherwise turn into
            # "binary" pairs for every file.
            b"x".decode(args.encoding)
        except LookupError:
            parser.error(f"unknown text encoding for --encoding: {args.encoding!r}")
        except UnicodeDecodeError:
            pass  # a real text codec that cannot decode this probe byte (e.g. utf-16)
        except UnicodeError:
            # e.g. the "undefined" codec, which raises a plain UnicodeError for
            # every input: it can never decode a file.
            parser.error(f"unusable text encoding for --encoding: {args.encoding!r}")
    for option, value in (
        ("--bates-prefix", args.bates_prefix),
        ("--bates-suffix", args.bates_suffix),
        # The stamp draws prefix + number + suffix with one font, so the
        # combination must be drawable too (e.g. Hangul prefix + "é" suffix).
        ("--bates-prefix/--bates-suffix", args.bates_prefix + args.bates_suffix),
    ):
        try:
            bates_font_for(value)
        except ValueError as exc:
            parser.error(f"{option}: {exc}")
    if args.pdf_font:
        try:
            register_pdf_font(args.pdf_font, "UserCJK")
        except PdfFontError as exc:
            parser.error(f"--pdf-font: {exc}")
    if args.bates_start < 1:
        parser.error("--bates-start must be >= 1.")

    calibration_assessment = None
    if args.mode == "deep" and args.normalize:
        calibration_assessment = assess_normalize_calibration(
            threshold=args.threshold_deep,
            k=args.k_gram,
            w=args.window,
            strip_comments=args.strip_comments,
            lang_aware=args.lang_aware,
        )
    if args.mode == "deep":
        # Same wording as the report notice. Extensions whose comments cannot be
        # stripped are known only after collection; the pipeline warns then.
        warning = threshold_console_warning(
            calibration_assessment, args.threshold_deep, threshold_provenance
        )
        if warning:
            logging.warning("%s", warning)

    # Convert threshold-deep from 0-100 (user-facing) to 0-1 (internal)
    min_jaccard_internal = args.threshold_deep / 100.0

    # Build analysis metadata (embedded in every report for transparency)
    metadata = AnalysisMetadata(
        exec_mode=args.mode,
        k=args.k_gram,
        w=args.window,
        threshold=args.threshold_deep,  # 0-100 scale in metadata
        threshold_provenance=threshold_provenance,
        autojunk=not args.no_autojunk,
        normalize=args.normalize,
        lang_aware=args.lang_aware,
        strip_comments=args.strip_comments,
        calibration_profile_id=(
            calibration_assessment.profile_id if calibration_assessment else None
        ),
        calibration_status=(
            calibration_assessment.status if calibration_assessment else "not-applicable"
        ),
        calibration_profile_mismatches=(
            calibration_assessment.profile_mismatches if calibration_assessment else ()
        ),
        calibration_threshold_matches=(
            calibration_assessment.threshold_matches if calibration_assessment else None
        ),
    )

    # Resolve encoding
    encoding = args.encoding if args.encoding.lower() != "auto" else None

    # Resolve default PDF output if no --report-* specified
    report_pdf = args.report_pdf
    if (
        report_pdf is None
        and args.report_html is None
        and args.report_md is None
        and args.report_json is None
    ):
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
        threshold_provenance=threshold_provenance,
        normalize=args.normalize,
        lang_aware=args.lang_aware,
        metadata=metadata,
        # Forensic options
        autojunk=not args.no_autojunk,
        max_index_entries=args.max_index_entries,
        # Evidence integrity
        embed_hash=args.embed_hash,
        bundle_path=args.bundle_path,
        allow_partial=args.allow_partial,
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
        ignore_file=args.ignore_file,
        sensitive_files=args.sensitive_files,
        include_patterns=args.include_patterns,
        bundle_sources=args.bundle_sources,
        # Metrics-only run and selection filter
        metrics_only=args.metrics_only,
        filter_json=args.filter_json,
        # Stability & Forensics
        unreadable_log=args.unreadable_log,
        max_file_size_mb=args.max_file_size,
        max_diff_html_size_mb=args.max_diff_html_size,
        dir_alias_a=args.dir_alias_a,
        dir_alias_b=args.dir_alias_b,
        # Individual output
        preserve_tree=args.preserve_tree,
        # Whitespace normalization
        normalize_ws=args.normalize_whitespace,
        # PDF font
        pdf_font=args.pdf_font,
        pdf_lang=args.pdf_lang,
    )


if __name__ == "__main__":
    main()
