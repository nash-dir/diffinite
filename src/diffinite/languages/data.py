"""Data / query languages: SQL, YAML, TOML."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

# ── SQL ───────────────────────────────────────────────────────────
register(LangSpec(
    name="SQL",
    extensions=(".sql",),
    comment=CommentSpec(line_markers=("--",), block_start="/*", block_end="*/"),
    keywords=frozenset({
        "select", "from", "where", "insert", "update", "delete",
        "create", "drop", "alter", "table", "index", "view",
        "join", "inner", "outer", "left", "right", "on",
        "and", "or", "not", "in", "like", "between",
        "order", "by", "group", "having", "limit", "offset",
        "as", "distinct", "union", "all", "exists",
        "null", "true", "false", "is",
        "begin", "end", "commit", "rollback", "transaction",
    }),
))

# ── YAML ──────────────────────────────────────────────────────────
register(LangSpec(
    name="YAML",
    extensions=(".yaml", ".yml"),
    comment=CommentSpec(line_markers=("#",), block_start=None, block_end=None),
))

# ── TOML ──────────────────────────────────────────────────────────
register(LangSpec(
    name="TOML",
    extensions=(".toml",),
    comment=CommentSpec(line_markers=("#",), block_start=None, block_end=None),
))
