"""End-to-end pipeline tests using the example directory."""

import json
import os
from pathlib import Path

import pytest


EXAMPLE_LEFT = str(Path(__file__).resolve().parent.parent / "example" / "left")
EXAMPLE_RIGHT = str(Path(__file__).resolve().parent.parent / "example" / "right")
EXAMPLE_EXISTS = Path(EXAMPLE_LEFT).is_dir() and Path(EXAMPLE_RIGHT).is_dir()


@pytest.mark.skipif(not EXAMPLE_EXISTS, reason="example/ directories not found")
class TestPipelineE2E:
    """Integration tests using the example data."""

    def test_standard_mode(self, tmp_path):
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "e2e_report.pdf")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            report_pdf=output,
            by_word=False,
            strip_comments=True,
        )
        assert Path(output).exists()
        assert Path(output).stat().st_size > 0

    def test_deep_mode(self, tmp_path):
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "deep_report.pdf")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            report_pdf=output,
            exec_mode="deep",
            workers=2,
            kgram_size=5,
            window_size=4,
        )
        assert Path(output).exists()
        assert Path(output).stat().st_size > 0

    def test_no_merge_mode(self, tmp_path):
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "individual.pdf")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            report_pdf=output,
            no_merge=True,
        )
        files_dir = tmp_path / "individual_files"
        if files_dir.exists():
            pdfs = list(files_dir.glob("*.pdf"))
            assert len(pdfs) >= 1


class TestJsonReport:
    """Tests for --report-json output format."""

    def test_json_report_empty_dirs(self, tmp_path):
        """JSON report is generated even with empty directories."""
        from diffinite.pipeline import run_pipeline

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        output = str(tmp_path / "result.json")

        run_pipeline(dir_a=str(d_a), dir_b=str(d_b), report_json=output)

        assert Path(output).exists()
        data = json.loads(Path(output).read_text(encoding="utf-8"))
        assert data["summary"]["matched_pairs"] == 0
        assert isinstance(data["results"], list)
        assert isinstance(data["unmatched_a"], list)

    def test_json_report_structure(self, tmp_path):
        """JSON report contains all required top-level keys."""
        from diffinite.pipeline import run_pipeline

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        (d_a / "hello.py").write_text("import os\nprint('hello')\nprint('done')\n", encoding="utf-8")
        (d_b / "hello.py").write_text("import os\nprint('world')\nprint('done')\n", encoding="utf-8")
        output = str(tmp_path / "result.json")

        run_pipeline(dir_a=str(d_a), dir_b=str(d_b), report_json=output)

        data = json.loads(Path(output).read_text(encoding="utf-8"))
        # Top-level keys
        for key in ("metadata", "dir_a", "dir_b", "summary",
                     "results", "unmatched_a", "unmatched_b"):
            assert key in data, f"Missing key: {key}"
        # Result entry keys
        assert len(data["results"]) == 1
        r = data["results"][0]
        for key in ("file_a", "file_b", "ratio", "additions",
                     "deletions", "html_diff"):
            assert key in r, f"Missing result key: {key}"
        assert r["ratio"] > 0
        assert "<table" in r["html_diff"]

    @pytest.mark.skipif(not EXAMPLE_EXISTS, reason="example/ directories not found")
    def test_json_report_deep_mode(self, tmp_path):
        """JSON report includes deep_results when mode=deep."""
        from diffinite.pipeline import run_pipeline

        output = str(tmp_path / "deep.json")
        run_pipeline(
            dir_a=EXAMPLE_LEFT,
            dir_b=EXAMPLE_RIGHT,
            report_json=output,
            exec_mode="deep",
            workers=2,
        )
        data = json.loads(Path(output).read_text(encoding="utf-8"))
        assert data["metadata"]["exec_mode"] == "deep"
        # deep_results should be a list (may be empty if no cross-matches)
        assert isinstance(data["deep_results"], list)

