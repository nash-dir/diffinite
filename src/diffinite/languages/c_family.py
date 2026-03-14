"""C-family language definitions: C, C++, Objective-C headers."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_COMMENT = CommentSpec(line_markers=("//",), block_start="/*", block_end="*/")

_KEYWORDS = frozenset({
    # Control flow
    "if", "else", "for", "while", "do", "switch", "case",
    "break", "continue", "return", "goto",
    # Declaration
    "struct", "typedef", "enum", "union",
    "static", "const", "volatile", "extern", "register",
    "inline",
    # Types
    "void", "int", "long", "float", "double", "char",
    "short", "unsigned", "signed",
    # Logical
    "sizeof", "true", "false", "null",
    # Preprocessor-related keywords
    "define", "include",
})

_CPP_EXTRA = frozenset({
    "class", "namespace", "template", "virtual", "override",
    "public", "private", "protected", "friend",
    "new", "delete", "throw", "try", "catch",
    "const", "constexpr", "auto", "decltype",
    "nullptr", "this", "using", "typename",
    "bool", "string",
})

register(LangSpec(
    name="C",
    extensions=(".c", ".h"),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_KEYWORDS,
    tree_sitter_module="tree_sitter_c",
))

register(LangSpec(
    name="C++",
    extensions=(".cpp", ".hpp", ".cc"),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_KEYWORDS | _CPP_EXTRA,
    tree_sitter_module="tree_sitter_cpp",
))
