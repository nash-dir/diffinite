"""Tests for the language specification registry.

Validates that the new ``diffinite.languages`` package matches the
existing hardcoded data in ``parser.py``, ``fingerprint.py``, and
``ast_normalizer.py``, ensuring zero regression during migration.
"""

import pytest

# ── Import the old hardcoded data for comparison ──────────────────
from diffinite.parser import COMMENT_SPECS, _C_FAMILY_EXTS
from diffinite.fingerprint import _COMMON_KEYWORDS
from diffinite.ast_normalizer import _LANG_MAP

# ── Import the new registry API ──────────────────────────────────
from diffinite.languages import (
    LangSpec,
    get_spec,
    all_extensions,
    all_keywords,
    all_specs,
)
from diffinite.languages._registry import _REGISTRY


class TestRegistryCompleteness:
    """Verify the registry covers all previously-hardcoded extensions."""

    def test_all_comment_spec_extensions_registered(self):
        """Every extension in the old COMMENT_SPECS dict must exist
        in the new registry."""
        registered = set(all_extensions())
        for ext in COMMENT_SPECS:
            assert ext in registered, (
                f"Extension {ext!r} from COMMENT_SPECS is missing from "
                f"the language registry"
            )

    def test_all_lang_map_extensions_registered(self):
        """Every extension in the old _LANG_MAP must be in the registry."""
        registered = set(all_extensions())
        for ext in _LANG_MAP:
            assert ext in registered, (
                f"Extension {ext!r} from _LANG_MAP is missing from "
                f"the language registry"
            )


class TestCommentSpecParity:
    """Verify comment specs match the old hardcoded data."""

    @pytest.mark.parametrize("ext", list(COMMENT_SPECS.keys()))
    def test_comment_spec_matches(self, ext: str):
        spec = get_spec(ext)
        assert spec is not None, f"No LangSpec for {ext!r}"
        old = COMMENT_SPECS[ext]
        assert spec.comment.line_markers == old.line_markers, (
            f"{ext}: line_markers mismatch: "
            f"{spec.comment.line_markers!r} != {old.line_markers!r}"
        )
        assert spec.comment.block_start == old.block_start, (
            f"{ext}: block_start mismatch"
        )
        assert spec.comment.block_end == old.block_end, (
            f"{ext}: block_end mismatch"
        )


class TestIfdefZeroParity:
    """Verify has_ifdef_zero matches old _C_FAMILY_EXTS."""

    @pytest.mark.parametrize("ext", list(_C_FAMILY_EXTS))
    def test_ifdef_zero_flag(self, ext: str):
        spec = get_spec(ext)
        assert spec is not None, f"No LangSpec for {ext!r}"
        assert spec.has_ifdef_zero is True, (
            f"{ext}: expected has_ifdef_zero=True"
        )


class TestKeywordsParity:
    """Verify keyword superset relationship."""

    def test_all_keywords_superset_of_old(self):
        """all_keywords() must be a superset of the old _COMMON_KEYWORDS."""
        new_kw = all_keywords()
        missing = _COMMON_KEYWORDS - new_kw
        assert not missing, (
            f"Old keywords missing from registry: {missing}"
        )


class TestTreeSitterParity:
    """Verify tree-sitter module mappings match old _LANG_MAP."""

    @pytest.mark.parametrize("ext", list(_LANG_MAP.keys()))
    def test_tree_sitter_mapping(self, ext: str):
        spec = get_spec(ext)
        assert spec is not None, f"No LangSpec for {ext!r}"
        old_module, old_func = _LANG_MAP[ext]
        assert spec.tree_sitter_module == old_module, (
            f"{ext}: tree_sitter_module mismatch: "
            f"{spec.tree_sitter_module!r} != {old_module!r}"
        )
        assert spec.tree_sitter_func == old_func, (
            f"{ext}: tree_sitter_func mismatch: "
            f"{spec.tree_sitter_func!r} != {old_func!r}"
        )


class TestRegistryIntegrity:
    """Registry invariants."""

    def test_no_empty_registry(self):
        assert len(all_extensions()) > 0

    def test_specs_are_frozen(self):
        for spec in all_specs():
            assert isinstance(spec, LangSpec)
            # LangSpec is frozen=True, so assignment should fail
            with pytest.raises(AttributeError):
                spec.name = "Modified"  # type: ignore[misc]

    def test_duplicate_extension_raises(self):
        """Registering the same extension twice must raise ValueError."""
        from diffinite.languages._registry import register
        from diffinite.models import CommentSpec as CS

        dummy = LangSpec(
            name="Duplicate",
            extensions=(".py",),  # already registered
            comment=CS(line_markers=("#",)),
        )
        with pytest.raises(ValueError, match="already registered"):
            register(dummy)
