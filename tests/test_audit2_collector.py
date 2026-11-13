"""Regression tests for collector audit findings #1, #10, #11, #12, #13."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from diffinite import collector
from diffinite.collector import collect_files, match_files, should_ignore


# ── #1: every listed-but-not-collected entry is disclosed ────────────────
class TestUncollectedEntriesDisclosed:
    def test_stat_failure_is_disclosed(self, tmp_path, monkeypatch):
        (tmp_path / "ok.py").write_text("x", encoding="utf-8")
        (tmp_path / "gone.py").write_text("x", encoding="utf-8")
        real_lstat = os.lstat

        def failing_lstat(path, *args, **kwargs):
            if os.path.basename(os.fspath(path)) == "gone.py":
                raise FileNotFoundError(2, "localized text", os.fspath(path))
            return real_lstat(path, *args, **kwargs)

        monkeypatch.setattr(collector.os, "lstat", failing_lstat)
        errs: list[str] = []
        assert collect_files(str(tmp_path), [], errs) == ["ok.py"]
        assert errs == ["gone.py (skipped: stat failed: ENOENT)"]

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX FIFOs")
    def test_non_regular_file_is_disclosed(self, tmp_path):
        (tmp_path / "ok.py").write_text("x", encoding="utf-8")
        os.mkfifo(tmp_path / "pipe")
        errs: list[str] = []
        assert collect_files(str(tmp_path), [], errs) == ["ok.py"]
        assert errs == ["pipe (skipped: not a regular file)"]

    @pytest.mark.skipif(os.name != "nt", reason="Win32 path normalisation only")
    def test_trailing_dot_and_space_names_are_disclosed(self, tmp_path):
        root = tmp_path.resolve()
        (root / "ok.py").write_text("x", encoding="utf-8")
        # A sibling that Win32 normalisation of "a.py." would silently alias.
        (root / "a.py").write_text("x", encoding="utf-8")
        prefix = "\\\\?\\" + str(root)
        for name in ("a.py.", "sp "):
            with open(prefix + "\\" + name, "w", encoding="utf-8") as fh:
                fh.write("hidden")
        os.mkdir(prefix + "\\dir.")
        with open(prefix + "\\dir.\\inner.py", "w", encoding="utf-8") as fh:
            fh.write("x")
        try:
            errs: list[str] = []
            files = collect_files(str(root), [], errs)
            assert files == ["a.py", "ok.py"]
            reason = collector._WIN32_NAME_REASON
            assert sorted(errs) == sorted(
                [f"a.py. (skipped: {reason})",
                 f"dir. (skipped: {reason})",
                 f"sp  (skipped: {reason})"]
            )
        finally:
            for name in ("a.py.", "sp ", "dir.\\inner.py"):
                os.remove(prefix + "\\" + name)
            os.rmdir(prefix + "\\dir.")

    def test_unaddressable_name_check_is_windows_only(self, monkeypatch):
        monkeypatch.setattr(collector.os, "name", "posix")
        assert collector._is_win32_unaddressable("a.") is False


# ── #10: same-basename ties are broken by directory, not input order ─────
class TestBasenameTieBreak:
    def test_same_basename_paired_by_parent_directory(self):
        matches, ua, ub = match_files(
            ["old/client/index.js", "old/server/index.js"],
            ["v2/server/index.js", "v2/web/client/index.js"],
        )
        pairs = {(m.rel_path_a, m.rel_path_b) for m in matches}
        assert pairs == {
            ("old/client/index.js", "v2/web/client/index.js"),
            ("old/server/index.js", "v2/server/index.js"),
        }
        assert all(m.similarity == 100.0 for m in matches)
        assert ua == [] and ub == []

    def test_tie_break_independent_of_input_order(self):
        a = ["x/zeta/util.py", "x/alpha/util.py"]
        b = ["y/alpha/util.py", "y/zeta/util.py"]
        for fa in (a, list(reversed(a))):
            matches, _, _ = match_files(fa, b)
            pairs = {(m.rel_path_a, m.rel_path_b) for m in matches}
            assert pairs == {
                ("x/zeta/util.py", "y/zeta/util.py"),
                ("x/alpha/util.py", "y/alpha/util.py"),
            }


# ── #11: ignored linked directories are not collection failures ──────────
class TestIgnoreBeforeLinkCheck:
    def test_ignored_linked_directory_not_reported(self, tmp_path, monkeypatch):
        root = tmp_path / "src"
        linked = root / "node_modules"
        linked.mkdir(parents=True)
        (root / "a.py").write_text("x", encoding="utf-8")
        original = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink", lambda self: self == linked or original(self)
        )
        errs: list[str] = []
        assert collect_files(str(root), ["node_modules"], errs) == ["a.py"]
        assert errs == []

    @pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-only")
    def test_ignored_junction_not_reported(self, tmp_path):
        root = tmp_path / "src"
        target = tmp_path / "target"
        root.mkdir()
        target.mkdir()
        (root / "a.py").write_text("x", encoding="utf-8")
        (target / "dep.py").write_text("x", encoding="utf-8")
        res = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(root / "node_modules"), str(target)],
            capture_output=True,
        )
        if res.returncode != 0:
            pytest.skip("could not create junction")
        errs: list[str] = []
        assert collect_files(str(root), ["node_modules"], errs) == ["a.py"]
        assert errs == []
        errs2: list[str] = []
        assert collect_files(str(root), [], errs2) == ["a.py"]
        assert errs2 == ["node_modules (skipped: linked or reparse-point directory)"]


# ── #12: case-sensitive matching on every OS ─────────────────────────────
class TestCaseSensitiveIgnore:
    def test_extension_case_differs(self):
        assert should_ignore("src/Foo.JAVA", ["*.java"]) is False
        assert should_ignore("src/Foo.java", ["*.java"]) is True

    def test_path_pattern_case_differs(self):
        assert should_ignore("Src/Gen/a.py", ["src/gen"]) is False
        assert should_ignore("src/gen/a.py", ["src/gen"]) is True

    def test_collect_files_case_sensitive(self, tmp_path):
        (tmp_path / "Thumbs.DB").write_text("x", encoding="utf-8")
        assert collect_files(str(tmp_path), ["Thumbs.db"]) == ["Thumbs.DB"]


# ── #13: gitignore-like semantics ────────────────────────────────────────
class TestGitignoreSemantics:
    def test_leading_globstar_matches_root(self):
        assert should_ignore("x.gen.cs", ["**/*.gen.cs"]) is True
        assert should_ignore("a/b/x.gen.cs", ["**/*.gen.cs"]) is True
        assert should_ignore("x.cs", ["**/*.gen.cs"]) is False

    def test_trailing_slash_matches_directory_at_any_depth(self):
        assert should_ignore("node_modules", ["node_modules/"], is_dir=True) is True
        assert should_ignore("pkg/node_modules", ["node_modules/"], is_dir=True) is True
        assert should_ignore("pkg/node_modules/x.js", ["node_modules/"]) is True

    def test_trailing_slash_does_not_match_file(self):
        assert should_ignore("build", ["build/"]) is False
        assert should_ignore("src/build", ["build/"]) is False

    def test_star_does_not_cross_slash(self):
        assert should_ignore("src/a.py", ["src/*.py"]) is True
        assert should_ignore("src/a/b/c.py", ["src/*.py"]) is False

    def test_slash_in_middle_anchors_to_root(self):
        assert should_ignore("src/generated/a.py", ["src/generated"]) is True
        assert should_ignore("lib/src/generated/a.py", ["src/generated"]) is False

    def test_leading_slash_anchors_bare_name(self):
        assert should_ignore("build/a.py", ["/build"]) is True
        assert should_ignore("pkg/build/a.py", ["/build"]) is False

    def test_middle_and_trailing_globstar(self):
        assert should_ignore("a/b", ["a/**/b"]) is True
        assert should_ignore("a/x/y/b", ["a/**/b"]) is True
        assert should_ignore("abc/x/y.py", ["abc/**"]) is True
        assert should_ignore("abc", ["abc/**"], is_dir=True) is False

    def test_bare_name_matches_ancestor_component(self):
        assert should_ignore("pkg/node_modules/x.js", ["node_modules"]) is True

    def test_default_style_patterns_still_work(self):
        assert should_ignore("pkg/__pycache__/m.pyc", ["*.py[cod]"]) is True
        assert should_ignore("a/b.py", ["*.py[cod]"]) is False
        assert should_ignore("a/x$py.class", ["*$py.class"]) is True

    def test_collect_files_applies_semantics(self, tmp_path):
        for rel in ("x.gen.cs", "a/y.gen.cs", "pkg/node_modules/m.js",
                    "src/top.py", "src/deep/nested.py", "keep.cs", "build"):
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        files = collect_files(
            str(tmp_path), ["**/*.gen.cs", "node_modules/", "src/*.py", "build/"]
        )
        assert files == ["build", "keep.cs", "src/deep/nested.py"]
