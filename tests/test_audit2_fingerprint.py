"""Regression tests for the 2026-11-10 code audit, fingerprint/deep-compare group.

Findings covered: #2, #20, #21, #22, #45 (deep side), #47, #48, #49, #50, #51, #52.
"""

from __future__ import annotations

import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pytest

import diffinite.deep_compare as dc
from diffinite.fingerprint import (
    TIER1_PREFIX,
    TIER2_PREFIX,
    extract_fingerprints,
    pygments_version,
    tokenize,
    tokenize_lang_aware,
)

pytest.importorskip("pygments")


def _jaccard(src_a: str, src_b: str, ext: str, **kw) -> float:
    a = {f.hash_value for f in extract_fingerprints(src_a, normalize=True, ext=ext, **kw)}
    b = {f.hash_value for f in extract_fingerprints(src_b, normalize=True, ext=ext, **kw)}
    return len(a & b) / len(a | b)


def _max_str_run(tokens: list[str]) -> int:
    best = run = 0
    for t in tokens:
        run = run + 1 if t == "STR" else 0
        best = max(best, run)
    return best


# ── #2: lexer chosen from the registry language ──────────────────────────
R_SRC = (
    "total <- function(values) {\n"
    "  result <- 0\n"
    "  for (v in values) { result <- result + v }\n"
    "  result\n"
    "}\n"
)
PERL_SRC = "sub total {\n  my @v = @_;\n  my $s = 0;\n  foreach my $x (@v) { $s += $x; }\n  return $s;\n}\n"


@pytest.mark.parametrize("ext", [".r", ".R"])
def test_r_uses_r_lexer_not_rebol(ext):
    toks, tier = tokenize_lang_aware(R_SRC, ext)
    assert tier.startswith(TIER2_PREFIX) and tier != TIER2_PREFIX + "rebol"
    assert "function" in toks and "for" in toks
    assert _max_str_run(toks) == 0  # REBOL turned the { } body into STR runs


@pytest.mark.parametrize("ext", [".pl", ".pm"])
def test_perl_uses_perl_lexer(ext):
    toks, tier = tokenize_lang_aware(PERL_SRC, ext)
    assert tier == TIER2_PREFIX + "perl"
    assert {"sub", "my", "foreach", "return"} <= set(toks)
    assert _max_str_run(toks) == 0


# ── #20: Token.Error falls back to Tier-1, observably ────────────────────
KOTLIN = (
    "fun 합계(목록: List<Int>): Int {\n    var 결과 = 0\n"
    "    for (값 in 목록) { 결과 = 결과 + 값 * 2 }\n    return 결과\n}\n"
)
KOTLIN_RENAMED = (
    "fun 총합(배열: List<Int>): Int {\n    var 누계 = 0\n"
    "    for (원소 in 배열) { 누계 = 누계 + 원소 * 2 }\n    return 누계\n}\n"
)
CSHARP = (
    "int 합계(int[] 목록) {\n    int 결과 = 0;\n"
    "    foreach (var 값 in 목록) { 결과 = 결과 + 값 * 2; }\n    return 결과;\n}\n"
)
CSHARP_RENAMED = (
    "int 총합(int[] 배열) {\n    int 누계 = 0;\n"
    "    foreach (var 원소 in 배열) { 누계 = 누계 + 원소 * 2; }\n    return 누계;\n}\n"
)
RUBY = "def 합계(목록)\n  결과 = 0\n  목록.each do |값|\n    결과 = 결과 + 값 * 2\n  end\n  결과\nend\n"
RUBY_RENAMED = "def 총합(배열)\n  누계 = 0\n  배열.each do |원소|\n    누계 = 누계 + 원소 * 2\n  end\n  누계\nend\n"


@pytest.mark.parametrize(
    "ext,src,renamed",
    [(".kt", KOTLIN, KOTLIN_RENAMED), (".cs", CSHARP, CSHARP_RENAMED), (".rb", RUBY, RUBY_RENAMED)],
)
def test_error_tokens_fall_back_and_renamed_clone_matches(ext, src, renamed, caplog):
    with caplog.at_level("WARNING", logger="diffinite.fingerprint"):
        toks, tier = tokenize_lang_aware(src, ext)
    # No Hangul syllable survives as a raw token.
    assert not any(any("가" <= ch <= "힣" for ch in t) for t in toks)
    assert _jaccard(src, renamed, ext, lang_aware=True) == 1.0
    if tier.startswith(TIER1_PREFIX):
        assert tier == TIER1_PREFIX + "lexer-error-token"
        assert "lexer-error-token" in caplog.text


def test_kotlin_hangul_tier_is_reported_as_fallback():
    _toks, tier = tokenize_lang_aware("val 가격 = 수량 * 2\n", ".kt")
    assert tier == TIER1_PREFIX + "lexer-error-token"


# ── #21: keyword case folding for case-insensitive languages ─────────────
SQL_UPPER = "SELECT id, name FROM users WHERE id = 1 ORDER BY name;\nUPDATE users SET name = 'x' WHERE id = 2;\n"


