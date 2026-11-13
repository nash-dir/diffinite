"""Regression tests: reports describe what the analysis actually did.

Each test pins one audit finding: lang-aware comment handling is disclosed,
Tier-2 text chunks are tokenized, inline block comments leave a separator,
index truncation is reported only when entries are dropped, difflib labels name
the comparison unit, the hash table prints full digests, bundle ZIP entries keep
the recorded mtimes, and the calibration size scope is stated per pair.
"""

from __future__ import annotations

import datetime
import json
import os
import time
import zipfile
from pathlib import Path

import pytest

from diffinite.models import AnalysisMetadata, FileHashEntry, deep_compare_comment_mode


def _deep_meta(**overrides) -> AnalysisMetadata:
    fields = dict(normalize=True, lang_aware=True, threshold_provenance="user")
    fields.update(overrides)
    return AnalysisMetadata("deep", 5, 4, 93.0, **fields)


# ── #1 deep-channel comment mode ──────────────────────────────────────────
def test_lang_aware_deep_channel_reports_comments_dropped():
    assert deep_compare_comment_mode(False, _deep_meta()).startswith("stripped")
    assert deep_compare_comment_mode(True, _deep_meta()) == "stripped"
    assert deep_compare_comment_mode(False, _deep_meta(lang_aware=False)) == "included"
    assert deep_compare_comment_mode(False, _deep_meta(normalize=False)) == "included"
    assert deep_compare_comment_mode(False, None) == "not-applicable"


def test_json_and_markdown_split_line_and_deep_comment_modes(tmp_path):
    from diffinite.pipeline import _generate_json_report, _generate_markdown_report

    meta = _deep_meta()
    out_json = tmp_path / "r.json"
    _generate_json_report([], [], [], "A", "B", False, False, [], str(out_json), metadata=meta)
    pre = json.loads(out_json.read_text(encoding="utf-8"))["preprocessing"]
    assert pre["line_diff_comments"] == "included"
    assert pre["deep_compare_comments"].startswith("stripped (lang-aware")

    out_md = tmp_path / "r.md"
    _generate_markdown_report([], [], [], "A", "B", False, False, [], str(out_md), metadata=meta)
    md = out_md.read_text(encoding="utf-8")
    assert "| Comments (line diff) | included |" in md
    assert "| Comments (Deep Compare) | stripped (lang-aware" in md


def test_pdf_cover_splits_comment_modes_under_lang_aware():
    from diffinite.pdf_gen import build_cover_body

    html = build_cover_body([], [], [], "A", "B", False, False, metadata=_deep_meta())
    assert 'Comments (line diff)</td><td style="width: 78%;">included</td>' in html
    assert 'Comments (Deep Compare)</td><td style="width: 78%;">stripped (lang-aware' in html


