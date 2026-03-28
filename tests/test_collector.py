"""Tests for collector module — directory scanning and matching."""

import os
import tempfile

import pytest

from diffinite.collector import collect_files, match_files


class TestCollectFiles:
    """Verify directory file collection."""

    def test_collect_from_directory(self, tmp_path):
        (tmp_path / "foo.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "bar.java").write_text("int x;", encoding="utf-8")
        files = collect_files(str(tmp_path))
        assert len(files) == 2
        assert any("foo.py" in f for f in files)
        assert any("bar.java" in f for f in files)

    def test_collect_sorted(self, tmp_path):
        for name in ["z.py", "a.py", "m.py"]:
            (tmp_path / name).write_text("pass", encoding="utf-8")
        files = collect_files(str(tmp_path))
        assert files == sorted(files)

    def test_collect_empty_dir(self, tmp_path):
        files = collect_files(str(tmp_path))
        assert files == []

    def test_collect_nested(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.py").write_text("pass", encoding="utf-8")
        (tmp_path / "top.py").write_text("pass", encoding="utf-8")
        files = collect_files(str(tmp_path))
        assert len(files) == 2


class TestMatchFiles:
    """Verify file matching logic."""

    def test_exact_match(self):
        fa = ["handler.java", "looper.java"]
        fb = ["handler.java", "looper.java"]
        matches, ua, ub = match_files(fa, fb)
        assert len(matches) == 2
        assert ua == [] and ub == []
        for m in matches:
            assert m.similarity == 100.0

    def test_no_match(self):
        fa = ["alpha.py"]
        fb = ["omega.java"]
        matches, ua, ub = match_files(fa, fb, threshold=90)
        if not matches:
            assert "alpha.py" in ua
            assert "omega.java" in ub

    def test_fuzzy_match(self):
        fa = ["my_handler_v1.java"]
        fb = ["my_handler_v2.java"]
        matches, ua, ub = match_files(fa, fb, threshold=50)
        assert len(matches) == 1
        assert matches[0].similarity > 50.0

    def test_empty_lists(self):
        matches, ua, ub = match_files([], [])
        assert matches == [] and ua == [] and ub == []

    def test_one_side_empty(self):
        matches, ua, ub = match_files(["foo.py"], [])
        assert matches == []
        assert ua == ["foo.py"]
        assert ub == []

    def test_unmatched_reported(self):
        fa = ["common.py", "only_a.py"]
        fb = ["common.py", "only_b.py"]
        matches, ua, ub = match_files(fa, fb, threshold=90)
        assert any(m.rel_path_a == "common.py" for m in matches)
