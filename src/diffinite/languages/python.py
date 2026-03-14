"""Python language definition."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_COMMENT = CommentSpec(line_markers=("#",), block_start=None, block_end=None)

_KEYWORDS = frozenset({
    # Control flow
    "if", "else", "elif", "for", "while",
    "break", "continue", "return", "try", "except",
    "finally", "raise", "with", "as",
    # Declaration
    "class", "def", "import", "from",
    "lambda", "yield", "async", "await",
    # Logical
    "and", "or", "not", "in", "is",
    "True", "False", "None",
    # Scope
    "global", "nonlocal",
    # Other
    "pass", "del", "assert",
    # Also support lowercase for token normalisation
    "true", "false", "null",
    "self",
})

register(LangSpec(
    name="Python",
    extensions=(".py", ".pyw"),
    comment=_COMMENT,
    has_ifdef_zero=False,
    keywords=_KEYWORDS,
    tree_sitter_module="tree_sitter_python",
))
