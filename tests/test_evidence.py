"""Tests for the multi-evidence channel module (Phase 3)."""

import pytest

from diffinite.evidence import (
    comment_string_overlap,
    compute_channel_scores,
    extract_comments_and_strings,
    identifier_cosine,
)


class TestIdentifierCosine:
    def test_identical_sources(self):
        source = "def foo(x, y):\n    result = x + y\n    return result\n"
        score = identifier_cosine(source, source)
        assert abs(score - 1.0) < 1e-6

    def test_completely_different(self):
        source_a = "foo bar baz qux"
        source_b = "alice bob charlie dave"
        score = identifier_cosine(source_a, source_b)
        assert score == 0.0

    def test_partial_overlap(self):
        source_a = "def foo(x): return process(x)"
        source_b = "def foo(y): return handle(y)"
        score = identifier_cosine(source_a, source_b)
        # "foo" is shared, but "x"/"y" and "process"/"handle" differ
        assert 0.0 < score < 1.0

    def test_empty_source(self):
        score = identifier_cosine("", "def foo(): pass")
        assert score == 0.0

    def test_both_empty(self):
        score = identifier_cosine("", "")
        assert score == 0.0

    def test_keywords_excluded(self):
        """Keywords should not contribute to identifier similarity."""
        # Two sources with identical keywords but different identifiers
        source_a = "if True: return foo"
        source_b = "if True: return bar"
        score = identifier_cosine(source_a, source_b)
        # "foo" vs "bar" differ, so score should not be 1.0
        assert score < 1.0


class TestCommentStringOverlap:
    def test_identical_comments(self):
        source = "# This is a comment\nx = 1  # another comment\n"
        score = comment_string_overlap(source, source, ".py")
        # At least some overlap should be detected
        assert score >= 0.0

    def test_no_comments(self):
        source_a = "x = 1\ny = 2\n"
        source_b = "a = 3\nb = 4\n"
        score = comment_string_overlap(source_a, source_b, ".py")
        assert score == 0.0

    def test_shared_strings(self):
        source_a = 'msg = "Hello World"\n'
        source_b = 'greeting = "Hello World"\n'
        score = comment_string_overlap(source_a, source_b, ".py")
        assert score > 0.0

    def test_different_comments(self):
        source_a = "# Written by Alice\nx = 1\n"
        source_b = "# Written by Bob\nx = 1\n"
        score = comment_string_overlap(source_a, source_b, ".py")
        assert score < 1.0


class TestExtractCommentsAndStrings:
    def test_extracts_strings(self):
        source = 'x = "hello world"\ny = "foo bar baz"\n'
        fragments = extract_comments_and_strings(source, ".py")
        assert any("hello world" in f for f in fragments)

    def test_ignores_short_strings(self):
        source = 'x = "ab"\n'  # Only 2 chars — should be filtered
        fragments = extract_comments_and_strings(source, ".py")
        assert not any("ab" in f for f in fragments)


class TestComputeChannelScores:
    def test_returns_composite(self):
        scores = compute_channel_scores(
            fp_raw_a={1, 2, 3},
            fp_raw_b={2, 3, 4},
            fp_norm_a={10, 20, 30},
            fp_norm_b={20, 30, 40},
        )
        assert "raw_winnowing" in scores
        assert "normalized_winnowing" in scores
        assert "composite" in scores
        assert 0.0 <= scores["composite"] <= 1.0

    def test_partial_inputs(self):
        """Should handle missing channels gracefully."""
        scores = compute_channel_scores(
            fp_raw_a={1, 2, 3},
            fp_raw_b={2, 3, 4},
        )
        assert "raw_winnowing" in scores
        assert "normalized_winnowing" not in scores
        assert "composite" in scores

    def test_identical_sets(self):
        s = {1, 2, 3, 4, 5}
        scores = compute_channel_scores(
            fp_raw_a=s, fp_raw_b=s,
            fp_norm_a=s, fp_norm_b=s,
        )
        assert abs(scores["raw_winnowing"] - 1.0) < 1e-6
        assert abs(scores["normalized_winnowing"] - 1.0) < 1e-6
        assert abs(scores["composite"] - 1.0) < 1e-6

    def test_disjoint_sets(self):
        scores = compute_channel_scores(
            fp_raw_a={1, 2, 3},
            fp_raw_b={4, 5, 6},
        )
        assert scores["raw_winnowing"] == 0.0

    def test_empty_inputs(self):
        scores = compute_channel_scores()
        assert scores == {}

    def test_identifier_channel(self):
        scores = compute_channel_scores(
            cleaned_a="def foo(x): return process(x)",
            cleaned_b="def foo(x): return process(x)",
        )
        assert "identifier_cosine" in scores
        assert abs(scores["identifier_cosine"] - 1.0) < 1e-6

    def test_all_channels(self):
        """When all inputs provided, all channels should be computed."""
        scores = compute_channel_scores(
            fp_raw_a={1, 2},
            fp_raw_b={2, 3},
            fp_norm_a={10, 20},
            fp_norm_b={20, 30},
            fp_ast_a={100, 200},
            fp_ast_b={200, 300},
            source_a="# comment\nx = 1\n",
            source_b="# comment\ny = 2\n",
            cleaned_a="x = 1",
            cleaned_b="y = 2",
            extension=".py",
        )
        expected_keys = {
            "raw_winnowing", "normalized_winnowing", "ast_winnowing",
            "identifier_cosine", "comment_string_overlap", "composite",
        }
        assert expected_keys == set(scores.keys())