def test_lang_aware_help_discloses_comment_drop(capsys):
    from diffinite.cli import main

    with pytest.raises(SystemExit):
        main(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "always discarded (regardless of --strip-comments)" in out
    assert "counted separately for the cover section and for each file pair" in out


# ── #2 Tier-2 text chunks go through Tier-1 ───────────────────────────────
@pytest.mark.parametrize("ext", [".txt", ".html"])
def test_lang_aware_text_chunks_are_tokenized_not_appended_whole(ext):
    pytest.importorskip("pygments")
    from diffinite.fingerprint import extract_fingerprints, tokenize

    text = "alpha beta gamma 42 delta\nepsilon zeta eta theta\n" * 4
    tokens = tokenize(text, normalize=True, ext=ext, lang_aware=True)
    assert len(tokens) == len(tokenize(text, normalize=True))
    assert extract_fingerprints(text, normalize=True, ext=ext, lang_aware=True)


# ── #13 inline block comment is a separator ──────────────────────────────
def test_inline_block_comment_does_not_merge_identifiers():
    from diffinite.fingerprint import tokenize
    from diffinite.parser import strip_comments

    assert tokenize(strip_comments("int/*x*/y", ".c")) == ["int", "y"]
    assert strip_comments("return/*c*/value;", ".java") == "return value;"
    # Punctuation neighbours and multi-line comments are unchanged.
    assert strip_comments("foo(/*x*/a);", ".java") == "foo(a);"
    assert strip_comments("a /* m\nl */b", ".c") == "a \nb"


def test_markup_comment_is_not_turned_into_a_space():
    from diffinite.parser import strip_comments

    # In HTML/XML a comment is not whitespace: "foo<!-- c -->bar" renders as "foobar".
    for ext in (".html", ".xml", ".svg"):
        assert strip_comments("<b>foo<!-- c -->bar</b>", ext) == "<b>foobar</b>"


# ── #17 truncation only when an entry is dropped ─────────────────────────
def test_inverted_index_exactly_at_cap_is_complete():
    from diffinite.deep_compare import build_inverted_index

    fp_map = {"a": {1, 2}, "b": {3}}
    index, truncated = build_inverted_index(fp_map, max_entries=3)
    assert truncated is False
    assert sum(len(v) for v in index.values()) == 3

    index, truncated = build_inverted_index(fp_map, max_entries=2)
    assert truncated is True
    assert sum(len(v) for v in index.values()) == 2


# ── #16 unit-aware difflib labels ─────────────────────────────────────────
def test_by_word_reports_label_word_match(tmp_path):
    from diffinite.pdf_gen import build_cover_body
    from diffinite.pipeline import _generate_markdown_report

    out_md = tmp_path / "r.md"
    _generate_markdown_report([], [], [], "A", "B", True, False, None, str(out_md))
    md = out_md.read_text(encoding="utf-8")
    # One name per metric: "Word match" under --by-word, never "(difflib)".
    assert "| Word match |" in md and "Line match" not in md and "(difflib)" not in md

    html = build_cover_body([], [], [], "A", "B", True, False)
    assert "Word match" in html and "Line match" not in html


# ── #23 full digest in the hash table ─────────────────────────────────────
def test_hash_table_prints_full_sha256():
    from diffinite.pdf_gen import build_hash_table_html

    digest = "0123456789abcdef" * 4
    html = build_hash_table_html([FileHashEntry("a.py", digest, 1, "x")], [])
    assert digest in html
    assert "word-break:break-all" in html


# ── #26 bundle entries keep recorded mtimes ──────────────────────────────
def _bundle(tmp_path: Path, mtime: float, later_mtime: float | None = None) -> zipfile.ZipFile:
    from diffinite.evidence import compute_file_hashes, create_evidence_bundle, write_manifest

    d_a, d_b = tmp_path / "a", tmp_path / "b"
    d_a.mkdir()
    d_b.mkdir()
    (d_a / "m.py").write_text("print('a')", encoding="utf-8")
    (d_b / "m.py").write_text("print('b')", encoding="utf-8")
    for d in (d_a, d_b):
        os.utime(d / "m.py", (mtime, mtime))
    manifest = tmp_path / "manifest.sha256.json"
    write_manifest(
        str(d_a),
        str(d_b),
        compute_file_hashes(str(d_a), ["m.py"]),
        compute_file_hashes(str(d_b), ["m.py"]),
        [],
        str(manifest),
    )
    if later_mtime is not None:
        # Like the private snapshot the pipeline bundles from: same bytes, fresh mtime.
        for d in (d_a, d_b):
            os.utime(d / "m.py", (later_mtime, later_mtime))
    zip_path = tmp_path / "e.zip"
    create_evidence_bundle(str(d_a), str(d_b), ["m.py"], ["m.py"], str(manifest), [], str(zip_path))
    return zipfile.ZipFile(zip_path)


def test_bundle_entries_carry_source_mtime(tmp_path):
    mtime = datetime.datetime(2021, 6, 15, 12, 30, 20).timestamp()
    with _bundle(tmp_path, mtime) as zf:
        info = zf.getinfo("source_a/m.py")
        assert info.date_time == tuple(time.localtime(mtime)[:6])
        assert info.compress_type == zipfile.ZIP_DEFLATED


def test_bundle_entries_use_manifest_mtime_not_snapshot_mtime(tmp_path):
    recorded = datetime.datetime(2021, 6, 15, 12, 30, 20).timestamp()
    snapshot = datetime.datetime(2026, 1, 2, 3, 4, 6).timestamp()
    with _bundle(tmp_path, recorded, later_mtime=snapshot) as zf:
        assert zf.getinfo("source_a/m.py").date_time == tuple(time.localtime(recorded)[:6])
        assert zf.getinfo("source_b/m.py").date_time == tuple(time.localtime(recorded)[:6])


def test_bundle_entry_mtime_clamped_to_1980():
    from diffinite.evidence import _zip_date_time

    old = datetime.datetime(1975, 1, 1, 12, 0, 0).timestamp()
    assert _zip_date_time(old) == (1980, 1, 1, 0, 0, 0)


def test_bundle_entry_mtime_out_of_platform_range_clamps_toward_nearer_end():
    from diffinite.evidence import _ZIP_MAX_DATE_TIME, _ZIP_MIN_DATE_TIME, _zip_date_time

    # Far beyond what time.localtime accepts on any platform.
    assert _zip_date_time(1e18) == _ZIP_MAX_DATE_TIME
    assert _zip_date_time(-1e18) == _ZIP_MIN_DATE_TIME


# ── #4 / #19 calibration size scope and status wording ───────────────────
def test_disclosure_states_size_scope_per_pair_and_unchecked():
    from diffinite.calibration import (
        CALIBRATION_MAX_FILE_TOKENS,
        CALIBRATION_MAX_TOKENS,
        NORMALIZE_CALIBRATION_K,
        NORMALIZE_CALIBRATION_W,
        NORMALIZE_DEFAULT_THRESHOLD,
        assess_normalize_calibration,
        normalize_disclosure,
    )

    assessment = assess_normalize_calibration(
        threshold=NORMALIZE_DEFAULT_THRESHOLD,
        k=NORMALIZE_CALIBRATION_K,
        w=NORMALIZE_CALIBRATION_W,
        strip_comments=True,
        lang_aware=False,
    )
    s = normalize_disclosure(NORMALIZE_DEFAULT_THRESHOLD, "user", assessment=assessment)
    assert f"smaller file had {CALIBRATION_MAX_TOKENS} tokens or fewer" in s
    assert f"largest file {CALIBRATION_MAX_FILE_TOKENS}" in s
    assert "not checked" in s
    assert "files ≤" not in s


# ── #20 / #21 validation harness display and denominators ────────────────
def test_frontier_prints_two_decimal_fp_and_floor_filtered_per_level(tmp_path):
    import tests.validation.error_rate as er

    S = er.PairScore
    scores = [S("c", "normalize", "neg", None, 0.0, 100) for _ in range(104)]
    scores.append(S("c", "normalize", "neg", None, 1.0, 100))
    scores.append(S("c", "normalize", "pos", 1, 1.0, 100))
    scores.append(S("c", "normalize", "pos", 1, 0.0, 100))
    for s in list(scores):
        scores.append(S(s.case, "raw", s.label, s.level, s.jaccard, s.tokens_min))

    _, rec = er.calibrate(scores, fp_target=1.0)
    assert rec is not None and rec.fp_rate == 0.95
    out = tmp_path / "e.md"
    er.write_md_summary(scores, out)
    assert "0.95%" in out.read_text(encoding="utf-8")
    assert "| 0.9% |" not in out.read_text(encoding="utf-8")

    point = er.CalibrationPoint(floor=50, threshold=50, fp_rate=0.0, recall=0.0, coverage=1.0)
    small = [S("c", "normalize", "pos", 2, 1.0, 10), S("c", "normalize", "pos", 2, 0.0, 60)]
    # The 10-token positive is below the floor: excluded from both numerator and
    # denominator, exactly like the pooled recall.
    assert er.per_level_recall_at(small, point) == {"L2": 0.0}
