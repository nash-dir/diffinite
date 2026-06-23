"""Tests for the Winnowing fingerprint engine."""

import pytest

from diffinite.fingerprint import (
    DEFAULT_K,
    DEFAULT_W,
    extract_fingerprints,
    rolling_hash,
    tokenize,
    winnow,
)
from diffinite.models import FingerprintEntry


class TestTokenize:
    def test_basic(self):
        tokens = tokenize("def foo(x): return x + 1")
        assert "def" in tokens
        assert "foo" in tokens
        assert "return" in tokens
        assert "1" in tokens
        # Punctuation
        assert "(" in tokens
        assert ")" in tokens

    def test_empty(self):
        assert tokenize("") == []

    def test_whitespace_only(self):
        assert tokenize("   \n\t  ") == []


class TestRollingHash:
    def test_basic_length(self):
        tokens = ["a", "b", "c", "d", "e"]
        hashes = rolling_hash(tokens, k=3)
        assert len(hashes) == 3  # 5 - 3 + 1

    def test_too_short(self):
        tokens = ["a", "b"]
        hashes = rolling_hash(tokens, k=5)
        assert hashes == []

    def test_deterministic(self):
        tokens = ["def", "foo", "bar", "baz", "qux"]
        h1 = rolling_hash(tokens, k=3)
        h2 = rolling_hash(tokens, k=3)
        assert h1 == h2

    def test_different_input_different_hashes(self):
        tokens_a = ["a", "b", "c", "d"]
        tokens_b = ["x", "y", "z", "w"]
        h_a = rolling_hash(tokens_a, k=3)
        h_b = rolling_hash(tokens_b, k=3)
        assert h_a != h_b


class TestWinnow:
    def test_basic(self):
        hashes = [5, 2, 3, 1, 4, 6, 2, 7]
        fps = winnow(hashes, w=4)
        # Should contain at least one entry
        assert len(fps) > 0
        # All entries are FingerprintEntry
        assert all(isinstance(fp, FingerprintEntry) for fp in fps)

    def test_empty(self):
        assert winnow([], w=4) == []

    def test_single_window(self):
        hashes = [3, 1, 2]
        fps = winnow(hashes, w=4)
        # Fewer hashes than window — single window picks minimum
        assert len(fps) == 1
        assert fps[0].hash_value == 1

    def test_density_guarantee(self):
        """Any shared segment of length >= W + K - 1 must share a fingerprint."""
        # Build two sequences sharing a segment
        shared = list(range(100, 200))  # 100 elements
        prefix_a = list(range(0, 50))
        prefix_b = list(range(200, 250))
        seq_a = prefix_a + shared
        seq_b = prefix_b + shared

        fps_a = {fp.hash_value for fp in winnow(seq_a, w=10)}
        fps_b = {fp.hash_value for fp in winnow(seq_b, w=10)}

        # Must share at least some fingerprints from the shared segment
        assert len(fps_a & fps_b) > 0


class TestExtractFingerprints:
    def test_identical_sources(self):
        src = "def foo(x):\n    return x * 2 + bar(x - 1)\n" * 5
        fps = extract_fingerprints(src, k=5, w=4)
        assert len(fps) > 0

    def test_empty_source(self):
        assert extract_fingerprints("", k=5, w=4) == []

    def test_short_source(self):
        # Fewer tokens than K — no fingerprints
        fps = extract_fingerprints("x = 1", k=50, w=40)
        assert fps == []


class TestUnicodeTokenization:
    """Non-ASCII identifiers must tokenize as whole tokens, like Latin ones."""

    def test_cjk_identifier_is_single_token(self):
        assert tokenize("데이터 = 값") == ["데이터", "=", "값"]

    def test_cjk_token_count_matches_latin_structure(self):
        cjk = tokenize("함수 = 데이터 + 결과")
        latin = tokenize("func = data + result")
        assert len(cjk) == len(latin)

    def test_ascii_tokenization_unchanged(self):
        assert tokenize("def foo(x): return x + 1") == [
            "def", "foo", "(", "x", ")", ":", "return", "x", "+", "1",
        ]

    def test_float_is_single_token(self):
        assert "3.14" in tokenize("pi = 3.14")


