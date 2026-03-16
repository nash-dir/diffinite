"""JVM language family: Java, Kotlin, Scala."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_COMMENT = CommentSpec(line_markers=("//",), block_start="/*", block_end="*/")

_JAVA_KEYWORDS = frozenset({
    # Control flow
    "if", "else", "for", "while", "do", "switch", "case",
    "break", "continue", "return", "try", "catch", "finally",
    "throw", "throws",
    # Declaration
    "class", "interface", "enum", "extends", "implements",
    "import", "package", "new", "instanceof",
    # Types
    "void", "int", "long", "float", "double", "char",
    "boolean", "byte", "short", "string",
    # Access
    "public", "private", "protected", "default",
    "static", "final", "abstract", "synchronized",
    # Literals
    "true", "false", "null", "this", "super",
})

register(LangSpec(
    name="Java",
    extensions=(".java",),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_JAVA_KEYWORDS,
))

register(LangSpec(
    name="Kotlin",
    extensions=(".kt", ".kts"),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_JAVA_KEYWORDS | frozenset({
        "fun", "val", "var", "when", "object", "companion",
        "data", "sealed", "suspend", "coroutine",
    }),
))

register(LangSpec(
    name="Scala",
    extensions=(".scala",),
    comment=_COMMENT,
    has_ifdef_zero=True,
    keywords=_JAVA_KEYWORDS | frozenset({
        "def", "val", "var", "object", "trait", "sealed",
        "implicit", "lazy", "match", "yield",
    }),
))
