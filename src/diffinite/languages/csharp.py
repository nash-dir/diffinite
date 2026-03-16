"""C# language definition."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_COMMENT = CommentSpec(line_markers=("//",), block_start="/*", block_end="*/")

_KEYWORDS = frozenset({
    # Control flow
    "if", "else", "for", "foreach", "while", "do",
    "switch", "case", "break", "continue", "return",
    "try", "catch", "finally", "throw",
    # Declaration
    "class", "interface", "struct", "enum", "namespace",
    "using", "new", "delegate", "event",
    # Types
    "void", "int", "long", "float", "double", "char",
    "bool", "byte", "short", "string", "decimal",
    "object", "var",
    # Access
    "public", "private", "protected", "internal",
    "static", "abstract", "virtual", "override",
    "sealed", "readonly", "const",
    # Async
    "async", "await",
    # Literals
    "true", "false", "null", "this", "base",
})

register(LangSpec(
    name="C#",
    extensions=(".cs",),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_KEYWORDS,
))
