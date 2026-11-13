"""Report and console text, third pass (copy re-review and visual re-review).

Copy re-review items 1, 2, 4, 5, 10, 12, 13, 14 and visual re-review items 8
and 9: Deep Compare "ran, nothing reached the threshold" stated in every
format, exact recall figures, CLI help that matches behaviour, one column name,
console lines that say which report a digest belongs to, sentence-case CSV
headers, capitalized status words and data sizes that never read "0.0 MB".
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path

import pytest

from diffinite import notices
from diffinite.calibration import (
    NORMALIZE_DEFAULT_THRESHOLD,
    NORMALIZE_RECALL_NEAR_VERBATIM_PCT,
    NORMALIZE_RECALL_RESTRUCTURED_PCT,
    assess_normalize_calibration,
    threshold_disclosure,
)
from diffinite.models import (
    AnalysisStatus,
    analysis_state_label,
    size_label,
    truncation_note_text,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "diffinite"
FORBIDDEN = re.compile("[→←⇒…⚠✓✔—–·×]")

A_SRC = "\n".join(f"int alpha_{i}(int x) {{ return x * {i} + {i * 3}; }}" for i in range(40)) + "\n"
B_SRC = "\n".join(
    f"char *beta_{i}(void) {{ static char s[] = \"text {i} here\"; return s; }}" for i in range(40)
) + "\n"


def _dirs(tmp_path: Path, a_text: str, b_text: str) -> tuple[str, str]:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.c").write_text(a_text, encoding="utf-8")
    (tmp_path / "b" / "x.c").write_text(b_text, encoding="utf-8")
    return str(tmp_path / "a"), str(tmp_path / "b")


def _run(tmp_path: Path, a_text: str, b_text: str, **kw) -> tuple[str, dict]:
    from diffinite.pipeline import run_pipeline

    dir_a, dir_b = _dirs(tmp_path, a_text, b_text)
    out = tmp_path / "out"
    run_pipeline(
        dir_a,
        dir_b,
        workers=1,
        report_md=str(out / "r.md"),
        report_json=str(out / "r.json"),
        **kw,
    )
    md = (out / "r.md").read_text(encoding="utf-8")
    data = json.loads((out / "r.json").read_text(encoding="utf-8"))
    return md, data


# -- copy #1: Deep Compare ran but no pair reached the threshold ---------------
NO_ROWS = "0 (no file pair reached the Jaccard threshold)"
ROW_LABEL = "Deep Compare pairs at or above the threshold"


def test_deep_compare_with_no_rows_is_stated_in_markdown_and_json(tmp_path):
    md, data = _run(tmp_path, A_SRC, B_SRC, exec_mode="deep")
    assert data["deep_results"] == []
    assert data["analysis_status"]["deep"]["reported_pair_count"] == 0
    assert f"| {ROW_LABEL} | {NO_ROWS} |" in md
    assert "## Deep Compare" not in md


def test_simple_mode_says_nothing_about_deep_compare_rows(tmp_path):
    md, data = _run(tmp_path, A_SRC, B_SRC, exec_mode="simple")
    assert data["deep_results"] is None
    assert data["analysis_status"]["deep"]["reported_pair_count"] is None
    assert ROW_LABEL not in md


def test_deep_compare_row_count_when_pairs_are_reported(tmp_path):
    md, data = _run(tmp_path, A_SRC, A_SRC, exec_mode="deep")
    assert data["analysis_status"]["deep"]["reported_pair_count"] == 1
    assert f"| {ROW_LABEL} | 1 |" in md
    # copy #5: one column name.
    assert "| File A | File B | Shared hashes | Jaccard | A in B | B in A |" in md


def test_pdf_and_html_cover_receive_the_deep_compare_row():
    # pdf_gen.status_rows (PDF and HTML cover) reads the pipeline summary.
    from diffinite.pdf_gen import status_rows

    status = AnalysisStatus(deep_requested_file_count=2, deep_successful_file_count=2)
    status.deep_reported_pair_count = 0
    assert (ROW_LABEL, NO_ROWS) in status_rows(status)
    status.deep_reported_pair_count = 1234
    assert (ROW_LABEL, "1,234") in status_rows(status)


# -- copy #2: exact recall figures from calibration.json -----------------------
def test_threshold_notice_states_exact_recall_from_calibration_json():
    cal = json.loads((ROOT / "example" / "validation" / "calibration.json").read_text("utf-8"))
    point = cal["fp_le_1"]
    assert point["threshold"] == NORMALIZE_DEFAULT_THRESHOLD
    by_level = point["recall_by_level"]
    assert by_level["L1"] == NORMALIZE_RECALL_NEAR_VERBATIM_PCT
    assert {by_level[k] for k in ("L4", "L5", "L6")} == {NORMALIZE_RECALL_RESTRUCTURED_PCT}

    text = threshold_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
        True,
        assessment=assess_normalize_calibration(
            threshold=NORMALIZE_DEFAULT_THRESHOLD, k=5, w=4, strip_comments=True, lang_aware=False
        ),
    )
    assert "65% of near-verbatim copies (level L1)" in text
    assert "0% of heavily restructured copies (levels L4 to L6) were detected." in text
    assert "almost none" not in text


# -- copy #4 and #14: help text matches behaviour, no jargon -------------------
@pytest.fixture(scope="module")
def help_text():
    import contextlib
    import io

    from diffinite.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        main(["--help"])
    return " ".join(buf.getvalue().split())


def test_help_page_number_matches_cover_numbering(help_text):
    assert "counted separately for the cover section and for each file pair" in help_text
    assert "cover pages unnumbered" not in help_text


def test_help_sort_by_uses_metric_names(help_text):
    assert "'similarity' by name similarity, 'ratio' by line match" in help_text
    assert "name match score" not in help_text
    assert "content similarity" not in help_text


def test_help_hash_names_every_format_with_the_table(help_text):
    assert "to the PDF, HTML and Markdown reports" in help_text
    assert "cover page" not in help_text


@pytest.mark.parametrize(
    "jargon",
    ["Phase 1", "Phase 2", "OOM", "xhtml2pdf", "N:M", "inverted index", "the File A"],
)
def test_help_has_no_internal_terms(help_text, jargon):
    assert jargon not in help_text


# -- copy #10: console wording -------------------------------------------------
def test_console_names_each_report_digest_and_numbers_steps(tmp_path, caplog):
    from diffinite.pipeline import run_pipeline

    dir_a, dir_b = _dirs(tmp_path, A_SRC, A_SRC)
    out = tmp_path / "out"
    with caplog.at_level(logging.INFO):
        run_pipeline(
            dir_a,
            dir_b,
            workers=1,
            exec_mode="deep",
            report_html=str(out / "r.html"),
            report_json=str(out / "r.json"),
        )
    messages = [r.getMessage() for r in caplog.records]
    digests = [m for m in messages if "SHA-256 of r.html: " in m]
    assert len(digests) == 1
    assert not any("Report SHA-256" in m for m in messages)
    steps = [int(m.split(":")[0][5:]) for m in messages if re.match(r"Step \d+:", m)]
    assert steps == list(range(1, len(steps) + 1))
    assert steps[-1] >= 5
    for m in messages:
        assert not re.match(r"Step \d+[a-z]", m), m
        for term in ("N:M", "nverted index", "cross-matching"):
            assert term not in m, m
        assert not FORBIDDEN.search(m), m


def _logged_strings(path: Path) -> list[str]:
    """String literals passed to logger calls and exceptions in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in {"debug", "info", "warning", "error", "RuntimeError", "ValueError"}:
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    found.append(sub.value)
    return found