def test_sql_keyword_case_folded_tier2():
    upper, tier = tokenize_lang_aware(SQL_UPPER, ".sql")
    lower, _ = tokenize_lang_aware(SQL_UPPER.lower(), ".sql")
    assert tier.startswith(TIER2_PREFIX)
    assert upper == lower
    assert "select" in upper


def test_sql_keyword_case_folded_tier1():
    # .ddl is registered as SQL but has no Pygments lexer -> Tier-1 path.
    upper, tier = tokenize_lang_aware(SQL_UPPER, ".ddl")
    lower, _ = tokenize_lang_aware(SQL_UPPER.lower(), ".ddl")
    assert tier.startswith(TIER1_PREFIX)
    assert upper == lower
    assert "select" in upper and "from" in upper


def test_case_sensitive_language_keeps_keyword_case():
    toks, _ = tokenize_lang_aware("def f(x):\n    return x\n", ".py")
    assert "def" in toks and "return" in toks


# ── #47: NFC and combining marks inside identifiers ──────────────────────
def test_combining_marks_stay_in_identifier():
    assert tokenize("नमस्ते = 1", normalize=True) == ["ID", "=", "LIT"]
    assert tokenize("नमस्ते = 1") == ["नमस्ते", "=", "1"]


def test_nfc_and_nfd_tokenize_identically():
    nfc = "café = 1"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert tokenize(nfd) == tokenize(nfc)
    assert tokenize(nfd, normalize=True) == tokenize(nfc, normalize=True) == ["ID", "=", "LIT"]
    assert tokenize_lang_aware(nfd, ".py") == tokenize_lang_aware(nfc, ".py")


def test_letter_number_is_identifier():
    assert tokenize("Ⅻ = 1", normalize=True) == ["ID", "=", "LIT"]


def test_devanagari_renamed_clone_matches():
    src = "def जोड़(संख्या):\n    परिणाम = संख्या + 1\n    return परिणाम\n"
    renamed = "def add(number):\n    result = number + 1\n    return result\n"
    assert _jaccard(src, renamed, ".py") == 1.0


# ── #48: Pygments version and tier exposed ───────────────────────────────
def test_pygments_version_exposed():
    import pygments

    assert pygments_version() == pygments.__version__


def test_tier_reported():
    assert tokenize_lang_aware("x = 1\n", ".py")[1] == TIER2_PREFIX + "python"
    assert tokenize_lang_aware("x = 1\n", None)[1] == TIER1_PREFIX + "no-extension"


# ── #49: one STR per contiguous string ───────────────────────────────────
def test_string_escapes_do_not_change_str_count():
    a, _ = tokenize_lang_aware("s = 'a\\nb\\tc\\rd'\n", ".py")
    b, _ = tokenize_lang_aware("s = 'ab'\n", ".py")
    assert a == b == ["ID", "=", "STR"]


def test_escape_heavy_strings_do_not_create_all_str_kgrams():
    toks, _ = tokenize_lang_aware('char *s = "a\\nb\\tc\\rd\\ve\\af";\n', ".c")
    assert toks.count("STR") == 1


def test_interpolation_splits_string_runs():
    toks, _ = tokenize_lang_aware("s = f'x{y}z'\n", ".py")
    assert toks == ["ID", "=", "STR", "ID", "STR"]


# ── run_deep_compare helpers (in-process thread pool, so monkeypatch applies) ──
class _ThreadPool(ThreadPoolExecutor):
    max_workers_seen: list[int] = []

    def __init__(self, max_workers=None, mp_context=None, initializer=None):
        type(self).max_workers_seen.append(max_workers)
        super().__init__(max_workers=max_workers)


@pytest.fixture
def thread_pool(monkeypatch):
    _ThreadPool.max_workers_seen = []
    monkeypatch.setattr(dc, "ProcessPoolExecutor", _ThreadPool)
    return _ThreadPool


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


# ── #22: unregistered undecodable files are never counted as success ─────
def _item(path, rel, ext=None):
    ext = ext if ext is not None else "." + rel.rsplit(".", 1)[-1]
    return ("A", str(path), rel, ext, 5, 4, False, False, 0, False, None, ext)


def test_unregistered_undecodable_is_explicit_skip(tmp_path, monkeypatch):
    f = tmp_path / "Comp.vue"
    f.write_bytes(b"\xff\xfe template")
    monkeypatch.setattr(dc, "read_file", lambda *a, **k: None)
    res = dc._extract_one(_item(f, "Comp.vue"))
    assert res[5] == dc.SKIPPED_UNDECODABLE_REASON


def test_unregistered_unreadable_is_failure(tmp_path):
    res = dc._extract_one(_item(tmp_path / "gone.jsp", "gone.jsp"))
    assert res[5] == "decode-or-read-failure"


