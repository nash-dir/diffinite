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