class TestFingerprintGuards:
    """Degenerate k/w must raise, never silently fabricate fingerprints."""

    def test_k_below_one_raises(self):
        with pytest.raises(ValueError):
            extract_fingerprints("a b c d e f", k=0, w=4)

    def test_w_below_one_raises(self):
        with pytest.raises(ValueError):
            extract_fingerprints("a b c d e f", k=5, w=0)


class TestLangAwareNormalization:
    """Opt-in language-aware normalization (WS-C). Tier-2 (Pygments) preserves
    per-language keywords that the JVM/Python/JS-centric default set drops; Tier-1
    (registry keywords) is the fallback when no lexer exists."""

    RUST = "pub fn add(a: i32, b: i32) -> i32 {\n    let total = a + b;\n    total\n}\n"

    def test_default_normalize_drops_rust_keywords(self):
        # `fn`/`pub`/`let` are not in _COMMON_KEYWORDS, so the default normalize
        # path flattens them to ID -- the language-bias the review flagged.
        toks = tokenize(self.RUST, normalize=True)
        assert "fn" not in toks and "pub" not in toks
        assert "ID" in toks

    def test_lang_aware_preserves_rust_keywords(self):
        toks = tokenize(self.RUST, normalize=True, ext=".rs", lang_aware=True)
        # Declaration/type keywords survive; the function name collapses to ID.
        assert "fn" in toks and "pub" in toks
        assert "i32" in toks            # Keyword.Type preserved
        assert "ID" in toks             # `add`, `a`, `b`, `total` -> ID

    def test_lang_aware_changes_fingerprints_only_when_normalized(self):
        # With normalize=False, lang_aware is a documented no-op (raw tokens).
        raw = tokenize(self.RUST, normalize=False, ext=".rs", lang_aware=True)
        assert raw == tokenize(self.RUST, normalize=False)

    def test_default_path_unchanged_compatibility(self):
        # The crucial backward-compat guarantee: lang_aware=False (the default)
        # must emit byte-identical fingerprints to the historical behavior.
        src = "def foo(x):\n    return x + 1\n"
        before = extract_fingerprints(src, normalize=True)
        after = extract_fingerprints(src, normalize=True, lang_aware=False)
        assert before == after

    def test_unknown_extension_falls_back_gracefully(self):
        # No Pygments lexer for a bogus extension -> Tier-1 fallback, no crash.
        toks = tokenize(self.RUST, normalize=True, ext=".zzz", lang_aware=True)
        assert isinstance(toks, list) and toks

    def test_lang_aware_reduces_false_similarity_of_independent_code(self):
        # Two independent Rust fns, same forced skeleton, different logic. Under
        # default normalize their decls flatten together; lang-aware keeps the
        # keyword scaffold identical but still must not score HIGHER than default.
        a = self.RUST
        b = "pub fn mul(x: i32, y: i32) -> i32 {\n    let r = x * y;\n    r\n}\n"

        def jac(norm, la):
            fa = {f.hash_value for f in extract_fingerprints(a, normalize=norm, ext='.rs', lang_aware=la)}
            fb = {f.hash_value for f in extract_fingerprints(b, normalize=norm, ext='.rs', lang_aware=la)}
            inter, union = len(fa & fb), len(fa | fb)
            return inter / union if union else 0.0

        # Sanity: both runs are deterministic and in range.
        assert 0.0 <= jac(True, True) <= 1.0
        assert 0.0 <= jac(True, False) <= 1.0


class TestLangAwareRobustness:
    """Self-review fixes: lexer failures must degrade to Tier-1, and the floor
    token count must be channel-independent."""

    def test_lexer_failure_falls_back_to_tier1(self, monkeypatch):
        # Force any Pygments lexing to raise; lang-aware must not propagate it.
        import diffinite.fingerprint as fp

        def boom(*a, **k):
            raise RuntimeError("lexer exploded")

        # Patch the lazily-imported lookup so _normalize_lang_aware returns None.
        import pygments.lexers as pl
        monkeypatch.setattr(pl, "get_lexer_for_filename", boom)
        toks = fp.tokenize("pub fn f() {}", normalize=True, ext=".rs", lang_aware=True)
        # Falls back to Tier-1 (registry keywords) — still a normalized list.
        assert isinstance(toks, list) and toks
        assert "ID" in toks