class TestPipelineAuditFeatures:
    """Tests for Phase 1/2 Architecture and Forensic Audit Features."""
    
    def test_filter_json(self, tmp_path):
        from diffinite.pipeline import run_pipeline
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        (d_a / "f1.txt").write_text("A", encoding="utf-8")
        (d_b / "f1.txt").write_text("B", encoding="utf-8")
        (d_a / "f2.txt").write_text("A", encoding="utf-8")
        (d_b / "f2.txt").write_text("B", encoding="utf-8")
        
        filter_file = tmp_path / "filter.json"
        filter_file.write_text(json.dumps(["f2.txt"]))
        
        output = str(tmp_path / "result_filtered.json")
        run_pipeline(dir_a=str(d_a), dir_b=str(d_b), report_json=output, filter_json=str(filter_file))
        
        data = json.loads(Path(output).read_text(encoding="utf-8"))
        assert len(data["results"]) == 1
        assert data["results"][0]["file_a"] == "f2.txt"

    def test_multiprocessing_workers(self, tmp_path):
        from diffinite.pipeline import run_pipeline
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        # Create 10 files to distribute across workers
        for i in range(10):
            (d_a / f"f{i}.txt").write_text("1", encoding="utf-8")
            (d_b / f"f{i}.txt").write_text("2", encoding="utf-8")
            
        output = str(tmp_path / "result_mp.json")
        run_pipeline(dir_a=str(d_a), dir_b=str(d_b), report_json=output, workers=4)
        
        data = json.loads(Path(output).read_text(encoding="utf-8"))
        assert len(data["results"]) == 10
        
    def test_unreadable_log(self, tmp_path):
        from diffinite.pipeline import run_pipeline
        import sys
        import os
        
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        f_a = d_a / "locked.txt"
        f_b = d_b / "locked.txt"
        f_a.write_text("A", encoding="utf-8")
        f_b.write_text("B", encoding="utf-8")
        
        handles = []
        if sys.platform == "win32":
            import msvcrt
            f_a_handle = open(f_a, "a")
            msvcrt.locking(f_a_handle.fileno(), msvcrt.LK_NBLCK, 1)
            handles.append(f_a_handle)
            f_b_handle = open(f_b, "a")
            msvcrt.locking(f_b_handle.fileno(), msvcrt.LK_NBLCK, 1)
            handles.append(f_b_handle)
        else:
            os.chmod(f_a, 0o000)
            os.chmod(f_b, 0o000)
            
        log_file = tmp_path / "unreadable.log"
        
        try:
            run_pipeline(dir_a=str(d_a), dir_b=str(d_b), unreadable_log=str(log_file), workers=2)
            
            assert log_file.exists()
            log_content = log_file.read_text(encoding="utf-8")
            assert "locked.txt" in log_content
        finally:
            if sys.platform == "win32":
                import msvcrt
                for h in handles:
                    msvcrt.locking(h.fileno(), msvcrt.LK_UNLCK, 1)
                    h.close()
            else:
                os.chmod(f_a, 0o644)
                os.chmod(f_b, 0o644)

    def test_individual_html_flat(self, tmp_path):
        """--no-merge + --no-preserve-tree produces flat HTML files + index.html."""
        from diffinite.pipeline import run_pipeline
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        (d_a / "hello.py").write_text("print('a')\n", encoding="utf-8")
        (d_b / "hello.py").write_text("print('b')\n", encoding="utf-8")
        sub_a = d_a / "sub"; sub_a.mkdir()
        sub_b = d_b / "sub"; sub_b.mkdir()
        (sub_a / "deep.py").write_text("x=1\n", encoding="utf-8")
        (sub_b / "deep.py").write_text("x=2\n", encoding="utf-8")

        output = str(tmp_path / "result.html")
        run_pipeline(
            dir_a=str(d_a), dir_b=str(d_b),
            report_html=output,
            no_merge=True,
            preserve_tree=False,
            exec_mode="simple",
        )

        out_dir = tmp_path / "result_files"
        assert out_dir.exists()
        assert (out_dir / "index.html").exists()
        # Flat mode: files should be at root level with numbered prefix
        html_files = list(out_dir.glob("*.html"))
        # index.html + 2 diff files = 3
        assert len(html_files) == 3
        # Verify index.html contains links
        index_content = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "hello.py" in index_content
        assert "<a href=" in index_content

    def test_individual_html_tree(self, tmp_path):
        """--no-merge + --preserve-tree preserves directory structure."""
        from diffinite.pipeline import run_pipeline
        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        sub_a = d_a / "pkg"; sub_a.mkdir()
        sub_b = d_b / "pkg"; sub_b.mkdir()
        (sub_a / "mod.py").write_text("x=1\n", encoding="utf-8")
        (sub_b / "mod.py").write_text("x=2\n", encoding="utf-8")

        output = str(tmp_path / "tree_out.html")
        run_pipeline(
            dir_a=str(d_a), dir_b=str(d_b),
            report_html=output,
            no_merge=True,
            preserve_tree=True,
            exec_mode="simple",
        )

        out_dir = tmp_path / "tree_out_files"
        assert out_dir.exists()
        assert (out_dir / "index.html").exists()
        # Tree mode: file should be at pkg/mod.html
        assert (out_dir / "pkg" / "mod.html").exists()

    def test_max_file_size_hash_fallback(self, tmp_path):
        """Files exceeding max_file_size bypass read_file and fall back to SHA-256 hash comparison."""
        from diffinite.pipeline import run_pipeline

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        # Identical content → hash_match=True
        (d_a / "same.txt").write_text("hello\n", encoding="utf-8")
        (d_b / "same.txt").write_text("hello\n", encoding="utf-8")
        # Different content → hash_match=False
        (d_a / "diff.txt").write_text("aaa\n", encoding="utf-8")
        (d_b / "diff.txt").write_text("bbb\n", encoding="utf-8")

        output = str(tmp_path / "oom.json")
        # max_file_size=0.000001 (≈1 byte) forces ALL files through the hash bypass
        run_pipeline(
            dir_a=str(d_a), dir_b=str(d_b),
            report_json=output,
            max_file_size_mb=0.000001,
        )

        data = json.loads(Path(output).read_text(encoding="utf-8"))
        results = {r["file_a"]: r for r in data["results"]}
        # Both files should be marked as binary (hash fallback)
        assert results["same.txt"]["binary"] is True
        assert results["diff.txt"]["binary"] is True
        # Identical file → ratio 1.0, different → ratio 0.0
        assert results["same.txt"]["ratio"] == 1.0
        assert results["diff.txt"]["ratio"] == 0.0

    def test_max_file_size_permission_error_logged(self, tmp_path):
        """Locked oversized files are recorded in unreadable_log, not silently dropped."""
        import sys
        from diffinite.pipeline import run_pipeline

        d_a = tmp_path / "a"; d_a.mkdir()
        d_b = tmp_path / "b"; d_b.mkdir()
        f_a = d_a / "big_locked.txt"
        f_b = d_b / "big_locked.txt"
        f_a.write_text("A", encoding="utf-8")
        f_b.write_text("B", encoding="utf-8")

        handles = []
        if sys.platform == "win32":
            import msvcrt
            h_a = open(f_a, "a")
            msvcrt.locking(h_a.fileno(), msvcrt.LK_NBLCK, 1)
            handles.append(h_a)
            h_b = open(f_b, "a")
            msvcrt.locking(h_b.fileno(), msvcrt.LK_NBLCK, 1)
            handles.append(h_b)
        else:
            os.chmod(f_a, 0o000)
            os.chmod(f_b, 0o000)

        log_file = tmp_path / "unreadable_oom.log"

        try:
            # max_file_size=0.000001 forces hash path; locks cause PermissionError
            run_pipeline(
                dir_a=str(d_a), dir_b=str(d_b),
                unreadable_log=str(log_file),
                max_file_size_mb=0.000001,
                workers=1,
            )

            assert log_file.exists()
            log_content = log_file.read_text(encoding="utf-8")
            assert "big_locked.txt" in log_content
        finally:
            if sys.platform == "win32":
                import msvcrt
                for h in handles:
                    msvcrt.locking(h.fileno(), msvcrt.LK_UNLCK, 1)
                    h.close()
            else:
                os.chmod(f_a, 0o644)
                os.chmod(f_b, 0o644)
