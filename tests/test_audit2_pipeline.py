"""Regression tests for the 2026-11-10 audit, pipeline / differ / models group.

Each test names the audit index number (tmp/code-audit-index.txt) it covers.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

import pytest

import diffinite.pipeline as pipeline
from diffinite.differ import (
    _highlight_line,
    _highlight_word_diff,
    _get_lexer,
    compute_diff,
    generate_html_diff,
    read_file,
)
from diffinite.models import (
    AnalysisMetadata,
    AnalysisStatus,
    DeepMatchResult,
    DiffResult,
    FileMatch,
    hash_only_label,
    percent_label,
)


def _tree(root: Path, files: dict[str, bytes | str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8", newline="")
        else:
            path.write_bytes(content)
    return root


def _run(tmp_path: Path, a: dict, b: dict, **kwargs) -> dict:
    left = _tree(tmp_path / "a", a)
    right = _tree(tmp_path / "b", b)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    kwargs.setdefault("exec_mode", "simple")
    kwargs.setdefault("workers", 1)
    kwargs.setdefault("report_json", str(out / "r.json"))
    pipeline.run_pipeline(str(left), str(right), **kwargs)
    return json.loads(Path(kwargs["report_json"]).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# #23 — Pygments border removal touches only style attributes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name, line",
    [
        ("x.py", "# border: 1px solid #ff0000; important"),
        ("x.txt", "div{ border: 1px solid #abc; }"),
        ("x.zzz", "border:1px solid #000"),
    ],
)
def test_23_border_text_in_source_is_not_deleted(name, line):
    html = _highlight_line(line, _get_lexer(name))
    text = re.sub(r"<[^>]+>", "", html)
    assert "border" in text and "solid" in text
    assert text.replace("&#39;", "'").replace("&quot;", '"') == line


def test_23_border_still_removed_from_style_attribute():
    from diffinite import differ

    sample = '<span style="color: #f00; border: 1px solid #FF0000">border: 1px solid #FF0000</span>'
    out = differ._RE_STYLE_ATTR.sub(
        lambda m: 'style="' + differ._RE_PYG_ERR_BORDER.sub("", m.group(1)) + '"', sample
    )
    assert out == '<span style="color: #f00;">border: 1px solid #FF0000</span>'


# ---------------------------------------------------------------------------
# #24 — --by-word rows keep the source whitespace
# ---------------------------------------------------------------------------
def test_24_word_diff_preserves_indentation_and_spacing():
    a, b = _highlight_word_diff("    x  =  foo(1)", "    x  =  bar(1)")
    assert a.startswith("    x  =  ")
    assert b.startswith("    x  =  ")
    assert '<span class="word-del">foo(1)</span>' in a
    assert '<span class="word-add">bar(1)</span>' in b


def test_24_whitespace_only_difference_is_highlighted():
    a, b = _highlight_word_diff("    x  =  1", "\tx = 1")
    assert "word-del" in a and "word-add" in b
    plain_a = re.sub(r"<[^>]+>", "", a)
    plain_b = re.sub(r"<[^>]+>", "", b)
    assert plain_a == "    x  =  1"
    assert plain_b == "\tx = 1"


def test_24_generate_html_diff_by_word_shows_original_text():
    html = generate_html_diff(
        "def f():\n    x  =  1\n    y = 2\n",
        "def f():\n\tx = 1\n    y = 2\n",
        by_word=True,
    )
    plain = re.sub(r"<[^>]+>", "", html)
    assert "    x  =  1" in plain
    assert "\tx = 1" in plain


def test_24_equal_row_shows_each_side_own_text_under_by_word():
    # Tab vs space lines are "equal" for the by-word matcher; each side must
    # still show its own source text.
    html = generate_html_diff("a\n\tb\nc\n", "a\n b\nc\n", by_word=True, context_lines=-1)
    assert "<pre>\tb</pre>" in html
    assert "<pre> b</pre>" in html


# ---------------------------------------------------------------------------
# #25 — moved rows keep their classes under --by-word
# ---------------------------------------------------------------------------
def test_25_moved_rows_survive_by_word():
    blk = "".join(f"moved_line_{i} = compute({i})\n" for i in range(3))
    common = "".join(f"common_{i} = {i}\n" for i in range(10))
    a = blk + common + "d1 = 1\nd2 = 2\nd3 = 3\n"
    b = "e1 = 1\ne2 = 2\ne3 = 3\n" + common + blk
    plain = generate_html_diff(a, b, detect_moved=True, by_word=False, context_lines=-1)
    worded = generate_html_diff(a, b, detect_moved=True, by_word=True, context_lines=-1)
    assert plain.count("data-move-id") > 0
    assert worded.count("data-move-id") == plain.count("data-move-id")
    assert worded.count('class="code moved-') == plain.count('class="code moved-')


# ---------------------------------------------------------------------------
# #26 — a UTF-8 BOM is stripped on every decode path
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("encoding", [None, "utf-8", "UTF8"])
def test_26_bom_is_stripped_for_every_encoding_choice(tmp_path, encoding):
    bom = tmp_path / "bom.c"
    nobom = tmp_path / "nobom.c"
    bom.write_bytes(b"\xef\xbb\xbfint main(){}\nreturn 0;\n")
    nobom.write_bytes(b"int main(){}\nreturn 0;\n")
    text_bom = read_file(str(bom), encoding=encoding)
    text_nobom = read_file(str(nobom), encoding=encoding)
    assert text_bom == text_nobom
    assert compute_diff(text_bom, text_nobom) == (1.0, 0, 0)


def test_26_bom_is_stripped_on_fallback_path(tmp_path, monkeypatch):
    from diffinite import differ

    class _Chaotic:
        chaos = 0.9
        encoding = "utf_8"

    class _Matches:
        def best(self):
            return _Chaotic()

    monkeypatch.setattr(differ, "from_bytes", lambda raw: _Matches())
    path = tmp_path / "f.c"
    path.write_bytes(b"\xef\xbb\xbfint x;\n")
    assert read_file(str(path)) == "int x;\n"


# ---------------------------------------------------------------------------
# #27 / #29 — SHA-256-only pairs are never shown as a difflib percentage
# ---------------------------------------------------------------------------
def _big_pair(tmp_path, **kwargs):
    body = "".join(f"line_{i} = {i}\n" for i in range(20000))
    changed = body.replace("line_5 = 5\n", "line_5 = 6\n")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    kwargs.setdefault("report_md", str(out / "r.md"))
    kwargs.setdefault("report_html", str(out / "r.html"))
    report = _run(
        tmp_path,
        {"big.py": body},
        {"big.py": changed},
        max_file_size_mb=0.1,
        **kwargs,
    )
    return report, out


def test_27_oversized_pair_json_records_hash_only_reason(tmp_path):
    report, _out = _big_pair(tmp_path)
    entry = report["results"][0]
    assert entry["binary"] is True
    assert entry["ratio"] == 0.0  # kept for schema compatibility
    assert entry["comparison_method"] == "sha256-only"
    assert entry["hash_only_reason"] == "max-file-size-exceeded"
    assert entry["comparison_note"] == (
        "Not compared by difflib (over --max-file-size); SHA-256 different"
    )


def test_29_markdown_and_merged_html_do_not_print_difflib_value(tmp_path):
    _report, out = _big_pair(tmp_path)
    md = (out / "r.md").read_text(encoding="utf-8")
    assert "Not compared by difflib (over --max-file-size); SHA-256 different" in md
    assert "Binary" not in md.split("## Summary", 1)[1]
    html = (out / "r.html").read_text(encoding="utf-8")
    section = html.split("big.py vs. big.py", 1)[1]
    assert "Line-level match (difflib)" not in section
    assert "+0 line(s)" not in section
    assert "Not compared by difflib (over --max-file-size); SHA-256 different" in section


def test_29_per_pair_html_and_index_do_not_print_difflib_value(tmp_path):
    _report, out = _big_pair(tmp_path, no_merge=True, report_md=None)
    files = out / "r_files"
    page = (files / "entries" / "big.py.html").read_text(encoding="utf-8")
    assert "Line-level match (difflib)" not in page
    assert "SHA-256 different" in page
    index = (files / "index.html").read_text(encoding="utf-8")
    assert "Not compared by difflib (over --max-file-size); SHA-256 different" in index
    assert "+0</td>" not in index


def test_27_hash_only_label_for_undecodable_pair():
    m = FileMatch("a.bin", "a.bin", 100.0)
    r = DiffResult(m, 1.0, 0, 0, "", binary=True, hash_match=True, hash_only_reason="not-decodable")
    assert hash_only_label(r) == (
        "Not compared by difflib (binary or not decodable as text); SHA-256 identical"
    )
    assert hash_only_label(DiffResult(m, 0.5, 1, 1, "")) is None


def test_27_sort_by_ratio_keeps_hash_only_pairs_out_of_ranking(tmp_path):
    body = "".join(f"v{i} = {i}\n" for i in range(20000))
    report = _run(
        tmp_path,
        {"big.py": body, "s.py": "a = 1\nb = 2\n", "t.py": "a = 1\n"},
        {"big.py": body, "s.py": "a = 1\nb = 3\n", "t.py": "a = 1\n"},
        max_file_size_mb=0.1,
        sort_by="ratio",
        sort_order="desc",
    )
    order = [r["file_a"] for r in report["results"]]
    assert order == ["t.py", "s.py", "big.py"]


# ---------------------------------------------------------------------------
# #28 / #31 — --binary-handling exclude is disclosed; read errors never excluded
# ---------------------------------------------------------------------------
def test_28_31_excluded_pair_is_disclosed_everywhere(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    report = _run(
        tmp_path,
        {"main.c": "int a;\n", "blob.dat": b"\x00\xff\xfe\x00" * 50},
        {"main.c": "int a;\n", "blob.dat": b"\x00\xfe\xff\x01" * 50},
        binary_handling="exclude",
        report_md=str(out / "r.md"),
        report_html=str(out / "r.html"),
    )
    diff = report["analysis_status"]["diff"]
    assert diff["requested_pair_count"] == 2
    assert diff["successful_pair_count"] == 1
    assert diff["failed_pair_count"] == 0
    assert diff["excluded_pair_count"] == 1
    assert diff["excluded_pairs"] == [
        {"file_a": "blob.dat", "file_b": "blob.dat", "reason": "binary or not decodable as text"}
    ]
    assert report["summary"]["excluded_matched_pairs"] == 1
    assert [r["file_a"] for r in report["results"]] == ["main.c"]
    md = (out / "r.md").read_text(encoding="utf-8")
    assert "Matched Pairs Not Compared (--binary-handling exclude)" in md
    assert "`blob.dat`" in md
    html = (out / "r.html").read_text(encoding="utf-8")
    assert "Matched pairs not compared (--binary-handling exclude)" in html
    assert "blob.dat" in html


def test_28_read_error_is_never_silently_excluded(tmp_path):
    left = _tree(tmp_path / "a", {"x.c": "int x;\n"})
    right = _tree(tmp_path / "b", {})
    m = FileMatch("x.c", "x.c", 100.0)
    results, _lines, unreadable, excluded = pipeline._process_match_chunk(
        1, [m], str(left), str(right), None, "exclude",
        False, False, False, True, True, False, False,
    )
    assert excluded == []
    assert len(results) == 1
    assert results[0].error.startswith("Read error (FileNotFoundError")
    assert unreadable == [str((right / "x.c").resolve())]


# ---------------------------------------------------------------------------
# #30 — Markdown code spans show names literally and cannot inject structure
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        ("a<b>.py", "`a<b>.py`"),
        ("C:\\cases\\src", "`C:\\cases\\src`"),
        ("a`b.py", "``a`b.py``"),
        ("`x``", "``` `x`` ```"),
        ("evil\n## Forged.py", "`evil\u240a## Forged.py`"),
    ],
)
def test_30_md_code_span(value, expected):
    assert pipeline._md_code(value) == expected


def test_30_md_code_table_escapes_pipe_only_in_tables():
    assert pipeline._md_code("a|b.py") == "`a|b.py`"
    assert pipeline._md_code("a|b.py", table=True) == "`a\\|b.py`"


def test_30_markdown_report_cannot_forge_heading(tmp_path):
    out = tmp_path / "r.md"
    pipeline._generate_markdown_report(
        [], ["evil\n## Forged heading.py"], [], "A", "B", False, False, None, str(out)
    )
    text = out.read_text(encoding="utf-8")
    assert "\n## Forged" not in text
    assert "- `evil\u240a## Forged heading.py`" in text


def test_30_uncompared_text_file_cannot_forge_section(tmp_path):
    out = tmp_path / "u.txt"
    pipeline._write_uncompared_file(str(out), ["x\n## Only in B (1 files)"], [], "A", "B")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if line.startswith("## Only in B")) == 0


# ---------------------------------------------------------------------------
# #32 / #53 — error pairs are failures, with the right error text
# ---------------------------------------------------------------------------
def test_32_error_pair_is_not_counted_as_success(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    report = _run(
        tmp_path,
        {"main.c": "int a;\n", "blob.dat": b"\x00\xff\xfe\x00" * 50},
        {"main.c": "int a;\n", "blob.dat": b"\x00\xfe\xff\x01" * 50},
        binary_handling="error",
        report_md=str(out / "r.md"),
    )
    status = report["analysis_status"]
    assert status["state"] == "incomplete"
    assert "diff-pair-error" in status["reasons"]
    assert status["diff"]["successful_pair_count"] == 1
    assert status["diff"]["failed_pair_count"] == 1
    assert status["diff"]["error_pair_count"] == 1
    assert len(report["results"]) == (
        status["diff"]["successful_pair_count"] + status["diff"]["error_pair_count"]
    )
    assert status["diff"]["failed_pairs"][0]["reason"] == (
        "pair-error: Could not decode one or both files"
    )
    blob = next(r for r in report["results"] if r["file_a"] == "blob.dat")
    assert blob["comparison_method"] == "not-compared"
    md = (out / "r.md").read_text(encoding="utf-8")
    row = next(line for line in md.splitlines() if "`blob.dat`" in line and line.startswith("|"))
    # Cells: #, File A, File B, Name similarity, Line match, Added, Deleted.
    line_match_cell = row.split(" | ")[4]
    assert "%" not in line_match_cell
    assert "Not compared" in line_match_cell


def test_32_exhibit_csv_does_not_print_percent_for_error_pair(tmp_path):
    pytest.importorskip("xhtml2pdf")
    out = tmp_path / "out"
    out.mkdir()
    _run(
        tmp_path,
        {"main.c": "int a;\n", "blob.dat": b"\x00\xff\xfe\x00" * 50},
        {"main.c": "int a;\n", "blob.dat": b"\x00\xfe\xff\x01" * 50},
        binary_handling="error",
        report_pdf=str(out / "r.pdf"),
    )
    with open(out / "r.csv", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    blob = next(row for row in rows[1:] if row[1] == "blob.dat")
    assert blob[4] == "Not compared (Could not decode one or both files)"


def test_53_permission_error_is_not_labelled_decode_failure(tmp_path, monkeypatch):
    left = _tree(tmp_path / "a", {"x.c": "int x;\n"})
    right = _tree(tmp_path / "b", {"x.c": "int y;\n"})
    real = pipeline.read_file

    def fake_read(path, encoding=None):
        if path.startswith(str(right.resolve())):
            raise PermissionError(13, "denied", path)
        return real(path, encoding=encoding)

    monkeypatch.setattr(pipeline, "read_file", fake_read)
    m = FileMatch("x.c", "x.c", 100.0)
    for handling in ("error", "hash", "exclude"):
        results, _l, unreadable, excluded = pipeline._process_match_chunk(
            1, [m], str(left), str(right), None, handling,
            False, False, False, True, True, False, False,
        )
        assert excluded == []
        assert results[0].error == "Access Denied (PermissionError)"
        assert unreadable == [str((right / "x.c").resolve())]


# ---------------------------------------------------------------------------
# #33 — BOM-prefixed ignore and filter files
# ---------------------------------------------------------------------------
def test_33_bom_prefixed_ignore_file_still_excludes(tmp_path):
    ignore = tmp_path / "ignore.txt"
    ignore.write_bytes(b"\xef\xbb\xbfvendor\n")
    report = _run(
        tmp_path,
        {"main.c": "int a;\n", "vendor/lib.c": "int v;\n"},
        {"main.c": "int a;\n", "vendor/lib.c": "int v;\n"},
        ignore_file=str(ignore),
    )
    assert [r["file_a"] for r in report["results"]] == ["main.c"]
    assert report["metadata"]["ignore_patterns"] == ["vendor"]


def test_33_bom_prefixed_filter_json_is_accepted(tmp_path):
    flt = tmp_path / "filter.json"
    flt.write_bytes(b"\xef\xbb\xbf" + json.dumps(["main.c"]).encode("utf-8"))
    report = _run(
        tmp_path,
        {"main.c": "int a;\n", "other.c": "int o;\n"},
        {"main.c": "int a;\n", "other.c": "int o;\n"},
        filter_json=str(flt),
    )
    assert [r["file_a"] for r in report["results"]] == ["main.c"]


# ---------------------------------------------------------------------------
# #45 — both channels use the pair-aware comment rules; labels disclose gaps
# ---------------------------------------------------------------------------
def test_45_deep_channel_borrows_partner_comment_rules(tmp_path):
    funcs = "".join(
        f"int func_{i}(int x) {{ return x * {i} + helper_{i}(x - {i}); }}\n" for i in range(60)
    )
    commented = "".join(
        f"// comment number {i} describing the function in detail\n"
        f"int func_{i}(int x) {{ return x * {i} + helper_{i}(x - {i}); }}\n"
        for i in range(60)
    )
    report = _run(
        tmp_path,
        {"engine.cxx": commented},
        {"engine.cxx.cpp": funcs},
        exec_mode="deep",
        strip_comments=True,
        min_jaccard=0.0,
        threshold=0.0,
    )
    # Before the fix Deep Compare kept the .cxx comments (unregistered suffix)
    # while the line channel stripped them, so Jaccard was far below 1.
    jaccard = report["deep_results"][0]["matches"][0]["jaccard"]
    assert jaccard == 1.0


def test_45_unstripped_extensions_are_disclosed(tmp_path):
    report = _run(
        tmp_path,
        {"build.gradle": "// license\napply plugin: 'java'\n"},
        {"build.gradle": "// license\napply plugin: 'java'\n"},
        exec_mode="deep",
        strip_comments=True,
    )
    assert report["comment_mode"].startswith("stripped (except")
    assert ".gradle" in report["comment_mode"]
    assert report["preprocessing"]["comments_not_stripped_extensions"]["line_diff"] == [".gradle"]
    assert ".gradle" in report["preprocessing"]["deep_compare_comments"]


# ---------------------------------------------------------------------------
# #46 — drive / share roots get a non-empty label
# ---------------------------------------------------------------------------
def test_46_root_label_is_never_empty():
    anchor = Path.cwd().anchor
    assert Path(anchor).resolve().name == ""
    assert pipeline._display_label(None, anchor) == str(Path(anchor).resolve())
    assert pipeline._display_label("alias", anchor) == "alias"
    assert pipeline._display_label(None, str(Path.cwd())) == Path.cwd().resolve().name


# ---------------------------------------------------------------------------
# #54 — an existing unreadable log is kept but this run's entries are logged
# ---------------------------------------------------------------------------
def test_54_existing_unreadable_log_does_not_swallow_this_run(tmp_path, caplog):
    log = tmp_path / "unreadable.log"
    pipeline._write_unreadable_log(str(log), ["A:old_run_file.c"], overwrite=False)
    with caplog.at_level(logging.ERROR, logger="diffinite.pipeline"):
        pipeline._write_unreadable_log(str(log), ["A:this_run_file.c"], overwrite=False)
    assert "A:old_run_file.c" in log.read_text(encoding="utf-8")
    assert "not from this run" in caplog.text
    assert "A:this_run_file.c" in caplog.text


# ---------------------------------------------------------------------------
# #55 / #61 — the recorded threshold is the one the user set
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("threshold", [7, 14, 28, 29, 55, 56, 57, 58, 0.9, 13.1])
def test_55_61_threshold_from_library_call_round_trips(tmp_path, threshold):
    report = _run(
        tmp_path,
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1\n"},
        exec_mode="deep",
        min_jaccard=threshold / 100.0,
    )
    assert report["metadata"]["threshold"] == float(threshold)


def test_55_61_threshold_from_cli_metadata_is_kept(tmp_path):
    meta = AnalysisMetadata("deep", 5, 4, 57.0, threshold_provenance="user")
    report = _run(
        tmp_path,
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1\n"},
        exec_mode="deep",
        min_jaccard=57 / 100.0,
        metadata=meta,
    )
    assert report["metadata"]["threshold"] == 57.0


# ---------------------------------------------------------------------------
# #82 — names with lone surrogates fail early with a clear message
# ---------------------------------------------------------------------------
def test_82_reject_unencodable_names_names_the_file():
    with pytest.raises(RuntimeError, match=re.escape("'x\\udc80.java'")):
        pipeline._reject_unencodable_names("source A path", ["ok.java", "x\udc80.java"])
    pipeline._reject_unencodable_names("source A path", ["ok.java", "한글.java"])


def test_82_surrogate_file_name_fails_before_analysis(tmp_path):
    left = tmp_path / "a"
    right = tmp_path / "b"
    left.mkdir()
    right.mkdir()
    try:
        (left / "x\udc80.java").write_text("class X {}\n", encoding="utf-8")
    except (UnicodeEncodeError, OSError):
        pytest.skip("this filesystem cannot store lone-surrogate names")
    (right / "ok.java").write_text("class X {}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="lone UTF-16 surrogate"):
        pipeline.run_pipeline(
            str(left),
            str(right),
            exec_mode="simple",
            workers=1,
            report_json=str(tmp_path / "r.json"),
        )
    assert not (tmp_path / "r.json").exists()


# ---------------------------------------------------------------------------
# Handoffs from earlier groups (fingerprint / extension) touching these files
# ---------------------------------------------------------------------------
def test_handoff_containment_is_exact_and_display_never_rounds_up_to_100():
    dr = DeepMatchResult("a.py", unique_hashes_a=100000, unique_hashes_b={"b.py": 100000})
    a_in_b, b_in_a = dr.containment("b.py", 99998)
    assert a_in_b == 99998 / 100000
    assert percent_label(a_in_b, 2) == "99.99%"
    assert percent_label(1.0, 2) == "100.00%"
    assert percent_label(0.9996, 1) == "99.9%"
    assert percent_label(0.57, 2) == "57.00%"


def test_handoff_deep_status_and_versions_reach_json(tmp_path):
    report = _run(
        tmp_path,
        {"tiny.py": "x\n", "big.py": "".join(f"v{i} = f({i})\n" for i in range(40))},
        {"tiny.py": "x\n", "big.py": "".join(f"v{i} = f({i})\n" for i in range(40))},
        exec_mode="deep",
    )
    deep = report["analysis_status"]["deep"]
    paths = {(item["side"], item["path"]) for item in deep["unfingerprinted_files"]}
    assert ("A", "tiny.py") in paths and ("B", "tiny.py") in paths
    assert deep["unfingerprinted_file_count"] == len(deep["unfingerprinted_files"])
    meta = report["metadata"]
    assert meta["python_version"]
    assert meta["unicodedata_version"]
    assert "pygments_version" in meta


def test_handoff_filtered_run_discloses_omitted_unmatched_counts(tmp_path):
    flt = tmp_path / "filter.json"
    flt.write_text(json.dumps(["main.c"]), encoding="utf-8")
    report = _run(
        tmp_path,
        {"main.c": "int a;\n", "zzzzzz.c": "int b;\n"},
        {"main.c": "int a;\n", "qq.h": "int c;\n", "wwwwwwww.txt": "int d;\n"},
        filter_json=str(flt),
    )
    assert report["unmatched_b"] == []
    selection = report["analysis_status"]["selection"]
    assert selection["omitted_unmatched_a_count"] == 1
    assert selection["omitted_unmatched_b_count"] == 2
    summary = pipeline._analysis_status_summary(
        AnalysisStatus(filter_omitted_unmatched_a=1, filter_omitted_unmatched_b=2)
    )
    assert any("omitted by the selection filter: 1 in A; 2 in B" in line for line in summary)


def test_handoff_parent_watch_initializer_is_harmless_in_main_process():
    # In the main process there is no parent; the initializer must be a no-op.
    pipeline._exit_when_parent_dies()