def test_undecodable_skip_is_disclosed_and_not_successful(tmp_path, monkeypatch, thread_pool):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "Comp.vue", b"opaque")
    _write(b, "x.py", "def f(a):\n    return a + 1\n")
    real = dc.read_file
    monkeypatch.setattr(
        dc, "read_file", lambda p, **k: None if p.endswith("Comp.vue") else real(p, **k))
    status: dict = {}
    dc.run_deep_compare(str(a), str(b), ["Comp.vue"], ["x.py"], workers=1, status=status)
    assert status["successful_file_count"] == 1
    assert status["skipped_binary_files"] == [
        {"side": "A", "path": "Comp.vue", "reason": dc.SKIPPED_UNDECODABLE_REASON}]
    assert status["failed_files"] == []


def test_missing_unregistered_file_fails_run(tmp_path, thread_pool):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    _write(b, "x.py", "def f(a):\n    return a + 1\n")
    with pytest.raises(RuntimeError, match="gone.jsp"):
        dc.run_deep_compare(str(a), str(b), ["gone.jsp"], ["x.py"], workers=1)


# ── #51: files below k tokens are recorded ───────────────────────────────
def test_below_k_files_recorded(tmp_path, thread_pool):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "tiny.c", "return x;\n")
    _write(b, "tiny.c", "return x;\n")
    status: dict = {}
    res = dc.run_deep_compare(str(a), str(b), ["tiny.c"], ["tiny.c"], workers=1, status=status)
    assert res == []
    assert status["unfingerprinted_files"] == [
        {"side": "A", "path": "tiny.c", "reason": dc.BELOW_KGRAM_REASON},
        {"side": "B", "path": "tiny.c", "reason": dc.BELOW_KGRAM_REASON},
    ]


# ── #50: exact Jaccard is kept ───────────────────────────────────────────
def test_near_identical_jaccard_not_rounded_to_one(tmp_path, monkeypatch, thread_pool):
    big = set(range(100_000))
    near = (big - {0}) | {10**9}

    def fake(item):
        side, _abs, rel = item[:3]
        hs = big if (side == "A" or rel == "same.c") else near
        return side, rel, hs, len(hs), 1000, None, None

    monkeypatch.setattr(dc, "_extract_one", fake)
    res = dc.run_deep_compare(
        str(tmp_path), str(tmp_path), ["a.c"], ["near.c", "same.c"], workers=1)
    matches = res[0].matched_files_b
    assert [m[0] for m in matches] == ["same.c", "near.c"]
    assert matches[0][2] == 1.0
    assert matches[1][2] == 99_999 / 100_001
    assert matches[1][2] < 1.0


# ── #52: Windows worker clamp ────────────────────────────────────────────
@pytest.mark.parametrize("platform,expected", [("win32", 61), ("linux", 64)])
def test_workers_clamped_on_windows(tmp_path, monkeypatch, thread_pool, platform, expected):
    _write(tmp_path / "a", "x.py", "def f(a):\n    return a + 1\n")
    _write(tmp_path / "b", "x.py", "def f(a):\n    return a + 1\n")
    monkeypatch.setattr(sys, "platform", platform)
    dc.run_deep_compare(
        str(tmp_path / "a"), str(tmp_path / "b"), ["x.py"], ["x.py"], workers=64)
    assert thread_pool.max_workers_seen == [expected]


# ── #45 (deep side): pair-aware comment rules ────────────────────────────
JAVA_COMMENTED = "".join(
    f"// helper number {i} explained at length here\nint f{i}(int a) {{ return a * {i} + 1; }}\n"
    for i in range(20)
)
JAVA_PLAIN = "".join(f"int f{i}(int a) {{ return a * {i} + 1; }}\n" for i in range(20))


def test_unregistered_side_borrows_partner_comment_rules(tmp_path, thread_pool):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "Foo.orig", JAVA_COMMENTED)
    _write(b, "Foo.java", JAVA_PLAIN)

    status: dict = {}
    res = dc.run_deep_compare(
        str(a), str(b), ["Foo.orig"], ["Foo.java"], workers=1, strip_comments=True,
        min_jaccard=0.0, status=status, comment_pairs=[("Foo.orig", "Foo.java")])
    assert res[0].matched_files_b[0][2] == 1.0
    assert status["comment_unstripped_extensions"] == []

    status2: dict = {}
    res2 = dc.run_deep_compare(
        str(a), str(b), ["Foo.orig"], ["Foo.java"], workers=1, strip_comments=True,
        min_jaccard=0.0, status=status2)
    assert not res2 or res2[0].matched_files_b[0][2] < 1.0
    assert status2["comment_unstripped_extensions"] == [".orig"]


# ── #48 / #20: lang-aware tiers recorded in the deep status ──────────────
def test_lang_aware_tiers_in_status(tmp_path, thread_pool):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "x.kt", KOTLIN)
    _write(b, "y.py", "def f(a):\n    return a + 1\n")
    status: dict = {}
    dc.run_deep_compare(
        str(a), str(b), ["x.kt"], ["y.py"], workers=1, normalize=True, lang_aware=True,
        status=status)
    assert status["lang_aware_tiers"][".py"] == [TIER2_PREFIX + "python"]
    assert status["lang_aware_tiers"][".kt"] == [TIER1_PREFIX + "lexer-error-token"]
    assert status["lang_aware_fallback_files"] == [
        {"side": "A", "path": "x.kt", "tier": TIER1_PREFIX + "lexer-error-token"}]
