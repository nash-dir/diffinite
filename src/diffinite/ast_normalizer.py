"""AST-based token linearization via tree-sitter.

Parses source code into an Abstract Syntax Tree using tree-sitter, then
linearizes the tree into a token sequence suitable for the existing
Winnowing fingerprint pipeline.

The linearization preserves **structural information** by emitting
open/close tags for internal nodes (e.g. ``<for_statement>``,
``</for_statement>``).  Leaf nodes are normalised:

* Identifiers → ``"ID"``
* Numeric literals → ``"LIT"``
* String literals → ``"STR"``
* Keywords and operators → preserved as-is

This makes the resulting fingerprints resilient to both identifier
renaming (Type-2 clones) and superficial structural shuffling
(reduces Type-3 false positives).

When tree-sitter grammars are not available for a given language,
the module returns ``None`` so callers can **fall back** to Phase 1
Token Normalization seamlessly.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — tree-sitter is an optional dependency
# ---------------------------------------------------------------------------
try:
    import tree_sitter as _ts

    _TS_AVAILABLE = True
except ImportError:
    _ts = None  # type: ignore[assignment]
    _TS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Extension → tree-sitter language mapping  (delegated to language registry)
# ---------------------------------------------------------------------------
from diffinite.languages import get_spec  # noqa: E402
from diffinite.languages._defaults import (
    DEFAULT_IDENTIFIER_TYPES,
    DEFAULT_LITERAL_TYPES,
    DEFAULT_STRING_TYPES,
    DEFAULT_STRUCTURE_NODE_TYPES,
    DEFAULT_STATEMENT_TYPES,
)

# Legacy aliases — backward compatibility for any external imports
_LANG_MAP: dict[str, tuple[str, str]] = {}


def _build_legacy_lang_map() -> dict[str, tuple[str, str]]:
    """Build old-style _LANG_MAP from registry for backward compat."""
    from diffinite.languages import all_extensions
    result: dict[str, tuple[str, str]] = {}
    for ext in all_extensions():
        spec = get_spec(ext)
        if spec and spec.tree_sitter_module:
            result[ext] = (spec.tree_sitter_module, spec.tree_sitter_func)
    return result


# Populate at import time
_LANG_MAP.update(_build_legacy_lang_map())

# Default node type sets — imported from _defaults.py
_IDENTIFIER_TYPES = DEFAULT_IDENTIFIER_TYPES
_LITERAL_TYPES = DEFAULT_LITERAL_TYPES
_STRING_TYPES = DEFAULT_STRING_TYPES
_STRUCTURE_NODE_TYPES = DEFAULT_STRUCTURE_NODE_TYPES


def _get_identifier_types(ext: str) -> frozenset[str]:
    """Get identifier node types, with per-language override support."""
    spec = get_spec(ext)
    if spec and spec.identifier_types is not None:
        return spec.identifier_types
    return DEFAULT_IDENTIFIER_TYPES


def _get_literal_types(ext: str) -> frozenset[str]:
    spec = get_spec(ext)
    if spec and spec.literal_types is not None:
        return spec.literal_types
    return DEFAULT_LITERAL_TYPES


def _get_string_types(ext: str) -> frozenset[str]:
    spec = get_spec(ext)
    if spec and spec.string_types is not None:
        return spec.string_types
    return DEFAULT_STRING_TYPES


def _get_structure_types(ext: str) -> frozenset[str]:
    spec = get_spec(ext)
    if spec and spec.structure_types is not None:
        return spec.structure_types
    return DEFAULT_STRUCTURE_NODE_TYPES


def _get_statement_types(ext: str) -> frozenset[str]:
    spec = get_spec(ext)
    if spec and spec.statement_types is not None:
        return spec.statement_types
    return DEFAULT_STATEMENT_TYPES

# tree-sitter parser cache to avoid re-creating parsers
_parser_cache: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Parser acquisition
# ---------------------------------------------------------------------------
def get_parser(extension: str) -> Optional[object]:
    """Get a tree-sitter ``Parser`` for the given file extension.

    Args:
        extension: Lowercase file extension including the dot, e.g. ``".py"``.

    Returns:
        A configured ``tree_sitter.Parser``, or ``None`` if tree-sitter is
        not installed or the language grammar is unavailable.
    """
    if not _TS_AVAILABLE:
        return None

    if extension in _parser_cache:
        return _parser_cache[extension]

    spec = get_spec(extension)
    if spec is None or spec.tree_sitter_module is None:
        return None

    module_name = spec.tree_sitter_module
    func_name = spec.tree_sitter_func
    try:
        import importlib
        mod = importlib.import_module(module_name)
        lang_func = getattr(mod, func_name)
        lang_ptr = lang_func()

        # tree-sitter >= 0.23 requires Language() wrapping
        lang = _ts.Language(lang_ptr)
        parser = _ts.Parser(lang)
        _parser_cache[extension] = parser
        return parser
    except Exception as exc:
        logger.debug("tree-sitter parser unavailable for %s: %s", extension, exc)
        return None


# ---------------------------------------------------------------------------
# AST linearization
# ---------------------------------------------------------------------------
def linearize(node: object) -> list[str]:
    """Linearize an AST node into a flat token sequence via DFS.

    Internal nodes that are in ``_STRUCTURE_NODE_TYPES`` emit
    ``<node_type>`` / ``</node_type>`` bracketing tags.

    Leaf nodes are normalised:
    * Identifiers → ``"ID"``
    * Numeric literals → ``"LIT"``
    * String literals → ``"STR"``
    * Keywords/operators → preserved as-is

    Args:
        node: A ``tree_sitter.Node`` object.

    Returns:
        List of string tokens.
    """
    tokens: list[str] = []
    _linearize_recursive(node, tokens)
    return tokens


def _linearize_recursive(node: object, tokens: list[str]) -> None:
    """Recursive DFS helper for linearization."""
    node_type: str = node.type  # type: ignore[attr-defined]
    child_count: int = node.child_count  # type: ignore[attr-defined]

    if child_count == 0:
        # Leaf node — normalise
        if node_type in _IDENTIFIER_TYPES:
            tokens.append("ID")
        elif node_type in _LITERAL_TYPES:
            tokens.append("LIT")
        elif node_type in _STRING_TYPES:
            tokens.append("STR")
        else:
            # Keywords, operators, punctuation — preserve text
            text: str = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if text.strip():
                tokens.append(text.strip())
        return

    # Internal node — emit structure tags if meaningful
    emit_tags = node_type in _STRUCTURE_NODE_TYPES

    if emit_tags:
        tokens.append(f"<{node_type}>")

    for child in node.children:  # type: ignore[attr-defined]
        _linearize_recursive(child, tokens)

    if emit_tags:
        tokens.append(f"</{node_type}>")


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------
def ast_tokenize(source: str, extension: str) -> Optional[list[str]]:
    """Parse source code and return a linearized AST token sequence.

    Args:
        source:    Source code text.
        extension: Lowercase file extension (e.g. ``".py"``).

    Returns:
        List of normalised AST tokens, or ``None`` if tree-sitter is
        unavailable or parsing fails — signalling the caller to fall
        back to Phase 1 token normalisation.
    """
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node
        tokens = linearize(root)
        if not tokens:
            return None
        return tokens
    except Exception as exc:
        logger.debug("AST parsing failed for extension %s: %s", extension, exc)
        return None


# ---------------------------------------------------------------------------
# Phase 4: Lightweight PDG Normalization
# ---------------------------------------------------------------------------
# Statement-level node types — imported from _defaults.py
_STATEMENT_TYPES = DEFAULT_STATEMENT_TYPES


def _collect_identifiers(node: object) -> tuple[set[str], set[str]]:
    """Collect defined and used identifiers from an AST subtree.

    A simplified use-def analysis:
    - **def**: identifiers on the left-hand side of assignments
    - **use**: all other identifiers

    Returns:
        ``(defined_identifiers, used_identifiers)``
    """
    defined: set[str] = set()
    used: set[str] = set()
    _collect_ids_recursive(node, defined, used, is_lhs=False)
    return defined, used


def _collect_ids_recursive(
    node: object,
    defined: set[str],
    used: set[str],
    *,
    is_lhs: bool,
) -> None:
    """Recursive helper for identifier collection."""
    node_type: str = node.type  # type: ignore[attr-defined]
    child_count: int = node.child_count  # type: ignore[attr-defined]

    if child_count == 0:
        if node_type in _IDENTIFIER_TYPES:
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if is_lhs:
                defined.add(text)
            else:
                used.add(text)
        return

    # For assignment nodes, the left side is "defined"
    is_assignment = node_type in (
        "assignment", "augmented_assignment",
        "assignment_expression", "variable_declarator",
        "local_variable_declaration",
    )

    children = list(node.children)  # type: ignore[attr-defined]
    for i, child in enumerate(children):
        child_is_lhs = is_lhs
        if is_assignment and i == 0:
            child_is_lhs = True
        _collect_ids_recursive(child, defined, used, is_lhs=child_is_lhs)


def extract_use_def(
    statements: list[object],
) -> list[tuple[object, set[str], set[str]]]:
    """Extract use-def information for a list of statement nodes.

    Args:
        statements: List of tree-sitter statement nodes.

    Returns:
        List of ``(node, defined_ids, used_ids)`` tuples.
    """
    result = []
    for stmt in statements:
        defined, used = _collect_identifiers(stmt)
        result.append((stmt, defined, used))
    return result


def filter_independent_statements(
    stmt_info: list[tuple[object, set[str], set[str]]],
) -> list[tuple[object, set[str], set[str]]]:
    """Filter out statements that have no dependency relationships.

    A statement is considered **independent** (potential dead code) if:
    - It defines no variables used by any other statement, AND
    - It uses no variables defined by any other statement

    Statements that are control flow (if, for, while, return, etc.)
    are always preserved regardless of dependency analysis.

    Args:
        stmt_info: Output of :func:`extract_use_def`.

    Returns:
        Filtered list with independent statements removed.
    """
    # Nodes to always keep (control flow, returns, etc.)
    _ALWAYS_KEEP = frozenset({
        "return_statement", "if_statement", "for_statement",
        "while_statement", "for_in_statement", "enhanced_for_statement",
        "do_statement", "switch_statement", "try_statement",
        "throw_statement",
    })

    if len(stmt_info) <= 1:
        return stmt_info

    # Collect all defined and used variables across all statements
    all_defined: set[str] = set()
    all_used: set[str] = set()
    for _, defs, uses in stmt_info:
        all_defined |= defs
        all_used |= uses

    filtered: list[tuple[object, set[str], set[str]]] = []
    for node, defs, uses in stmt_info:
        node_type: str = node.type  # type: ignore[attr-defined]

        # Always keep control flow statements
        if node_type in _ALWAYS_KEEP:
            filtered.append((node, defs, uses))
            continue

        # Keep if this statement defines something used elsewhere
        other_uses = all_used - uses
        if defs & other_uses:
            filtered.append((node, defs, uses))
            continue

        # Keep if this statement uses something defined elsewhere
        other_defs = all_defined - defs
        if uses & other_defs:
            filtered.append((node, defs, uses))
            continue

        # Independent statement — filter out (likely dead code)
        logger.debug("PDG filter: removing independent statement at line %d",
                      node.start_point[0] + 1)  # type: ignore[attr-defined]

    return filtered


def reorder_by_dependency(
    stmt_info: list[tuple[object, set[str], set[str]]],
) -> list[tuple[object, set[str], set[str]]]:
    """Reorder statements by dependency (topological sort).

    Statements are sorted so that definitions come before uses,
    producing a canonical ordering that is resilient to superficial
    reordering attacks.

    Uses a simple greedy algorithm: repeatedly pick the statement
    whose used variables are all already defined.

    Args:
        stmt_info: Output of :func:`filter_independent_statements`.

    Returns:
        Reordered list of statement info tuples.
    """
    if len(stmt_info) <= 1:
        return stmt_info

    remaining = list(range(len(stmt_info)))
    ordered: list[int] = []
    satisfied: set[str] = set()  # Variables already defined

    max_iterations = len(remaining) * 2  # Safety limit
    iteration = 0

    while remaining and iteration < max_iterations:
        iteration += 1
        progress = False

        for idx in list(remaining):
            _, defs, uses = stmt_info[idx]
            # Check if all used variables are satisfied
            unsatisfied = uses - satisfied
            if not unsatisfied or not (unsatisfied & {d for i in remaining if i != idx for d in stmt_info[i][1]}):
                ordered.append(idx)
                remaining.remove(idx)
                satisfied |= defs
                progress = True

        if not progress:
            # Cycle or unresolvable — append remaining in original order
            ordered.extend(remaining)
            break

    return [stmt_info[i] for i in ordered]


def _get_top_level_statements(root: object) -> list[object]:
    """Extract top-level statement nodes from an AST root.

    For languages with a module/program/compilation_unit root node,
    extracts the direct children that are statements.  For function
    bodies, extracts the body statements.
    """
    statements: list[object] = []
    for child in root.children:  # type: ignore[attr-defined]
        child_type: str = child.type  # type: ignore[attr-defined]
        if child_type in _STATEMENT_TYPES:
            statements.append(child)
        elif child.child_count > 0:  # type: ignore[attr-defined]
            # Recurse into function bodies, class bodies, etc.
            for grandchild in child.children:  # type: ignore[attr-defined]
                if grandchild.type in _STATEMENT_TYPES:  # type: ignore[attr-defined]
                    statements.append(grandchild)
    return statements


def pdg_tokenize(source: str, extension: str) -> Optional[list[str]]:
    """Parse source code with PDG-normalised AST tokenization.

    Extends ``ast_tokenize`` by:
    1. Extracting top-level statements from the AST
    2. Building use-def chains for each statement
    3. Filtering independent (dead-code) statements
    4. Reordering by dependency
    5. Linearizing the filtered, reordered statements

    This makes fingerprints resilient to:
    - Dead code injection attacks
    - Statement reordering attacks

    Args:
        source:    Source code text.
        extension: Lowercase file extension (e.g. ``".py"``).

    Returns:
        List of normalised tokens, or ``None`` if tree-sitter is
        unavailable or processing fails.
    """
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node

        # Extract top-level statements
        statements = _get_top_level_statements(root)
        if not statements:
            # Fall back to full AST linearization if no statements found
            return linearize(root) or None

        # Use-def analysis
        stmt_info = extract_use_def(statements)

        # Filter independent (dead-code) statements
        filtered = filter_independent_statements(stmt_info)

        # Reorder by dependency
        reordered = reorder_by_dependency(filtered)

        # Linearize the reordered statements
        tokens: list[str] = []
        for node, _, _ in reordered:
            tokens.extend(linearize(node))

        return tokens if tokens else None

    except Exception as exc:
        logger.debug("PDG tokenization failed for extension %s: %s", extension, exc)
        return None
