"""Round-3 audit regressions: pdf_gen / evidence / cli / calibration / collector.

Covers the handoffs left by the round-2 fixer and reviewer reports:
``--encoding undefined`` exit code, Bates Hangul + non-ASCII Latin mix,
evidence ``environment`` / ``split_roots`` / base-dir contract, collector
drive-designator / backslash names and ``**`` matcher cost.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from diffinite import cli, collector, pdf_gen
from diffinite.calibration import assess_normalize_calibration
from diffinite.evidence import (
    _logical_report_paths,
    create_evidence_bundle,
    write_manifest,
)
from diffinite.models import AnalysisStatus, DiffResult, FileMatch


@pytest.fixture
def captured(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(cli, "run_pipeline", lambda **kw: calls.append(kw))
    return calls


def _cli_exit(argv) -> int:
    with pytest.raises(SystemExit) as exc:
        cli.main(["a", "b", *argv])
    return exc.value.code


# ── cli ───────────────────────────────────────────────────────────────
class TestCli:
    def test_undefined_encoding_is_clean_exit_2(self, captured, capsys):
        assert _cli_exit(["--encoding", "undefined"]) == 2
        assert "--encoding" in capsys.readouterr().err
        assert not captured

    def test_bates_prefix_suffix_combination_checked(self, captured):
        # Each part alone is drawable; together one font must draw both.
        assert _cli_exit(["--bates-prefix", "원고-", "--bates-suffix=-é"]) == 2
        assert not captured
        cli.main(["a", "b", "--bates-prefix", "PLAINTIFF-", "--bates-suffix=-é"])
        assert captured[-1]["bates_suffix"] == "-é"

    def test_strip_comments_help_discloses_kept_comments(self, capsys):
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        help_text = " ".join(capsys.readouterr().out.split())
        assert "no registered comment syntax" in help_text
        assert "compared with their comments" in help_text

    def test_workers_cap_on_windows(self, captured, monkeypatch):
        monkeypatch.setattr(cli.sys, "platform", "win32")
        assert _cli_exit(["--workers", "62"]) == 2


# ── Bates font (problem B) ────────────────────────────────────────────
class TestBatesFont:
    @pytest.mark.parametrize("text", ["원고-é", "€원고", "원고 "])
    def test_hangul_with_non_ascii_latin_rejected(self, text):
        with pytest.raises(ValueError, match="together with Hangul"):
            pdf_gen.bates_font_for(text)

    def test_allowed_labels(self):
        assert pdf_gen.bates_font_for("원고-A_1") == "HYGothic-Medium"
        assert pdf_gen.bates_font_for("PLAINTIFF-é€") == "Times-Roman"
        assert pdf_gen.bates_font_for("") == "Times-Roman"

    def test_stamp_refuses_mix_before_writing(self, tmp_path):
        from reportlab.pdfgen import canvas

        src = tmp_path / "in.pdf"
        c = canvas.Canvas(str(src))
        c.showPage()
        c.save()
        out = tmp_path / "out.pdf"
        with pytest.raises(ValueError):
            pdf_gen.add_bates_numbers(str(src), str(out), prefix="원고-", suffix="-é")
        assert not out.exists()


# ── pdf_gen labels ────────────────────────────────────────────────────
def _result(**kw) -> DiffResult:
    base = dict(
        # 87.5, not 100: the name-similarity column must not contain "0.0%".
        match=FileMatch("a.py", "a.py", 87.5),
        ratio=0.0,
        additions=0,
        deletions=0,
        html_diff="",
    )
    base.update(kw)
    return DiffResult(**base)


class TestPdfLabels:
    def test_binary_and_error_pairs_never_show_percent(self):
        binary = _result(binary=True, hash_match=False, ratio=0.0)
        error = _result(error="read failed", ratio=0.0)
        cover = pdf_gen.build_cover_body(
            [binary, error], [], [], "A", "B", False, False,
        )
        assert "SHA-256 different" in cover
        assert "Not compared (read failed)" in cover
        assert "0.0%" not in cover
        page = pdf_gen.build_diff_page_html(error, 2, "line")
        assert "Not compared (read failed)" in page and "%" not in page.split("<h2>", 1)[1].split("</p>", 1)[0]

    def test_ratio_badge_near_one(self):
        assert "100.0%" not in pdf_gen._ratio_badge(0.99996)
        assert "100.0%" in pdf_gen._ratio_badge(1.0)

    def test_cover_comment_mode_not_hard_coded(self):
        cover = pdf_gen.build_cover_body([], [], [], "A", "B", False, False)
        assert 'Comments</td><td style="width: 78%;">included</td>' in cover

    def test_status_block_uses_pipeline_summary(self):
        from diffinite.pipeline import _analysis_status_summary

        status = AnalysisStatus()
        cover = pdf_gen.build_cover_body(
            [], [], [], "A", "B", False, False, analysis_status=status,
        )
        import html as _html

        from diffinite.notices import analysis_status_rows

        # Labelled rows: every summary item appears as its own label and value.
        assert _analysis_status_summary(status)
        for label, value in analysis_status_rows(status):
            assert f">{_html.escape(label)}</td>" in cover
            assert f">{_html.escape(value)}</td>" in cover


# ── evidence contract ─────────────────────────────────────────────────
def _report(path: Path, text: str = "{}") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestEvidenceContract:
    ENV = {
        "python_version": "3.12.0",
        "pygments_version": "2.18.0",
        "unicodedata_version": "15.0.0",
        "lang_aware_tiers": {"tier1": 1},
        "lang_aware_fallback_files": ["x.txt"],
    }

    def test_environment_written_verbatim(self, tmp_path):
        report = _report(tmp_path / "out" / "report.json")
        manifest = write_manifest(
            str(tmp_path / "a"), str(tmp_path / "b"), [], [], [str(report)],
            str(tmp_path / "out" / "manifest.sha256.json"),
            split_roots=[], environment=self.ENV,
        )
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        assert data["environment"] == self.ENV

    def test_environment_omitted_when_none(self, tmp_path):
        report = _report(tmp_path / "out" / "report.json")
        manifest = write_manifest(
            str(tmp_path / "a"), str(tmp_path / "b"), [], [], [str(report)],
            str(tmp_path / "out" / "manifest.sha256.json"),
        )
        assert "environment" not in json.loads(Path(manifest).read_text(encoding="utf-8"))

    def test_split_roots_accepts_paths_and_generators(self, tmp_path):
        tree = tmp_path / "out" / "report_files"
        paths = [str(tree / "001_a.html")]
        assert _logical_report_paths(paths, (p for p in [tree]))[0][1] == "report_files/001_a.html"

    def test_inferred_root_must_be_below_base(self, tmp_path):
        # A merged index.html saved directly in a case folder named *_files.
        case = tmp_path / "Acme_files"
        paths = [str(case / "index.html")]
        assert _logical_report_paths(paths)[0][1] == "Acme_files/index.html"
        assert _logical_report_paths(paths, base_dir=case)[0][1] == "index.html"
        tree = case / "report_files"
        nested = [str(tree / "index.html")]
        assert _logical_report_paths(nested, base_dir=case)[0][1] == "report_files/index.html"

    def test_manifest_in_files_folder_uses_bare_names(self, tmp_path):
        case = tmp_path / "Acme_files"
        report = _report(case / "index.html", "<html></html>")
        manifest = write_manifest(
            str(tmp_path / "a"), str(tmp_path / "b"), [], [], [str(report)],
            str(case / "manifest.sha256.json"),
        )
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        assert [e["path"] for e in data["reports"]] == ["index.html"]

    def test_bundle_matches_manifest_with_split_roots(self, tmp_path):
        out = tmp_path / "out"
        tree = out / "report_files"
        reports = [
            _report(tree / "000_cover.pdf", "%PDF"),
            _report(out / "report.json"),
        ]
        roots = [tree]
        manifest = write_manifest(
            str(tmp_path / "a"), str(tmp_path / "b"), [], [],
            [str(r) for r in reports], str(out / "manifest.sha256.json"),
            split_roots=iter(roots), environment=self.ENV,
        )
        digest = create_evidence_bundle(
            str(tmp_path / "a"), str(tmp_path / "b"), [], [], manifest,
            [str(r) for r in reports], str(tmp_path / "bundle.zip"),
            split_roots=iter(roots),
        )
        assert len(digest) == 64


# ── calibration ───────────────────────────────────────────────────────
def test_strip_comments_with_unstripped_extensions_is_a_mismatch():
    from diffinite.calibration import (
        NORMALIZE_CALIBRATION_K,
        NORMALIZE_CALIBRATION_LANG_AWARE,
        NORMALIZE_CALIBRATION_W,
    )

    kwargs = dict(
        threshold=93,
        k=NORMALIZE_CALIBRATION_K,
        w=NORMALIZE_CALIBRATION_W,
        strip_comments=True,
        lang_aware=NORMALIZE_CALIBRATION_LANG_AWARE,
    )
    clean = assess_normalize_calibration(**kwargs)
    flagged = assess_normalize_calibration(**kwargs, comment_unstripped_extensions=(".vue",))
    assert "strip_comments" not in clean.profile_mismatches
    assert "strip_comments" in flagged.profile_mismatches
    assert not flagged.applicable


# ── collector ─────────────────────────────────────────────────────────
class TestCollector:
    @pytest.mark.parametrize("name", ["a:b.java", "C:x", "z:", "a\\b.java"])
    def test_archive_unsafe_names_have_reason(self, name):
        assert collector._archive_unsafe_name_reason(name) is not None

    @pytest.mark.parametrize("name", ["foo:bar.txt", "1:x", "é:x", "ab", ":x", "a"])
    def test_safe_names(self, name):
        assert collector._archive_unsafe_name_reason(name) is None

    @pytest.mark.skipif(os.name == "nt", reason="colon/backslash names need POSIX")
    def test_unsafe_names_skipped_at_collection(self, tmp_path):
        (tmp_path / "a:b.java").write_text("x")
        (tmp_path / "x\\y.java").write_text("x")
        (tmp_path / "D:dir").mkdir()
        (tmp_path / "D:dir" / "f.java").write_text("x")
        (tmp_path / "ok.java").write_text("x")
        skipped: list[str] = []
        assert collector.collect_files(str(tmp_path), [], skipped) == ["ok.java"]
        assert sorted(s.split(" (skipped")[0] for s in skipped) == [
            "D:dir", "a:b.java", "x\\y.java",
        ]

    def test_unsafe_names_skipped_via_monkeypatched_walk(self, tmp_path, monkeypatch):
        # Platform-independent check of the walk loop wiring.
        (tmp_path / "ok.java").write_text("x")
        real_walk = os.walk

        def fake_walk(top, onerror=None):
            for dirpath, dirnames, filenames in real_walk(top, onerror=onerror):
                if Path(dirpath) == Path(top):
                    dirnames.append("C:dir")
                    filenames.extend(["a:b.java"])
                yield dirpath, dirnames, filenames

        monkeypatch.setattr(collector.os, "walk", fake_walk)
        skipped: list[str] = []
        assert collector.collect_files(str(tmp_path), [], skipped) == ["ok.java"]
        assert sorted(skipped) == [
            "C:dir (skipped: name starts with a drive designator (X:); not "
            "representable in the evidence archive)",
            "a:b.java (skipped: name starts with a drive designator (X:); not "
            "representable in the evidence archive)",
        ]

    def test_degenerate_double_star_is_fast(self):
        path = "d/" * 40 + "x"
        start = time.perf_counter()
        assert not collector.should_ignore(path, ["**/**/**/**/**/y"])
        assert collector.should_ignore(path, ["**/**/**/**/**/x"])
        # Before merging/memoisation one call took ~5 s; now well under 1 s.
        assert time.perf_counter() - start < 1.0

    @pytest.mark.parametrize(
        "pattern,path,expected",
        [
            ("**/**/x", "x", True),
            ("a/**/**/b", "a/b", True),
            ("a/**/**/b", "a/q/r/b", True),
            ("abc/**/**", "abc", False),
            ("abc/**/**", "abc/d", True),
            ("**/x", "y/x", True),
        ],
    )
    def test_merged_double_star_semantics(self, pattern, path, expected):
        assert collector.should_ignore(path, [pattern]) is expected

    def test_docstring_mentions_leading_space_strip(self):
        assert "앞의 공백도 제거" in (collector.matching_pattern.__doc__ or "")


def test_bates_label_with_control_character_is_refused():
    import pytest as _pytest

    from diffinite.pdf_gen import bates_font_for

    with _pytest.raises(ValueError, match="control character"):
        bates_font_for("A\tB")
    assert bates_font_for("PLAINTIFF-") == "Times-Roman"


def test_name_similarity_is_never_rounded_up_to_100():
    from diffinite.models import percent_label

    assert percent_label(99.96 / 100, 1) == "99.9%"
    assert percent_label(100.0 / 100, 1) == "100.0%"
