"""Go, Rust, and Swift language definitions."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_C_STYLE_COMMENT = CommentSpec(line_markers=("//",), block_start="/*", block_end="*/")

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
    comment=_C_STYLE_COMMENT,
    has_ifdef_zero=True,
    keywords=_GO_KEYWORDS,
))

register(LangSpec(
    name="Rust",
    extensions=(".rs",),
    comment=_C_STYLE_COMMENT,
    has_ifdef_zero=True,
    keywords=_RUST_KEYWORDS,
))

register(LangSpec(
    name="Swift",
    extensions=(".swift",),
    comment=_C_STYLE_COMMENT,
    has_ifdef_zero=True,
    keywords=_SWIFT_KEYWORDS,
))
