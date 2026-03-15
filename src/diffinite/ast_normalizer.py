"""tree-sitter AST 기반 토큰 선형화 엔진.

소스코드를 AST로 파싱한 후, 트리를 Winnowing 파이프라인에서
소비할 수 있는 토큰 시퀀스로 선형화(linearize)한다.

선형화 규칙:
    - 내부 노드: open/close 태그 (``<for_statement>``, ``</for_statement>``)
    - 식별자: ``"ID"`` (Type-2 클론 저항)
    - 숫자 리터럴: ``"LIT"``
    - 문자열 리터럴: ``"STR"``
    - 키워드/연산자: 원본 보존 (구조 시그니처)

이 전략의 효과:
    - 식별자 변경(Type-2) 저항: ID 정규화로 변수명에 무관
    - 구조 보존: open/close 태그가 중첩 구조를 인코딩
    - 연산자/키워드 보존: 알고리즘의 "뼈대"를 유지

추가 기능:
    - ``extract_declaration_identifiers()``: API 표면 식별자만 추출 (SSO 탐지용)
    - ``linearize_pdg()``: Program Dependence Graph 선형화 (실험적)

tree-sitter 의존성:
    tree-sitter는 선택적 의존. 미설치 시 ``None`` 반환으로
    호출자가 Phase 1 토큰 정규화로 자연스럽게 폴백.
    ``pip install tree-sitter tree-sitter-java`` 등으로 설치.

호출관계:
    ``fingerprint.extract_fingerprints(mode='ast')`` -> ``linearize_ast()``
    ``evidence.declaration_identifier_cosine()`` -> ``extract_declaration_identifiers()``
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


# ---------------------------------------------------------------------------
# SSO Detection: Declaration-Level Identifier Extraction
# ---------------------------------------------------------------------------
# Node types that represent declarations (API surface)
_DECLARATION_NODE_TYPES = frozenset({
    "class_declaration", "class_definition",
    "interface_declaration",
    "method_declaration", "method_definition",
    "function_declaration", "function_definition",
    "constructor_declaration",
    "enum_declaration",
    "annotation_type_declaration",
})

# Node types that are formal parameters
_PARAMETER_NODE_TYPES = frozenset({
    "formal_parameter", "spread_parameter",
    "parameter", "required_parameter", "optional_parameter",
    "parameter_declaration",
})

# Node types whose identifiers should be EXCLUDED (implementation detail)
_IMPLEMENTATION_NODE_TYPES = frozenset({
    "local_variable_declaration",
    "variable_declaration",
    "assignment_expression", "assignment",
    "augmented_assignment",
    "expression_statement",
    "method_invocation", "call_expression",
    "field_access",
})

# Boilerplate method names — common overrides that every Java class may implement
_BOILERPLATE_METHODS = frozenset({
    "equals", "hashCode", "toString", "compareTo",
    "clone", "finalize",
})


def _is_boilerplate_method_name(name: str) -> bool:
    """Check whether *name* is a boilerplate method (equals, hashCode,
    toString, getter/setter, etc.).

    Boilerplate methods are those whose presence is driven by language
    convention rather than API design — filtering them reduces false
    positives in SSO detection.
    """
    if name in _BOILERPLATE_METHODS:
        return True
    # Getter/setter pattern: get/set/is + UpperCaseLetter
    if len(name) > 3 and name[:3] in ("get", "set") and name[3].isupper():
        return True
    if len(name) > 2 and name[:2] == "is" and name[2].isupper():
        return True
    return False


def extract_declaration_identifiers(
    source: str, extension: str,
    *, skip_boilerplate: bool = False,
) -> Optional[list[str]]:
    """Extract only declaration-level identifiers from the AST.

    Collects identifiers from:
    - Class/interface/enum names
    - Method/function names
    - Formal parameter names and types

    Excludes:
    - Local variable names
    - Method call targets
    - Field access expressions

    When *skip_boilerplate* is True, identifiers belonging to boilerplate
    methods (equals, hashCode, toString, getters/setters) are excluded.

    Args:
        source:           Source code text.
        extension:        Lowercase file extension (e.g. ``".java"``).
        skip_boilerplate: If True, exclude boilerplate method identifiers.

    Returns:
        Sorted list of declaration-level identifier strings,
        or ``None`` if tree-sitter is unavailable.
    """
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node

        identifiers: list[str] = []
        _collect_declaration_ids(
            root, identifiers, in_declaration=False,
            skip_boilerplate=skip_boilerplate,
        )
        return identifiers if identifiers else None

    except Exception as exc:
        logger.debug(
            "Declaration identifier extraction failed for %s: %s",
            extension, exc,
        )
        return None


def _collect_declaration_ids(
    node: object,
    identifiers: list[str],
    *,
    in_declaration: bool,
    skip_boilerplate: bool = False,
    _in_boilerplate_method: bool = False,
) -> None:
    """Recursively collect identifiers from declaration contexts."""
    node_type: str = node.type  # type: ignore[attr-defined]
    child_count: int = node.child_count  # type: ignore[attr-defined]

    # Check if we're entering a declaration context
    is_decl = node_type in _DECLARATION_NODE_TYPES
    is_param = node_type in _PARAMETER_NODE_TYPES
    is_impl = node_type in _IMPLEMENTATION_NODE_TYPES

    # Check if this method declaration is boilerplate
    in_boilerplate = _in_boilerplate_method
    if skip_boilerplate and is_decl and node_type in (
        "method_declaration", "method_definition",
        "function_declaration", "function_definition",
    ):
        # Look for the method name child
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "identifier":  # type: ignore[attr-defined]
                name = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text  # type: ignore[attr-defined]
                if _is_boilerplate_method_name(name):
                    in_boilerplate = True
                break

    # If inside boilerplate method and filtering, skip entirely
    if skip_boilerplate and in_boilerplate:
        return

    # Skip implementation blocks (but still recurse into nested declarations)
    if is_impl and not in_declaration:
        # Still look for nested class/method declarations inside
        for child in node.children:  # type: ignore[attr-defined]
            child_type: str = child.type  # type: ignore[attr-defined]
            if child_type in _DECLARATION_NODE_TYPES:
                _collect_declaration_ids(
                    child, identifiers, in_declaration=True,
                    skip_boilerplate=skip_boilerplate,
                    _in_boilerplate_method=in_boilerplate,
                )
        return

    # Leaf node in declaration context → collect identifier
    if child_count == 0:
        id_types = _get_identifier_types(node_type)  # reuse existing helper
        # For identifiers at declaration level, collect the actual text
        if node_type in _IDENTIFIER_TYPES and (in_declaration or is_param):
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if text and text.strip():
                identifiers.append(text.strip())
        # Also collect type identifiers from declarations/parameters
        elif node_type == "type_identifier" and (in_declaration or is_param):
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if text and text.strip():
                identifiers.append(text.strip())
        return

    # Recurse into children
    new_in_decl = in_declaration or is_decl or is_param
    for child in node.children:  # type: ignore[attr-defined]
        child_type = child.type  # type: ignore[attr-defined]
        # Don't descend into implementation bodies for declarations
        # (the block/body inside a method is implementation)
        if (is_decl or in_declaration) and child_type in ("block", "statement_block", "compound_statement"):
            # Skip method body — it's implementation detail
            continue
        _collect_declaration_ids(
            child, identifiers, in_declaration=new_in_decl,
            skip_boilerplate=skip_boilerplate,
            _in_boilerplate_method=in_boilerplate,
        )


# ---------------------------------------------------------------------------
# SSO Detection: Structure-Only AST Linearization
# ---------------------------------------------------------------------------
def linearize_structure_only(
    source: str, extension: str,
) -> Optional[list[str]]:
    """Linearize the AST emitting only the structural skeleton.

    Unlike full ``linearize()``, this variant:
    1. Emits structure tags for declaration nodes
    2. Preserves identifier names at declaration level (class/method/param names)
    3. Skips implementation body content (method bodies, local variables)

    This amplifies the SSO signal: files that share the same API structure
    will produce nearly identical token sequences even if their implementations
    are completely different.

    Args:
        source:    Source code text.
        extension: Lowercase file extension.

    Returns:
        Token sequence, or ``None`` if tree-sitter is unavailable.
    """
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node

        tokens: list[str] = []
        _linearize_structure_recursive(root, tokens, extension)
        return tokens if tokens else None

    except Exception as exc:
        logger.debug(
            "Structure-only linearization failed for %s: %s",
            extension, exc,
        )
        return None


def _linearize_structure_recursive(
    node: object, tokens: list[str], extension: str,
) -> None:
    """DFS helper that emits only declaration structure."""
    node_type: str = node.type  # type: ignore[attr-defined]
    child_count: int = node.child_count  # type: ignore[attr-defined]

    # Leaf node
    if child_count == 0:
        if node_type in _IDENTIFIER_TYPES:
            # Preserve actual identifier at declaration level
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if text and text.strip():
                tokens.append(text.strip())
        elif node_type == "type_identifier":
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if text and text.strip():
                tokens.append(text.strip())
        elif node_type in _LITERAL_TYPES:
            tokens.append("LIT")
        elif node_type in _STRING_TYPES:
            tokens.append("STR")
        else:
            text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text  # type: ignore[attr-defined]
            if text and text.strip():
                tokens.append(text.strip())
        return

    # Internal node
    is_structure = node_type in _STRUCTURE_NODE_TYPES
    is_declaration = node_type in _DECLARATION_NODE_TYPES

    if is_structure or is_declaration:
        tokens.append(f"<{node_type}>")

    for child in node.children:  # type: ignore[attr-defined]
        child_type: str = child.type  # type: ignore[attr-defined]
        # Skip method/function bodies (implementation detail)
        if is_declaration and child_type in ("block", "statement_block", "compound_statement", "class_body"):
            # For class bodies, we DO want to descend to find nested declarations
            if child_type == "class_body":
                _linearize_structure_recursive(child, tokens, extension)
            else:
                # Method body — emit a placeholder instead of traversing
                tokens.append("<BODY>")
            continue
        _linearize_structure_recursive(child, tokens, extension)

    if is_structure or is_declaration:
        tokens.append(f"</{node_type}>")


# ---------------------------------------------------------------------------
# AFC: Abstraction Layer — Class-Level Decomposition  (Stage 6)
# ---------------------------------------------------------------------------
_CLASS_NODE_TYPES = frozenset({
    "class_declaration", "class_definition",
    "interface_declaration", "enum_declaration",
})

_METHOD_NODE_TYPES = frozenset({
    "method_declaration", "method_definition",
    "function_declaration", "function_definition",
    "constructor_declaration",
})


def _node_text(node) -> str:
    text = node.text
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return text


def _find_name(node) -> str:
    """Find the name identifier from a declaration node."""
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child)
    return "<anonymous>"


def extract_class_declarations(
    source: str, extension: str,
) -> Optional[list[dict]]:
    """Decompose source into class-level units (AFC Abstraction layer).

    Each class is returned as a dict with:
      - ``name``: class/interface name
      - ``methods``: list of ``{"name": str}`` dicts
      - ``node_type``: tree-sitter node type

    Args:
        source:    Source code text (comments stripped).
        extension: Lowercase file extension.

    Returns:
        List of class info dicts, or ``None`` if tree-sitter unavailable.
    """
    parser = get_parser(extension)
    if parser is None:
        return None

    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        classes: list[dict] = []
        _find_classes_recursive(root, classes)
        return classes if classes else None

    except Exception as exc:
        logger.debug("Class extraction failed for %s: %s", extension, exc)
        return None


def _find_classes_recursive(node, classes: list[dict]) -> None:
    """Recursively find class/interface declarations."""
    node_type = node.type

    if node_type in _CLASS_NODE_TYPES:
        name = _find_name(node)
        methods = []
        # Find methods within this class
        for child in node.children:
            if child.type == "class_body":
                _find_methods_in_body(child, methods)
            elif child.type in _METHOD_NODE_TYPES:
                methods.append({"name": _find_name(child)})

        classes.append({
            "name": name,
            "node_type": node_type,
            "methods": methods,
        })

    # Recurse into children
    for child in node.children:
        if child.type != "class_body":  # Don't double-descend
            _find_classes_recursive(child, classes)


def _find_methods_in_body(body_node, methods: list[dict]) -> None:
    """Find method declarations within a class body."""
    for child in body_node.children:
        if child.type in _METHOD_NODE_TYPES:
            methods.append({"name": _find_name(child)})
        elif child.type in _CLASS_NODE_TYPES:
            # Nested class — skip for now (handled by top-level recursion)
            pass


