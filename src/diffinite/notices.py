"""Fixed report notices and plain-language status text.

Single source of the legal notices and of the plain labels for the Analysis
Status rows. The Markdown, HTML and PDF reports print the notices in
their Scope and Limitations section (each notice once, where it applies), and
the JSON report carries the same texts in its top-level ``notices`` array
(:func:`applicable_notices`). The threshold notice is produced by
``calibration.threshold_disclosure`` because its figures depend on the
effective settings.

Internal reason codes (``AnalysisStatus.reasons`` and the per-item ``reason``
fields) stay in the JSON report for machines; human-readable formats show the
labels defined here (and ``pdf_gen.incomplete_notice`` for the reasons).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Optional

from diffinite.calibration import (
    INCONCLUSIVE_TOKEN_FLOOR,
    assess_normalize_metadata,
    threshold_disclosure,
)
from diffinite.models import analysis_state_label, count_label

if TYPE_CHECKING:
    from diffinite.models import AnalysisMetadata, AnalysisStatus

SCOPE_NOTICE = (
    "Similarity figures in this report measure textual and token overlap "
    "between the files compared. They do not establish copying, derivation "
    "or infringement."
)

SHORT_CODE_NOTICE = (
    "Short files and small code fragments can show high similarity even when "
    "written independently, because language syntax and common idioms leave "
    "little room for variation."
)

INTEGRITY_NOTICE = (
    "SHA-256 digests identify the exact files analyzed. A digest shows that a "
    "file is unchanged only when it is compared with an independently retained "
    "copy. The manifest is not a digital signature."
)

INCONCLUSIVE_NOTICE = (
    "A match is marked inconclusive when, after normalization, the smaller file "
    f"has fewer than {INCONCLUSIVE_TOKEN_FLOOR} tokens. This is a precaution; no "
    "separate error rate was measured for matches between files this short."
)

CONTAINMENT_NOTE = (
    "A in B is the number of shared hashes divided by the number of unique "
    "hashes of the A file; B in A is the same ratio for the B file. "
    "Rows are selected by the Jaccard threshold only."
)


def report_notice_texts(metadata: Optional["AnalysisMetadata"]) -> list[str]:
    """Scope and Limitations notices (plain text), in report order."""
    notices = [SCOPE_NOTICE, SHORT_CODE_NOTICE]
    if metadata is not None and metadata.exec_mode == "deep":
        notices.append(
            threshold_disclosure(
                metadata.threshold,
                metadata.threshold_provenance,
                metadata.normalize,
                assessment=assess_normalize_metadata(metadata) if metadata.normalize else None,
            )
        )
    return notices


def applicable_notices(
    metadata: Optional["AnalysisMetadata"],
    *,
    any_inconclusive: bool = False,
    deep_rows: bool = False,
    hashes_reported: bool = False,
) -> list[str]:
    """Every notice that applies to one report, in the order the reports print them.

    Scope, short code and (deep mode) threshold notices always apply; the
    containment note applies when the Deep Compare table has rows; the
    inconclusive notice when a row is marked inconclusive; the integrity notice
    when the report lists SHA-256 digests (``--hash``).
    """
    notices = report_notice_texts(metadata)
    if deep_rows:
        notices.append(CONTAINMENT_NOTE)
    if any_inconclusive:
        notices.append(INCONCLUSIVE_NOTICE)
    if hashes_reported:
        notices.append(INTEGRITY_NOTICE)
    return notices


# ---------------------------------------------------------------------------
# Analysis Status as labelled rows
# ---------------------------------------------------------------------------
ITEM_REASON_LABELS: dict[str, str] = {
    "max-file-size-exceeded": "over --max-file-size",
    "permission-denied": "permission denied",
    "decode-or-read-failure": "read or decode error",
    "below-k-gram-size": "fewer tokens than the k-gram size",
    "skipped-binary-content": "binary content",
    "skipped-undecodable-unregistered-extension": (
        "not decodable as text, no registered language"
    ),
    "not-decodable": "binary or not decodable as text",
}


def item_reason_label(reason: Optional[str]) -> str:
    """Plain words for a per-file or per-pair reason recorded in the status."""
    if not reason:
        return "reason not recorded"
    if reason in ITEM_REASON_LABELS:
        return ITEM_REASON_LABELS[reason]
    for prefix, words in (
        ("worker-failure: ", "worker process stopped: "),
        ("pair-error: ", ""),
        ("skipped: ", ""),
    ):
        if reason.startswith(prefix):
            return words + reason[len(prefix):]
    return reason


EXCLUDED_INPUTS_HEADING = "Excluded Inputs"


def visible_controls(s: str) -> str:
    """Replace C0 control characters and DEL with their Unicode Control Pictures.

    A file name containing a newline (legal on POSIX) must not start a new
    Markdown block, table row or list line, where it could forge an entry.
    U+2400 + code is the Unicode "Control Pictures" block (U+2400..U+241F for
    C0, U+2421 for DEL), so the character stays visible.
    """
    return "".join(
        chr(0x2400 + ord(ch)) if ord(ch) < 0x20 else ("\u2421" if ch == "\x7f" else ch)
        for ch in s
    )


def exclusion_reason(item: dict[str, str]) -> str:
    """Why one input was excluded, in plain words (kind and rule)."""
    source = item.get("source")
    rule = item.get("rule", "?")
    if source == "ignore-file":
        why = f"ignore file rule {rule}"
    elif source == "sensitive-preset":
        why = f"sensitive-file preset rule {rule}"
    elif source == "include-filter":
        why = "no --include pattern matches"
    else:
        why = rule
    kind = "directory, contents not listed; " if item.get("kind") == "directory" else ""
    return f"{kind}{why}"


def exclusion_label(item: dict[str, str]) -> str:
    """One policy exclusion on one line: side, path, kind and the rule."""
    return f"{visible_controls(_side_path(item))}, {exclusion_reason(item)}"


def exclusion_value(status: "AnalysisStatus") -> str:
    """The value of the "Inputs excluded by policy" row.

    The list itself is never put in this one table cell: a long cell cannot
    break across PDF pages. Inline mode lists the inputs in their own
    section (:func:`excluded_input_rows`).
    """
    count = len(status.policy_excluded)
    if not count or status.exclusion_listing == "none":
        return count_label(count)
    if status.exclusion_listing == "separate":
        return f"{count_label(count)} (listed in the uncompared-files list)"
    return f"{count_label(count)} (listed under {EXCLUDED_INPUTS_HEADING})"


def excluded_input_rows(status: "AnalysisStatus") -> list[tuple[str, str]]:
    """Rows (side and path, reason) of the Excluded Inputs section; [] when the
    reports do not list them inline."""
    if status.exclusion_listing != "inline":
        return []
    return [
        (visible_controls(_side_path(item)), exclusion_reason(item))
        for item in status.policy_excluded
    ]


def _side_path(item: dict[str, str]) -> str:
    return f"{item.get('side', '?')}: {item.get('path', '?')}"


def _pair(item: dict[str, str]) -> str:
    return f"{item.get('file_a', '?')} and {item.get('file_b', '?')}"


def _detail(count: int, items: Iterable[str]) -> str:
    """``"0"`` or ``"2 (x; y)"``: the count first, then each item."""
    listed = list(items)
    if not listed:
        return count_label(count)
    return f"{count_label(count)} ({'; '.join(listed)})"


def analysis_status_rows(status: "AnalysisStatus") -> list[tuple[str, str]]:
    """Analysis Status as (label, plain-text value) rows, State first.

    Values are plain text (escape them for HTML). Deep Compare rows appear only
    when Deep Compare had inputs.
    """
    rows: list[tuple[str, str]] = [
        # The JSON "state" in words: "Complete" or "Incomplete".
        ("State", analysis_state_label(status.state)),
        (
            "Inputs not read",
            _detail(
                len(status.collection_failed_files),
                (
                    f"{_side_path(item)}, {item_reason_label(item.get('reason'))}"
                    for item in status.collection_failed_files
                ),
            ),
        ),
        ("Inputs excluded by policy", exclusion_value(status)),
        (
            "File pairs compared",
            f"{count_label(status.diff_successful_pair_count)} of "
            f"{count_label(status.diff_requested_pair_count)}",
        ),
        (
            "File pairs failed",
            _detail(
                len(status.diff_failed_pairs),
                (
                    f"{_pair(item)}, {item_reason_label(item.get('reason'))}"
                    for item in status.diff_failed_pairs
                ),
            ),
        ),
    ]
    if status.diff_excluded_pairs:
        rows.append((
            "File pairs not compared (--binary-handling exclude)",
            _detail(
                len(status.diff_excluded_pairs),
                (
                    f"{_pair(item)}, {item_reason_label(item.get('reason'))}"
                    for item in status.diff_excluded_pairs
                ),
            ),
        ))
    if status.filter_omitted_unmatched_a or status.filter_omitted_unmatched_b:
        rows.append((
            "Unmatched files omitted by the selection filter",
            f"{count_label(status.filter_omitted_unmatched_a)} in A; "
            f"{count_label(status.filter_omitted_unmatched_b)} in B",
        ))
    rows.append(("Inline diffs truncated", count_label(status.diff_truncated_count)))

    deep_used = bool(
        status.deep_requested_file_count
        or status.deep_failed_files
        or status.deep_skipped_binary_files
        or status.deep_unfingerprinted_files
        or status.deep_index_truncated
        or status.deep_reported_pair_count is not None
    )
    if deep_used:
        rows += [
            (
                "Deep Compare files processed",
                f"{count_label(status.deep_successful_file_count)} of "
                f"{count_label(status.deep_requested_file_count)}",
            ),
            (
                "Deep Compare files failed",
                _detail(
                    len(status.deep_failed_files),
                    (
                        f"{_side_path(item)}, {item_reason_label(item.get('reason'))}"
                        for item in status.deep_failed_files
                    ),
                ),
            ),
            (
                "Deep Compare files skipped (binary or not decodable as text)",
                _detail(
                    len(status.deep_skipped_binary_files),
                    (_side_path(item) for item in status.deep_skipped_binary_files),
                ),
            ),
            (
                "Deep Compare files with fewer tokens than the k-gram size",
                _detail(
                    len(status.deep_unfingerprinted_files),
                    (_side_path(item) for item in status.deep_unfingerprinted_files),
                ),
            ),
        ]
        if status.deep_lang_aware_fallback_files:
            rows.append((
                "Language-aware lexer fallback (registry keywords used)",
                _detail(
                    len(status.deep_lang_aware_fallback_files),
                    (
                        f"{_side_path(item)}, {item.get('tier', '?')}"
                        for item in status.deep_lang_aware_fallback_files
                    ),
                ),
            ))
        if status.deep_reported_pair_count is not None:
            rows.append((
                "Deep Compare pairs at or above the threshold",
                count_label(status.deep_reported_pair_count)
                if status.deep_reported_pair_count
                else "0 (no file pair reached the Jaccard threshold)",
            ))
        rows.append((
            "Deep Compare index",
            "Truncated at the --max-index-entries limit"
            if status.deep_index_truncated
            else "Complete",
        ))
    return rows


def policy_config_rows(metadata: "AnalysisMetadata") -> list[tuple[str, str]]:
    """Collection-policy rows of Analysis Configuration (label, plain text)."""
    mode = metadata.sensitive_files
    version = metadata.sensitive_preset_version or "?"
    if mode == "exclude":
        sensitive = f"excluded (preset version {version})"
    elif mode == "error":
        sensitive = f"stop the run when found (preset version {version})"
    elif mode == "include":
        sensitive = "included (preset not applied)"
    else:
        sensitive = "not recorded"
    rows = [
        ("Sensitive files", sensitive),
        (
            "Include filter",
            "; ".join(metadata.include_patterns) if metadata.include_patterns else "none",
        ),
    ]
    if metadata.bundle_sources == "full":
        rows.append(("Evidence bundle", "source files included"))
    elif metadata.bundle_sources == "none":
        rows.append((
            "Evidence bundle",
            "source files omitted; the manifest lists their SHA-256 digests",
        ))
    return rows


def status_rows_as_lines(rows: Sequence[tuple[str, str]]) -> list[str]:
    """``"Label: value"`` lines for plain-text consumers."""
    return [f"{label}: {value}" for label, value in rows]
