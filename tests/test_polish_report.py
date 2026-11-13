"""Report-text polish: one name per metric, plain status rows, notices stated once.

Regression tests for the report-text review items (copy review 1 to 14, 16, 17
and visual review 5, 17, 19): Markdown, HTML, JSON, CSV wording and the
console text of the CLI and the pipeline.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path

import pytest

from diffinite import calibration, notices
from diffinite.calibration import (
    INCONCLUSIVE_TOKEN_FLOOR,
    NORMALIZE_DEFAULT_THRESHOLD,
    assess_normalize_calibration,
    threshold_console_warning,
)
from diffinite.models import (
    AnalysisMetadata,
    AnalysisStatus,
    DeepMatchResult,
    DiffResult,
    FileHashEntry,
    FileMatch,
    threshold_source_label,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "diffinite"

# Arrows, ellipsis, warning sign, check marks, dashes, middle dot, times sign.
FORBIDDEN = re.compile("[→←⇒…⚠✓✔—–·×]")


def _meta(**kw) -> AnalysisMetadata:
    base = dict(
        exec_mode="deep",
        k=5,
        w=4,
        threshold=NORMALIZE_DEFAULT_THRESHOLD,
        threshold_provenance="normalize-default",
        autojunk=True,
        normalize=True,
        lang_aware=False,
        strip_comments=True,
    )
    base.update(kw)
    return AnalysisMetadata(**base)


def _result(path="a.c", ratio=0.5, similarity=84.21, additions=1234, deletions=5):
    return DiffResult(
        match=FileMatch(rel_path_a=path, rel_path_b=path, similarity=similarity),
        ratio=ratio,
        additions=additions,
        deletions=deletions,
        html_diff="",
    )


def _deep(inconclusive=False):
    return [
        DeepMatchResult(
            file_a="a.c",
            fingerprint_count_a=10,
            unique_hashes_a=10,
            matched_files_b=[("a.c", 7, 0.2795, inconclusive)],
            unique_hashes_b={"a.c": 12},
        )
    ]


def _md(tmp_path, *, results=None, deep=None, meta=None, status=None, hashes=None):
    from diffinite.pipeline import _generate_markdown_report

    out = tmp_path / "r.md"
    _generate_markdown_report(
        results if results is not None else [_result()],
        [],
        [],
        "A",
        "B",
        False,
        True,
        deep,
        str(out),
        metadata=meta if meta is not None else _meta(),
        analysis_status=status if status is not None else AnalysisStatus(),
        file_hashes=hashes,
    )
    return out.read_text(encoding="utf-8")


def _json(tmp_path, *, deep=None, meta=None):
    from diffinite.pipeline import _generate_json_report

    out = tmp_path / "r.json"
    _generate_json_report(
        [_result()],
        [],
        [],
        "A",
        "B",
        False,
        True,
        deep,
        str(out),
        metadata=meta if meta is not None else _meta(),
        analysis_status=AnalysisStatus(),
    )
    return json.loads(out.read_text(encoding="utf-8"))


# -- copy review 1 and 2: inconclusive rule stated once, no undefined term ----
def test_inconclusive_rule_is_stated_once_and_defines_no_candidates(tmp_path):
    md = _md(tmp_path, deep=_deep(inconclusive=True))
    rule = f"fewer than {INCONCLUSIVE_TOKEN_FLOOR} tokens"
    assert md.count(rule) == 1
    assert "candidate" not in md.lower()
    assert "candidate" not in notices.INCONCLUSIVE_NOTICE.lower()


def test_threshold_disclosure_no_longer_repeats_the_inconclusive_rule():
    text = calibration.threshold_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
        True,
        assessment=assess_normalize_calibration(
            threshold=NORMALIZE_DEFAULT_THRESHOLD, k=5, w=4, strip_comments=True, lang_aware=False
        ),
    )
    assert "inconclusive" not in text.lower()


# -- copy review 3 and 4: labelled status rows, no code spans, plain reasons ---
def test_markdown_status_rows_are_labelled_plain_text(tmp_path):
    status = AnalysisStatus(diff_requested_pair_count=2, diff_successful_pair_count=1)
    status.diff_failed_pairs.append(
        {"file_a": "x.c", "file_b": "x.c", "reason": "worker-failure: boom"}
    )
    status.mark_incomplete("diff-worker-failure")
    md = _md(tmp_path, status=status)
    section = md.split("## Analysis Status", 1)[1].split("## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ")][1:]
    assert rows, section
    for row in rows:
        label = row.split(" | ")[0].lstrip("| ").strip()
        assert label, f"empty label cell: {row}"
        assert "`" not in row, f"code span in status row: {row}"
    assert "| File pairs compared | 1 of 2 |" in section
    assert "worker process stopped: boom" in section
    # Internal codes never reach human-readable text.
    assert "diff-worker-failure" not in md
    assert "worker-failure:" not in md


def test_status_rows_map_item_reason_codes_to_words():
    assert notices.item_reason_label("below-k-gram-size") == "fewer tokens than the k-gram size"
    assert notices.item_reason_label("pair-error: decode") == "decode"
    assert notices.item_reason_label(None) == "reason not recorded"


# -- copy review 5: threshold source in plain words ----------------------------
@pytest.mark.parametrize(
    "token, words",
    [
        ("user", "Set by user"),
        ("normalize-default", "Default for normalized comparison"),
        ("legacy-uncalibrated", "Default (5%)"),
        ("something-else", "Not recorded"),
        (None, "Not recorded"),
    ],
)
def test_threshold_source_label(token, words):
    assert threshold_source_label(token) == words


def test_markdown_shows_threshold_source_words_not_token(tmp_path):
    md = _md(tmp_path)
    assert "| Threshold source | Default for normalized comparison |" in md
    assert "normalize-default" not in md


# -- copy review 6, 7, 10 and visual 2, 10: one format and name per metric -----
def test_markdown_numbers_follow_the_contract(tmp_path):
    md = _md(tmp_path, deep=_deep())
    assert "| Jaccard threshold | 93% |" in md
    assert "| # | File A | File B | Name similarity | Line match | Added | Deleted |" in md
    # Deletions carry U+2212 MINUS SIGN, as in the PDF and HTML cover.
    assert "| 84.2% | 50.0% | +1,234 | −5 |" in md
    assert "| File A | File B | Shared hashes | Jaccard | A in B | B in A |" in md
    assert "| 27.95% | 70.00% | 58.33% |" in md
    assert "(difflib)" not in md
    assert "A File" not in md


def test_csv_header_has_no_difflib_or_unit_suffix():
    source = (SRC / "pipeline.py").read_text(encoding="utf-8")
    assert '"Name similarity",' in source
    assert "match (difflib" not in source


# -- copy review 8 and visual 19: Markdown has the timestamp and hash table ----
def test_markdown_has_report_generated_and_hash_table_with_integrity_notice(tmp_path):
    hashes_a = [FileHashEntry("a.c", "a" * 64, 1234, "2026-01-01T00:00:00")]
    hashes_b = [FileHashEntry("a.c", "b" * 64, 5, "2026-01-01T00:00:00")]
    md = _md(tmp_path, hashes=(hashes_a, hashes_b))
    assert re.search(r"\| Report generated \| \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC \|", md)
    assert "## Evidence Integrity: SHA-256 Hashes" in md
    assert "a" * 64 in md and "b" * 64 in md
    assert "| 1,234 |" in md
    assert md.count(notices.INTEGRITY_NOTICE) == 1
    assert md.index("SHA-256 Hashes") < md.index(notices.INTEGRITY_NOTICE)


def test_markdown_without_hash_has_no_integrity_section(tmp_path):
    md = _md(tmp_path)
    assert "SHA-256 Hashes" not in md
    assert notices.INTEGRITY_NOTICE not in md


# -- copy review 9: JSON carries the notices ----------------------------------
def test_json_carries_the_applicable_notices(tmp_path):
    report = _json(tmp_path, deep=_deep(inconclusive=True))
    texts = report["notices"]
    assert texts[0] == notices.SCOPE_NOTICE
    assert texts[1] == notices.SHORT_CODE_NOTICE
    assert texts[2] == report["metadata"]["calibration_disclosure"]
    assert notices.CONTAINMENT_NOTE in texts
    assert notices.INCONCLUSIVE_NOTICE in texts
    assert notices.INTEGRITY_NOTICE in texts
    assert len(texts) == len(set(texts))


def test_json_omits_notices_that_do_not_apply(tmp_path):
    report = _json(tmp_path, deep=None, meta=_meta(exec_mode="simple", normalize=False))
    assert notices.INCONCLUSIVE_NOTICE not in report["notices"]
    assert notices.CONTAINMENT_NOTE not in report["notices"]
    assert notices.SCOPE_NOTICE in report["notices"]


# -- visual review 5: English pages say so ------------------------------------
def test_pipeline_html_templates_declare_english():
    source = (SRC / "pipeline.py").read_text(encoding="utf-8")
    assert 'lang="ko"' not in source
    assert source.count('<html lang="en">') == 3


# -- copy review 12: console warnings use the report wording -------------------
def test_console_warning_for_unvalidated_profile_names_unstripped_extensions():
    assessment = assess_normalize_calibration(
        threshold=NORMALIZE_DEFAULT_THRESHOLD,
        k=5,
        w=4,
        strip_comments=True,
        lang_aware=False,
        comment_unstripped_extensions=(".gradle", ".vue"),
    )
    text = threshold_console_warning(
        assessment,
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
        comment_unstripped_extensions=(".gradle", ".vue"),
    )
    assert "comment stripping (comments kept in .gradle, .vue files)" in text
    assert "unvalidated profile" in text
    assert "strip_comments" not in text
    assert "published" not in text


def test_console_warning_for_legacy_default_and_calibrated_point():
    legacy = threshold_console_warning(None, 5.0, "legacy-uncalibrated")
    assert legacy.startswith("Deep Compare uses the default threshold of 5%.")
    assert "candidates" not in legacy and "legal conclusions" not in legacy
    calibrated = assess_normalize_calibration(
        threshold=NORMALIZE_DEFAULT_THRESHOLD, k=5, w=4, strip_comments=True, lang_aware=False
    )
    assert threshold_console_warning(calibrated, 93.0, "normalize-default") is None


# -- copy review 13, 14 and visual 17: no decorative glyphs in console text ----
def _user_visible_strings(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            docstrings.add(id(node.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, node.value


@pytest.mark.parametrize(
    "name",
    [
        "pipeline.py",
        "cli.py",
        "collector.py",
        "deep_compare.py",
        "evidence.py",
        "calibration.py",
        "notices.py",
        "fingerprint.py",
    ],
)
def test_no_forbidden_glyphs_in_strings(name):
    hits = [
        f"{name}:{line}: {text[:60]!r}"
        for line, text in _user_visible_strings(SRC / name)
        if FORBIDDEN.search(text)
    ]
    assert not hits, "\n".join(hits)


def test_cli_help_has_no_forbidden_glyphs(capsys):
    from diffinite import cli

    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert not FORBIDDEN.search(out)
    assert "->" not in out


# -- copy review 16: units and grammar in truncation notes and counts ----------
def test_truncation_note_uses_one_unit(tmp_path):
    from diffinite.pipeline import _process_match_chunk

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.c").write_text("".join(f"int a{i};\n" for i in range(400)), encoding="utf-8")
    (b / "x.c").write_text("".join(f"int b{i};\n" for i in range(400)), encoding="utf-8")
    results, *_ = _process_match_chunk(
        1,
        [FileMatch("x.c", "x.c", 100.0)],
        str(a),
        str(b),
        None,
        "hash",
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        max_diff_html_size_mb=0.001,
    )
    note = results[0].html_diff
    assert "Inline diff not included" in note
    # 0.001 MB is 1,048 bytes: the limit is also stated in KB, never as "0.0 MB".
    assert "over the 0.001 MB (1.0 KB) limit set by --max-diff-html-size" in note
    assert "0.0 MB" not in note


def test_markdown_counts_use_singular_and_plural(tmp_path):
    md = _md(tmp_path, meta=_meta(ignore_patterns=("*.o",)))
    assert "| Ignore policy | 1 rule; SHA-256 none |" in md
    assert "| Selection filter | none; 0 paths; SHA-256 none |" in md
    assert "(s)" not in md


# -- copy review 17: no raw worker progress on stdout --------------------------
def test_worker_chunk_prints_nothing_to_stdout(tmp_path, capsys):
    from diffinite.pipeline import _process_match_chunk

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.c").write_text("int a;\n", encoding="utf-8")
    (tmp_path / "b" / "x.c").write_text("int b;\n", encoding="utf-8")
    _process_match_chunk(
        1,
        [FileMatch("x.c", "x.c", 100.0)],
        str(tmp_path / "a"),
        str(tmp_path / "b"),
        None,
        "hash",
        False,
        False,
        False,
        True,
        True,
        False,
        False,
    )
    assert capsys.readouterr().out == ""


def test_step_log_lines_have_no_trailing_ellipsis(tmp_path, caplog):
    from diffinite.pipeline import run_pipeline

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.c").write_text("int a;\n", encoding="utf-8")
    (tmp_path / "b" / "x.c").write_text("int a;\n", encoding="utf-8")
    with caplog.at_level(logging.INFO):
        run_pipeline(
            str(tmp_path / "a"),
            str(tmp_path / "b"),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "out" / "r.json"),
        )
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Step 1: Collecting files") for m in messages)
    for message in messages:
        assert not FORBIDDEN.search(message), message
