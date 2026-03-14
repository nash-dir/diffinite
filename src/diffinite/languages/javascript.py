"""JavaScript and TypeScript language definitions."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_COMMENT = CommentSpec(line_markers=("//",), block_start="/*", block_end="*/")

_JS_KEYWORDS = frozenset({
    # Control flow
    "if", "else", "for", "while", "do", "switch", "case",
    "break", "continue", "return", "try", "catch", "finally",
    "throw",
    # Declaration
    "function", "class", "extends", "import", "from",
    "var", "let", "const", "new", "delete",
    "instanceof", "typeof",
    # Access
    "export", "default", "static",
    # Async
    "async", "await", "yield",
    # Literals
    "true", "false", "null", "this", "super",
    "undefined",
})

_TS_EXTRA = frozenset({
    "interface", "enum", "type", "implements",
    "public", "private", "protected",
    "abstract", "readonly", "declare",
    "namespace", "module",
    "void", "string", "number", "boolean", "any", "never",
})

register(LangSpec(
    name="JavaScript",
    extensions=(".js", ".jsx", ".mjs"),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_JS_KEYWORDS,
    tree_sitter_module="tree_sitter_javascript",
))

register(LangSpec(
    name="TypeScript",
    extensions=(".ts",),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_JS_KEYWORDS | _TS_EXTRA,
    tree_sitter_module="tree_sitter_typescript",
    tree_sitter_func="language_typescript",
))

register(LangSpec(
    name="TSX",
    extensions=(".tsx",),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_JS_KEYWORDS | _TS_EXTRA,
    tree_sitter_module="tree_sitter_typescript",
    tree_sitter_func="language_tsx",
))
