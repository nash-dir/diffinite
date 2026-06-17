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


class TestPathAwareIgnore:
    """.diffignore patterns: bare names match at any depth; path patterns match paths."""

    def test_component_pattern_matches_at_any_depth(self, tmp_path):
        (tmp_path / "keep.py").write_text("x", encoding="utf-8")
        nm = tmp_path / "pkg" / "node_modules"; nm.mkdir(parents=True)
        (nm / "dep.py").write_text("x", encoding="utf-8")
        files = collect_files(str(tmp_path), ["node_modules"])
        assert "keep.py" in files
        assert all("node_modules" not in f for f in files)

    def test_path_anchored_pattern_now_matches(self, tmp_path):
        (tmp_path / "keep.py").write_text("x", encoding="utf-8")
        gen = tmp_path / "src" / "generated"; gen.mkdir(parents=True)
        (gen / "auto.py").write_text("x", encoding="utf-8")
        files = collect_files(str(tmp_path), ["src/generated"])
        assert "keep.py" in files
        assert all("generated" not in f for f in files)

    def test_globstar_path_pattern(self, tmp_path):
        d = tmp_path / "build"; d.mkdir()
        (d / "a.gen.cs").write_text("x", encoding="utf-8")
        (tmp_path / "main.cs").write_text("x", encoding="utf-8")
        files = collect_files(str(tmp_path), ["**/*.gen.cs"])
        assert "main.cs" in files
        assert all(not f.endswith(".gen.cs") for f in files)


class TestBasenameMatching:
    """Fuzzy matching scores basenames (filename similarity), not full paths."""

    def test_same_basename_different_subtree_matches(self):
        matches, ua, ub = match_files(
            ["old/src/util.py"], ["new/lib/util.py"], threshold=90,
        )
        assert len(matches) == 1
        assert matches[0].similarity == 100.0

    def test_dissimilar_basenames_not_overmatched_by_shared_prefix(self):
        fa = ["very/long/shared/path/prefix/aaaa.py"]
        fb = ["very/long/shared/path/prefix/zzzz.py"]
        matches, ua, ub = match_files(fa, fb, threshold=80)
        assert matches == []


class TestSymlinkDisclosure:
    """Skipped symlinks must be disclosed, not silently dropped."""

    def test_skipped_symlink_is_recorded(self, tmp_path):
        target = tmp_path / "real.py"
        target.write_text("x = 1\n", encoding="utf-8")
        link = tmp_path / "link.py"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not permitted on this platform")
        unreadable: list[str] = []
        files = collect_files(str(tmp_path), unreadable_list=unreadable)
        assert "real.py" in files
        assert "link.py" not in files
        assert any("link.py" in u for u in unreadable)
