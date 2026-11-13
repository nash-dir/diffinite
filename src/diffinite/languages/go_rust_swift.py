"""Go, Rust, and Swift language definitions."""

from diffinite.languages._spec import LangSpec, LanguageCommentSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

# Go: `raw strings` have no backslash escapes (`C:\` is a complete literal)
# and no interpolation (`${ // x }` is plain text).
_GO_COMMENT = LanguageCommentSpec(
    line_markers=("//",), block_start="/*", block_end="*/",
    template_escapes=False, template_interpolation=False,
)

# Rust: block comments nest; ' is a char literal only when complete ('x', '\n'),
# otherwise a lifetime/label ('a, 'static); no backtick strings.
_RUST_COMMENT = CommentSpec(
    line_markers=("//",), block_start="/*", block_end="*/",
    string_delims=('"',), template_delims=(), char_literals_strict=True,
    nested_block_comments=True,
)

# Swift: """multi-line strings""", nestable block comments, no ' or ` strings.
_SWIFT_COMMENT = CommentSpec(
    line_markers=("//",), block_start="/*", block_end="*/",
    string_delims=('"',), template_delims=(), triple_quote_delims=('"',),
    nested_block_comments=True,
)

_GO_KEYWORDS = frozenset({
    "break", "case", "chan", "const", "continue",
    "default", "defer", "else", "fallthrough", "for",
    "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select",
    "struct", "switch", "type", "var",
    # Built-in types
    "int", "string", "bool", "float", "byte",
    "true", "false", "nil",
})

_RUST_KEYWORDS = frozenset({
    "as", "break", "const", "continue", "crate",
    "else", "enum", "extern", "false", "fn", "for",
    "if", "impl", "in", "let", "loop", "match", "mod",
    "move", "mut", "pub", "ref", "return", "self",
    "static", "struct", "super", "trait", "true",
    "type", "unsafe", "use", "where", "while",
    "async", "await", "dyn",
})

_SWIFT_KEYWORDS = frozenset({
    "break", "case", "class", "continue", "default",
    "defer", "do", "else", "enum", "extension",
    "fallthrough", "for", "func", "guard", "if",
    "import", "in", "init", "let", "nil", "protocol",
    "repeat", "return", "self", "static", "struct",
    "super", "switch", "throw", "true", "false",
    "try", "typealias", "var", "where", "while",
    "async", "await",
})

register(LangSpec(
    name="Go",
    extensions=(".go",),
    comment=_GO_COMMENT,
    keywords=_GO_KEYWORDS,
))

register(LangSpec(
    name="Rust",
    extensions=(".rs",),
    comment=_RUST_COMMENT,
    keywords=_RUST_KEYWORDS,
))

register(LangSpec(
    name="Swift",
    extensions=(".swift",),
    comment=_SWIFT_COMMENT,
    keywords=_SWIFT_KEYWORDS,
))
