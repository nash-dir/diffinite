"""Unicode / i18n end-to-end coverage.

Exercises the full report pipeline on the committed ``example/unicode`` fixture —
non-ASCII filenames, CJK/Cyrillic/Arabic identifiers and comments, emoji — so a
regression in tokenization, comment-stripping, filename handling, or report
rendering on non-ASCII input fails CI instead of shipping.
"""

from pathlib import Path

import pytest

from diffinite.fingerprint import tokenize

_UNI = Path(__file__).resolve().parent.parent / "example" / "unicode"
_HAVE = (_UNI / "left").is_dir() and (_UNI / "right").is_dir()
requires_fixture = pytest.mark.skipif(not _HAVE, reason="example/unicode not present")


class TestUnicodeTokenization:
    def test_cjk_and_cyrillic_identifiers_are_single_tokens(self):
        # The tokenizer is Unicode-aware (\w+): a CJK/Cyrillic identifier must be
        # ONE token, not split per character (else non-ASCII fingerprint density
        # would differ wildly from ASCII).
        toks = tokenize("더하기 = 計算 + переменная")
        assert "더하기" in toks
        assert "計算" in toks
        assert "переменная" in toks

    def test_cjk_identifier_normalizes_to_id(self):
        toks = tokenize("결과 = 더하기(첫번째, 두번째)", normalize=True)
        assert "ID" in toks
        assert "더하기" not in toks  # identifier flattened, not preserved


@requires_fixture
class TestUnicodeReports:
    def _run(self, tmp_path, **kw):
        from diffinite.pipeline import run_pipeline
        out_md = tmp_path / "uni.md"
        out_html = tmp_path / "uni.html"
        run_pipeline(
            dir_a=str(_UNI / "left"), dir_b=str(_UNI / "right"),
            report_md=str(out_md), report_html=str(out_html), **kw,
        )
        return (out_md.read_text(encoding="utf-8"),
                out_html.read_text(encoding="utf-8"))

    def test_non_ascii_filenames_render(self, tmp_path):
        md, html = self._run(tmp_path)
        assert "日本語.java" in md and "계산기.py" in md
        # The HTML report declares UTF-8 and carries the CJK source in its body.
        assert '<meta charset="utf-8">' in html
        assert "더하기" in html or "합계" in html

    def test_deep_normalize_runs_and_preserves_unicode(self, tmp_path):
        # The heavy path: deep + normalize on Unicode input must not crash, must
        # carry the FP disclosure (MD summary), and keep non-ASCII filenames.
        md, html = self._run(tmp_path, exec_mode="deep", normalize=True, workers=1)
        assert "false-positive" in md.lower()      # disclosure present
        assert "계산기.py" in md                    # filename survives
        assert "더하기" in html or "합계" in html    # CJK identifier in HTML body