@pytest.mark.parametrize("module", ["pipeline.py", "deep_compare.py", "parser.py", "cli.py"])
def test_log_messages_have_no_dashes_or_internal_terms(module):
    for text in _logged_strings(SRC / module):
        assert not FORBIDDEN.search(text), text
        assert "nverted index" not in text, text
        assert "N:M" not in text, text


def test_index_cap_refusal_keeps_the_extension_classifier_phrase():
    # vscode-extension/src/failureClassifier.ts matches "reached --max-index-entries".
    texts = _logged_strings(SRC / "deep_compare.py")
    assert any("reached --max-index-entries" in t for t in texts)


# -- copy #12: CSV headers in sentence case -----------------------------------
def test_csv_range_headers_are_sentence_case():
    source = (SRC / "pipeline.py").read_text(encoding="utf-8")
    assert '"Bates range" if show_bates_number else "Page range"' in source
    assert "Page Range" not in source and "Bates Range" not in source


# -- copy #13 and #5: containment note -----------------------------------------
def test_containment_note_wording():
    assert "Rows are selected by the Jaccard threshold only." in notices.CONTAINMENT_NOTE
    assert "shared hashes" in notices.CONTAINMENT_NOTE
    assert "fingerprints" not in notices.CONTAINMENT_NOTE


# -- visual #8: status words capitalized, JSON keeps the machine value ---------
def test_state_row_is_capitalized_and_json_state_is_not():
    status = AnalysisStatus()
    assert notices.analysis_status_rows(status)[0] == ("State", "Complete")
    assert status.to_dict()["state"] == "complete"
    status.mark_incomplete("diff-pair-error")
    assert notices.analysis_status_rows(status)[0] == ("State", "Incomplete")
    assert analysis_state_label(None) == "Unknown"


# -- visual #9: truncation note sizes ------------------------------------------
@pytest.mark.parametrize(
    ("n", "text"),
    [
        (512, "512 bytes"),
        (10_485, "10.2 KB"),
        (1_048_575, "1.0 MB"),
        (3_145_728, "3.0 MB"),
    ],
)
def test_size_label_units(n, text):
    assert size_label(n) == text


def test_truncation_note_never_reads_zero_megabytes():
    note = truncation_note_text(50_000, 0.01)
    assert "over the 0.01 MB (10.2 KB) limit set by --max-diff-html-size" in note
    assert "its HTML is 48.8 KB" in note
    assert "0.0 MB" not in note
    # Just over the limit: never printed as the limit itself ("2.000 MB").
    note = truncation_note_text(2 * 1024 * 1024 + 10, 2.0)
    assert "its HTML is 2,097,162 bytes, over the 2 MB limit" in note
    assert "its HTML is 2.5 MB" in truncation_note_text(int(2.5 * 1024 * 1024), 2.0)
    assert not FORBIDDEN.search(note)
