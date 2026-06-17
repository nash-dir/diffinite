"""Report-generation robustness fixes."""

from pathlib import Path

from diffinite import pdf_gen
from diffinite.pipeline import run_pipeline


def test_html_to_pdf_returns_false_on_render_exception(monkeypatch, tmp_path):
    # A RecursionError/MemoryError out of xhtml2pdf must not crash the pipeline;
    # html_to_pdf returns False so the caller's per-page skip runs.
    def boom(*args, **kwargs):
        raise RecursionError("simulated deep nesting")

    monkeypatch.setattr(pdf_gen.pisa, "CreatePDF", boom)
    ok = pdf_gen.html_to_pdf("<html><body>x</body></html>", str(tmp_path / "x.pdf"))
    assert ok is False


def test_metrics_only_writes_json_and_skips_pdf(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    pdf = tmp_path / "out.pdf"
    run_pipeline(
        dir_a=str(a), dir_b=str(b),
        report_pdf=str(pdf), metrics_only=True, exec_mode="simple",
    )
    assert (tmp_path / "out.json").exists()   # metrics emitted, not a silent no-op
    assert not pdf.exists()                   # PDF skipped in metrics-only mode


def test_pdf_and_html_get_distinct_signature_files(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    (a / "x.py").write_text("print(1)\n", encoding="utf-8")
    (b / "x.py").write_text("print(2)\n", encoding="utf-8")
    run_pipeline(
        dir_a=str(a), dir_b=str(b),
        report_pdf=str(tmp_path / "report.pdf"),
        report_html=str(tmp_path / "report.html"),
        exec_mode="simple",
    )
    # Previously both collapsed to report.sig (HTML overwrote the PDF's).
    assert (tmp_path / "report.pdf.sig").exists()
    assert (tmp_path / "report.html.sig").exists()
