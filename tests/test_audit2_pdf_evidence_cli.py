"""Regression tests for the 2026-11-10 audit, group pdf-evidence-cli.

Findings: #3, #4, #34, #35, #36, #37, #39 (evidence half), #55/#61 (cli half),
#56, #57, #58, #59, #60, plus handoffs (comment-mode label, status block,
calibration strip_comments with unstripped extensions, CLI help texts).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import reportlab
from pypdf import PdfReader

from diffinite import cli, pdf_gen
from diffinite.calibration import assess_normalize_calibration
from diffinite.evidence import (
    SourceIntegrityError,
    _logical_report_paths,
    _validate_archive_path,
    compute_file_hashes,
    create_immutable_snapshot,
    write_manifest,
)
from diffinite.models import AnalysisMetadata, AnalysisStatus, DiffResult, FileMatch

VERA_TTF = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


def _result(**kw) -> DiffResult:
    base = dict(
        # 87.5, not 100: the name-similarity column (now "87.5%") must not
        # contain the "0.0%"/"100.0%" strings the tests below look for.
        match=FileMatch("a/x.c", "b/x.c", 87.5),
        ratio=0.0,
        additions=0,
        deletions=0,
        html_diff="",
    )
    base.update(kw)
    return DiffResult(**base)


def _fonts(pdf: Path) -> set[str]:
    page = PdfReader(str(pdf)).pages[0]
    return {str(v.get_object()["/BaseFont"]) for v in page["/Resources"]["/Font"].values()}


def _blank_pdf(path: Path, pages: int = 1) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for _ in range(pages):
        c.drawString(72, 720, "page")
        c.showPage()
    c.save()


# ── #3 CJK ranges ─────────────────────────────────────────────────────────
class TestCjkRanges:
    @pytest.mark.parametrize(
        "ch",
        ["㈜", "，", "（", "ｱ", "ᄀ", "ꥠ", "ힰ",
         "︰", "㆐", "\U0002a700"],
    )
    def test_previously_missing_blocks_get_a_font_or_a_marker(self, ch):
        # Every character is either set in a font that covers it or shown as
        # its code point; it is never left to a font that drops it.
        out = pdf_gen._apply_glyph_fonts(f"<td>x{ch}y</td>", pdf_gen._font_plan(None, None))
        assert out.startswith("<td>x<span class=") and out.endswith("</span>y</td>")
        assert ch in out or pdf_gen.code_point_marker(ch) in out

    def test_rendered_pdf_keeps_fullwidth_and_enclosed_text(self, tmp_path):
        text = "A㈜B，C（D）E"
        out = tmp_path / "cjk.pdf"
        assert pdf_gen.html_to_pdf(pdf_gen._html_wrap("t", f"<p>{text}</p>"), str(out))
        extracted = PdfReader(str(out)).pages[0].extract_text()
        assert text in extracted
        assert "■" not in extracted
        assert "/ZapfDingbats" not in _fonts(out)


# ── #56 ratio badge ───────────────────────────────────────────────────────
def test_ratio_badge_never_rounds_up_to_100():
    assert "99.9%" in pdf_gen._ratio_badge(0.9996)
    assert "100.0%" not in pdf_gen._ratio_badge(0.9996)
    assert "100.0%" in pdf_gen._ratio_badge(1.0)


# ── #34 error / hash-only pairs on the cover, diff page and layout data ──
class TestErrorPairs:
    def test_cover_shows_not_compared_for_error_pair(self):
        body = pdf_gen.build_cover_body(
            [_result(error="Could not decode one or both files")],
            [], [], "A", "B", False, False,
        )
        assert "Not compared (Could not decode one or both files)" in body
        assert "0.0%" not in body
        assert "+0" not in body and "-0<" not in body

    def test_cover_and_page_use_hash_label_for_hash_only_pair(self):
        r = _result(ratio=1.0, binary=True, hash_match=True,
                    hash_only_reason="max-file-size-exceeded")
        body = pdf_gen.build_cover_body([r], [], [], "A", "B", False, False)
        assert "Not compared by difflib (over --max-file-size); SHA-256 identical" in body
        assert "100.0%" not in body
        page = pdf_gen.build_diff_page_html(r, 1, "line")
        assert "SHA-256 identical" in page and "100.0%" not in page

    def test_diff_page_error_says_not_compared(self):
        page = pdf_gen.build_diff_page_html(_result(error="Access Denied"), 1, "line")
        assert "Not compared (Access Denied)" in page

    def test_layout_data_carries_error(self, tmp_path):
        cover, diff = tmp_path / "c.pdf", tmp_path / "d.pdf"
        _blank_pdf(cover)
        _blank_pdf(diff)
        rows = pdf_gen.merge_with_bookmarks(
            str(cover), [(str(diff), _result(error="Access Denied"))], str(tmp_path / "m.pdf")
        )
        assert rows[0]["error"] == "Access Denied"


# ── handoffs: cover comment label and status block ────────────────────────
def test_cover_comment_label_names_unstripped_extensions():
    meta = AnalysisMetadata(exec_mode="simple", k=5, w=4, threshold=5.0,
                            line_comment_unstripped_extensions=(".gradle",))
    body = pdf_gen.build_cover_body([], [], [], "A", "B", False, True, metadata=meta)
    assert "keep comments: .gradle" in body


def test_cover_status_block_matches_pipeline_summary():
    status = AnalysisStatus(
        diff_requested_pair_count=2,
        diff_successful_pair_count=1,
        diff_excluded_pairs=[{"file_a": "x.bin", "file_b": "x.bin", "reason": "binary"}],
        deep_unfingerprinted_files=[{"side": "A", "path": "t.py", "reason": "below-k-gram-size"}],
    )
    body = pdf_gen.build_cover_body([], [], [], "A", "B", False, False, analysis_status=status)
    assert ">File pairs not compared (--binary-handling exclude)</td>" in body
    assert "skipped (binary or not decodable as text)" in body
    assert "fewer tokens than the k-gram size</td><td" in body
    assert "skipped as binary content" not in body


# ── #35 user fonts are actually embedded ──────────────────────────────────
class TestUserFont:
    def test_pdf_font_is_embedded(self, tmp_path):
        out = tmp_path / "font.pdf"
        # U+0107 is outside Windows-1252 and in Vera's cmap, so Vera draws it.
        html = pdf_gen._html_wrap("t", "<p>abc \u0107 한글</p>", pdf_font=str(VERA_TTF))
        assert pdf_gen.html_to_pdf(html, str(out))
        assert any("Vera" in name for name in _fonts(out)), _fonts(out)

    def test_unloadable_font_raises(self, tmp_path):
        bad = tmp_path / "bad.ttf"
        bad.write_bytes(b"not a font")
        with pytest.raises(pdf_gen.PdfFontError):
            pdf_gen.register_pdf_font(bad, "UserCJK")
        with pytest.raises(pdf_gen.PdfFontError):
            pdf_gen.register_pdf_font(tmp_path / "missing.ttf", "UserCJK")


# ── #36 Bates labels ──────────────────────────────────────────────────────
class TestBates:
    def test_hangul_prefix_is_drawn_not_squares(self, tmp_path):
        src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
        _blank_pdf(src, pages=2)
        pdf_gen.add_bates_numbers(str(src), str(out), prefix="원고-", suffix="-A")
        texts = [p.extract_text() for p in PdfReader(str(out)).pages]
        assert "원고-0001-A" in texts[0]
        assert "원고-0002-A" in texts[1]

    def test_latin_prefix_uses_the_footer_face(self):
        assert pdf_gen.bates_font_for("PLAINTIFF-é") == "Times-Roman"

    def test_undrawable_prefix_is_refused(self, tmp_path):
        src = tmp_path / "in.pdf"
        _blank_pdf(src)
        before = src.read_bytes()
        with pytest.raises(ValueError):
            pdf_gen.add_bates_numbers(str(src), str(tmp_path / "o.pdf"), suffix="-秘")
        with pytest.raises(ValueError):
            pdf_gen.stamp_bates_inplace(str(src), 1, 4, prefix="秘")
        assert src.read_bytes() == before


# ── CLI validation (#37, #59, #60, #36, #35, #55/#61) ──────────────────────
@pytest.fixture
def captured(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(cli, "run_pipeline", lambda **kw: calls.append(kw))
    return calls


def _cli_exit(argv) -> int:
    with pytest.raises(SystemExit) as exc:
        cli.main(["a", "b", *argv])
    return exc.value.code


class TestCli:
    @pytest.mark.parametrize("enc", ["bogus", "base64", "rot13"])
    def test_unknown_or_non_text_encoding_rejected(self, captured, enc):
        assert _cli_exit(["--encoding", enc]) == 2
        assert not captured

    def test_valid_encodings_accepted(self, captured):
        cli.main(["a", "b", "--encoding", "utf-16"])
        cli.main(["a", "b", "--encoding", "euc-kr"])
        assert [c["encoding"] for c in captured] == ["utf-16", "euc-kr"]

    def test_workers_capped_on_windows(self, captured, monkeypatch):
        monkeypatch.setattr(cli.sys, "platform", "win32")
        assert _cli_exit(["--workers", "62"]) == 2
        cli.main(["a", "b", "--workers", "61"])
        assert captured[-1]["workers"] == 61

    def test_workers_not_capped_elsewhere(self, captured, monkeypatch):
        monkeypatch.setattr(cli.sys, "platform", "linux")
        cli.main(["a", "b", "--workers", "64"])
        assert captured[-1]["workers"] == 64

    @pytest.mark.parametrize("value", ["1e-7", "1e303"])
    def test_max_file_size_byte_bounds(self, captured, value):
        assert _cli_exit(["--max-file-size", value]) == 2
        assert _cli_exit(["--max-diff-html-size", value]) == 2
        assert not captured

    def test_bates_prefix_validated(self, captured):
        assert _cli_exit(["--bates-prefix", "秘-"]) == 2
        cli.main(["a", "b", "--bates-prefix", "원고-"])
        assert captured[-1]["bates_prefix"] == "원고-"

    def test_pdf_font_validated(self, captured, tmp_path):
        assert _cli_exit(["--pdf-font", str(tmp_path / "missing.ttf")]) == 2
        cli.main(["a", "b", "--pdf-font", str(VERA_TTF)])
        assert captured[-1]["pdf_font"] == str(VERA_TTF)

    def test_threshold_deep_recorded_as_typed(self, captured):
        cli.main(["a", "b", "--threshold-deep", "57"])
        call = captured[-1]
        assert call["metadata"].threshold == 57.0
        assert call["min_jaccard"] == 0.57
        # pipeline reuses metadata.threshold when it maps to min_jaccard exactly
        assert call["metadata"].threshold / 100.0 == call["min_jaccard"]


# ── #57 archive path colon rule ───────────────────────────────────────────
class TestArchivePath:
    @pytest.mark.parametrize("ok", ["foo:bar.txt", "dir/foo:bar.java", "ab:c", "dir/x.java"])
    def test_non_drive_colons_accepted_everywhere(self, ok):
        _validate_archive_path(ok, label="t")

    @pytest.mark.parametrize("bad", ["C:x.java", "dir/C:x.java", "a/b/z:", "../x", "a\\b"])
    def test_drive_designators_rejected_in_every_component(self, bad):
        with pytest.raises(SourceIntegrityError):
            _validate_archive_path(bad, label="t")

    def test_root_file_with_colon_is_hashed(self, tmp_path):
        if os.name == "nt":
            pytest.skip("':' is not a valid Windows file-name character")
        (tmp_path / "foo:bar.txt").write_text("x")
        assert [e.rel_path for e in compute_file_hashes(str(tmp_path), ["foo:bar.txt"])] == [
            "foo:bar.txt"
        ]


# ── #4 snapshot under a redirected ancestor ───────────────────────────────
def _make_dir_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
        )
        if proc.returncode != 0:
            pytest.skip("could not create junction")
    else:
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            pytest.skip("could not create symlink")


class TestSnapshotContainer:
    def _source(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("print(1)\n")
        return src, compute_file_hashes(str(src), ["a.py"])

    def test_symlinked_ancestor_of_temp_dir_is_accepted(self, tmp_path):
        src, hashes = self._source(tmp_path)
        real = tmp_path / "private_var"
        real.mkdir()
        _make_dir_link(tmp_path / "var", real)  # like macOS /var -> /private/var
        container = tmp_path / "var" / "diffinite_snapshot_x"
        container.mkdir()
        out = create_immutable_snapshot(str(src), ["a.py"], hashes, str(container / "source_a"))
        assert Path(out) == (real / "diffinite_snapshot_x" / "source_a").resolve()
        assert (Path(out) / "a.py").read_text() == "print(1)\n"

    def test_redirected_destination_itself_is_rejected(self, tmp_path):
        src, hashes = self._source(tmp_path)
        container = tmp_path / "snap"
        container.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        _make_dir_link(container / "source_a", elsewhere)
        with pytest.raises(SourceIntegrityError):
            create_immutable_snapshot(str(src), ["a.py"], hashes, str(container / "source_a"))


# ── #58 / #39 logical report names ────────────────────────────────────────
class TestLogicalReportPaths:
    def test_unrelated_files_ancestor_is_not_leaked(self, tmp_path):
        out = tmp_path / "acme_files" / "out"
        mapped = _logical_report_paths([str(out / "report.html"), str(out / "report.csv")])
        assert [name for _p, name in mapped] == ["report.html", "report.csv"]

    def test_staging_dir_under_files_folder_maps_to_names(self, tmp_path):
        staging = tmp_path / "Acme_files" / ".diffinite-export-ab12"
        mapped = _logical_report_paths([str(staging / "report.pdf")])
        assert mapped[0][1] == "report.pdf"

    def test_inferred_split_tree_and_nested_files_dir(self, tmp_path):
        tree = tmp_path / "acme_files" / "report_files"
        paths = [
            str(tree / "index.html"),
            str(tree / "entries" / "src" / "test_files" / "a.py.html"),
        ]
        assert [name for _p, name in _logical_report_paths(paths)] == [
            "report_files/index.html",
            "report_files/entries/src/test_files/a.py.html",
        ]

    def test_explicit_split_roots(self, tmp_path):
        tree = tmp_path / "out" / "report_files"
        paths = [str(tree / "001_a.html"), str(tmp_path / "out" / "report.json")]
        mapped = _logical_report_paths(paths, [str(tree)])
        assert [name for _p, name in mapped] == ["report_files/001_a.html", "report.json"]
        assert [name for _p, name in _logical_report_paths(paths, [])] == [
            "001_a.html",
            "report.json",
        ]

    def test_write_manifest_under_files_ancestor(self, tmp_path):
        import json

        out = tmp_path / "client_files" / "out"
        out.mkdir(parents=True)
        report = out / "report.json"
        report.write_text("{}")
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        manifest = write_manifest(
            str(tmp_path / "a"), str(tmp_path / "b"), [], [], [str(report)],
            str(out / "manifest.sha256.json"),
        )
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        assert [entry["path"] for entry in data["reports"]] == ["report.json"]


# ── handoff: calibration strip_comments vs. files without comment rules ──
def test_calibration_flags_unstripped_extensions():
    common = dict(threshold=93.0, k=5, w=4, strip_comments=True, lang_aware=False)
    assert assess_normalize_calibration(**common).status == "applicable"
    flagged = assess_normalize_calibration(**common, comment_unstripped_extensions=[".gradle"])
    assert flagged.status == "unvalidated-profile"
    assert flagged.profile_mismatches == ("strip_comments",)


def test_cli_help_mentions_comment_and_binary_rules(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "no registered comment syntax" in out
    assert "Unreadable files are never excluded" in out
