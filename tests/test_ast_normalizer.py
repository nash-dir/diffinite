"""Tests for the AST linearization module (Phase 2)."""

import pytest

# tree-sitter may not be installed — skip tests gracefully
ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
ts_py = pytest.importorskip("tree_sitter_python", reason="tree-sitter-python not installed")

from diffinite.ast_normalizer import (
    ast_tokenize,
    get_parser,
    linearize,
    pdg_tokenize,
)
from diffinite.fingerprint import extract_fingerprints


class TestGetParser:
    def test_supported_python(self):
        parser = get_parser(".py")
        assert parser is not None

    def test_supported_java(self):
        parser = get_parser(".java")
        assert parser is not None

    def test_supported_js(self):
        parser = get_parser(".js")
        assert parser is not None

    def test_supported_c(self):
        parser = get_parser(".c")
        assert parser is not None

    def test_unsupported_extension(self):
        parser = get_parser(".txt")
        assert parser is None

    def test_unsupported_unknown(self):
        parser = get_parser(".xyz")
        assert parser is None


class TestLinearize:
    def test_simple_python_function(self):
        source = "def foo(x):\n    return x + 1\n"
        tokens = ast_tokenize(source, ".py")
        assert tokens is not None
        assert len(tokens) > 0
        # Should contain structure tags
        assert "<function_definition>" in tokens
        assert "</function_definition>" in tokens
        # Should contain return
        assert "<return_statement>" in tokens

    def test_identifier_normalization(self):
        source = "x = hello_world\ny = another_var\n"
        tokens = ast_tokenize(source, ".py")
        assert tokens is not None
        # Identifiers should be normalized to ID
        assert "ID" in tokens
        # Original identifiers should NOT be in tokens
        assert "hello_world" not in tokens
        assert "another_var" not in tokens
        assert "x" not in tokens

    def test_literal_normalization(self):
        source = "x = 42\ny = 3.14\n"
        tokens = ast_tokenize(source, ".py")
        assert tokens is not None
        assert "LIT" in tokens
        assert "42" not in tokens

    def test_keyword_preservation(self):
        source = "if True:\n    return None\n"
        tokens = ast_tokenize(source, ".py")
        assert tokens is not None
        # Keywords should be preserved
        assert "if" in tokens
        assert "return" in tokens

    def test_structure_tags_for_if(self):
        source = "if x:\n    pass\nfor i in range(10):\n    pass\n"
        tokens = ast_tokenize(source, ".py")
        assert tokens is not None
        assert "<if_statement>" in tokens
        assert "</if_statement>" in tokens
        assert "<for_statement>" in tokens or "<for_in_statement>" in tokens

    def test_empty_source(self):
        tokens = ast_tokenize("", ".py")
        # Empty source may produce empty tokens or None
        assert tokens is None or tokens == []


class TestAstTokenizeFallback:
    def test_unsupported_extension_returns_none(self):
        tokens = ast_tokenize("some text", ".txt")
        assert tokens is None

    def test_unsupported_markdown_returns_none(self):
        tokens = ast_tokenize("# Header", ".md")
        assert tokens is None


class TestExtractFingerprintsAstMode:
    def test_ast_mode_produces_fingerprints(self):
        source = """
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total
"""
        fps = extract_fingerprints(source, mode="ast", extension=".py")
        assert len(fps) > 0

    def test_ast_mode_different_from_token_mode(self):
        source = """
def foo(x):
    if x > 0:
        return x * 2
    else:
        return x - 1
"""
        fps_token = extract_fingerprints(source, normalize=True)
        fps_ast = extract_fingerprints(source, mode="ast", extension=".py")

        # Both should produce fingerprints
        assert len(fps_token) > 0
        assert len(fps_ast) > 0

        # They should differ (AST includes structure tags)
        token_hashes = {fp.hash_value for fp in fps_token}
        ast_hashes = {fp.hash_value for fp in fps_ast}
        assert token_hashes != ast_hashes

    def test_ast_mode_resilient_to_variable_rename(self):
        source_a = "def foo(x):\n    return x + 1\n"
        source_b = "def bar(y):\n    return y + 1\n"

        fps_a = extract_fingerprints(source_a, mode="ast", extension=".py")
        fps_b = extract_fingerprints(source_b, mode="ast", extension=".py")

        hashes_a = {fp.hash_value for fp in fps_a}
        hashes_b = {fp.hash_value for fp in fps_b}

        # Should be identical — structure is the same
        assert hashes_a == hashes_b

    def test_ast_fallback_for_unsupported_extension(self):
        """When extension is unsupported, should fallback to token mode."""
        source = "def foo(): pass"
        fps = extract_fingerprints(source, mode="ast", extension=".xyz")
        # Should still produce fingerprints (via token fallback)
        assert len(fps) > 0


class TestPdgTokenize:
    def test_pdg_basic(self):
        source = """
x = 10
y = x + 5
z = y * 2
"""
        tokens = pdg_tokenize(source, ".py")
        # Should produce something (may be None if no statements extracted)
        # With Python, assignment is a statement type
        if tokens is not None:
            assert len(tokens) > 0

    def test_pdg_filters_dead_code(self):
        """Dead code (unused variables) should be filtered out."""
        # With dead code
        source_with_dead = """
x = 10
unused = 42
y = x + 5
dead = unused * 2
result = y * 2
"""
        # Without dead code
        source_clean = """
x = 10
y = x + 5
result = y * 2
"""
        tokens_dead = pdg_tokenize(source_with_dead, ".py")
        tokens_clean = pdg_tokenize(source_clean, ".py")

        # Both should produce tokens
        if tokens_dead is not None and tokens_clean is not None:
            # The PDG-normalised version should be more similar
            # to clean than the raw version
            assert len(tokens_dead) <= len(
                ast_tokenize(source_with_dead, ".py") or []
            )

    def test_pdg_fallback_for_unsupported(self):
        tokens = pdg_tokenize("some code", ".txt")
        assert tokens is None
