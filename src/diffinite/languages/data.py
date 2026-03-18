"""Data / query languages: SQL, YAML, TOML."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

# ── SQL ───────────────────────────────────────────────────────────
register(LangSpec(
    name="SQL",
    extensions=(".sql", ".ddl", ".dml", ".pks", ".pkb", ".plsql", ".tsql"),
    comment=CommentSpec(line_markers=("--",), block_start="/*", block_end="*/"),
    keywords=frozenset({
        # DML
        "select", "from", "where", "insert", "update", "delete", "merge",
        "into", "values", "set", "returning",
        # DDL
        "create", "drop", "alter", "table", "index", "view", "schema",
        "database", "sequence", "trigger", "procedure", "function",
        "column", "constraint", "primary", "foreign", "key", "references",
        "unique", "check", "default", "auto_increment", "identity",
        "cascade", "restrict", "truncate", "rename", "replace",
        # Joins
        "join", "inner", "outer", "left", "right", "cross", "full",
        "natural", "on", "using",
        # Operators & conditions
        "and", "or", "not", "in", "like", "ilike", "between",
        "is", "null", "true", "false", "case", "when", "then", "else",
        # Aggregates & ordering
        "order", "by", "group", "having", "limit", "offset", "fetch",
        "as", "distinct", "union", "intersect", "except", "all", "exists",
        "count", "sum", "avg", "min", "max",
        # Window functions
        "over", "partition", "row_number", "rank", "dense_rank",
        "lead", "lag", "first_value", "last_value", "ntile",
        "rows", "range", "unbounded", "preceding", "following", "current",
        # Transactions & control flow
        "begin", "end", "commit", "rollback", "savepoint", "transaction",
        # DCL
        "grant", "revoke", "deny",
        # Subquery & CTE
        "with", "recursive",
        # Types
        "int", "integer", "varchar", "char", "text", "boolean", "date",
        "timestamp", "decimal", "numeric", "float", "double", "blob", "clob",
        # Procedural (PL/SQL, T-SQL)
        "declare", "variable", "cursor", "open", "close", "fetch",
        "loop", "while", "for", "if", "elseif", "elsif", "return",
        "exec", "execute", "call", "raise", "exception", "handler",
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
