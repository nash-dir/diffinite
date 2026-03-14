"""Scripting languages: Ruby, PHP, Perl, Shell/Bash, Lua."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

# ── Ruby ──────────────────────────────────────────────────────────
register(LangSpec(
    name="Ruby",
    extensions=(".rb",),
    comment=CommentSpec(line_markers=("#",), block_start="=begin", block_end="=end"),
    keywords=frozenset({
        "if", "else", "elsif", "unless", "while", "until",
        "for", "do", "begin", "end", "def", "class",
        "module", "return", "yield", "raise", "rescue",
        "ensure", "retry", "break", "next", "case", "when",
        "true", "false", "nil", "self", "super",
        "require", "include", "extend",
    }),
))

# ── PHP ───────────────────────────────────────────────────────────
register(LangSpec(
    name="PHP",
    extensions=(".php",),
    comment=CommentSpec(line_markers=("//", "#"), block_start="/*", block_end="*/"),
    keywords=frozenset({
        "if", "else", "elseif", "while", "for", "foreach",
        "do", "switch", "case", "break", "continue", "return",
        "function", "class", "interface", "extends", "implements",
        "public", "private", "protected", "static", "abstract",
        "final", "new", "try", "catch", "finally", "throw",
        "namespace", "use", "echo", "var",
        "true", "false", "null", "this", "self",
    }),
))

# ── Perl ──────────────────────────────────────────────────────────
register(LangSpec(
    name="Perl",
    extensions=(".pl", ".pm"),
    comment=CommentSpec(line_markers=("#",), block_start=None, block_end=None),
    keywords=frozenset({
        "if", "else", "elsif", "unless", "while", "until",
        "for", "foreach", "do", "sub", "return",
        "my", "our", "local", "use", "require",
        "die", "warn", "print", "chomp",
    }),
))

# ── Shell / Bash ──────────────────────────────────────────────────
register(LangSpec(
    name="Shell",
    extensions=(".sh", ".bash"),
    comment=CommentSpec(line_markers=("#",), block_start=None, block_end=None),
    keywords=frozenset({
        "if", "then", "else", "elif", "fi",
        "for", "while", "do", "done", "case", "esac",
        "function", "return", "exit",
        "echo", "export", "local", "readonly",
        "true", "false",
    }),
))

# ── Lua ───────────────────────────────────────────────────────────
register(LangSpec(
    name="Lua",
    extensions=(".lua",),
    comment=CommentSpec(line_markers=("--",), block_start="--[[", block_end="]]"),
    keywords=frozenset({
        "and", "break", "do", "else", "elseif", "end",
        "false", "for", "function", "goto", "if", "in",
        "local", "nil", "not", "or", "repeat", "return",
        "then", "true", "until", "while",
    }),
))
