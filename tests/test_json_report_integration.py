import json
import tempfile
from pathlib import Path
from diffinite.cli import main

def test_json_report_generation():
    """Verify that --report-json generates a valid JSON report with expected schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir_a = Path(tmpdir) / "A"
        dir_b = Path(tmpdir) / "B"
        dir_a.mkdir()
        dir_b.mkdir()
        
        (dir_a / "sample.py").write_text("def hello():\n    print('world')", encoding="utf-8")
        (dir_b / "sample.py").write_text("def hello():\n    print('diffinite')", encoding="utf-8")
        
        json_path = Path(tmpdir) / "out.json"
        
        # Call CLI
        args = [
            str(dir_a),
            str(dir_b),
            "--mode", "simple",
            "--report-json", str(json_path)
        ]
        main(args)
        
        assert json_path.exists(), "JSON report was not created"
        
        data = json.loads(json_path.read_text(encoding="utf-8"))
        
        # Verify schema
        assert "metadata" in data
        assert data["metadata"]["exec_mode"] == "simple"
        assert data["dir_a"] == str(dir_a)
        assert data["dir_b"] == str(dir_b)
        assert data["summary"]["matched_pairs"] == 1
        
        # Verify results
        results = data["results"]
        assert len(results) == 1
        assert results[0]["file_a"] == "sample.py"
        assert results[0]["additions"] > 0
        assert results[0]["deletions"] > 0
        assert "html_diff" in results[0]
        assert "error" in results[0]
