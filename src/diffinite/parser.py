"""2-Pass heuristic comment-stripping engine.

Overcomes the limitations of pure-regex comment removal (e.g. false
positives inside string literals like ``http://`` being treated as ``//``
comments) by combining a fast extension-based pre-filter with a precise
character-level state-machine parser.

Fast-path
    Lines that do *not* contain any comment marker for the file's language
    are passed through immediately — no per-character scanning needed.

Slow-path
    Lines (or the full text during a block-comment) are fed to a
    character-level state machine that tracks ``in_string`` / ``escaped``
    state to ensure only *genuine* comments are stripped.
"""

from __future__ import annotations

import enum
import re
from typing import Optional

from diffinite.models import CommentSpec

# ---------------------------------------------------------------------------
# Extension → CommentSpec mapping
# ---------------------------------------------------------------------------

# C-family extensions that may use #if 0
_C_FAMILY_EXTS = frozenset({
    ".c", ".h", ".cpp", ".hpp", ".cs", ".java",
    ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".swift", ".kt", ".scala",
})

COMMENT_SPECS: dict[str, CommentSpec] = {
    # Python
    ".py":   CommentSpec(line_markers=("#",),    block_start=None,    block_end=None),
    # C-family
    ".c":    CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".h":    CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".cpp":  CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".hpp":  CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".cs":   CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".java": CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".js":   CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".jsx":  CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".ts":   CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".tsx":  CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".go":   CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".rs":   CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".swift":CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".kt":   CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".scala":CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    # PHP — supports both // and # line comments
    ".php":  CommentSpec(line_markers=("//", "#"), block_start="/*",  block_end="*/"),
    # Ruby
    ".rb":   CommentSpec(line_markers=("#",),    block_start="=begin", block_end="=end"),
    # Shell / Bash
    ".sh":   CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
    ".bash": CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
    # Perl
    ".pl":   CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
    ".pm":   CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
    # HTML / XML / SVG
    ".html": CommentSpec(line_markers=(),        block_start="<!--",  block_end="-->"),
    ".htm":  CommentSpec(line_markers=(),        block_start="<!--",  block_end="-->"),
    ".xml":  CommentSpec(line_markers=(),        block_start="<!--",  block_end="-->"),
    ".svg":  CommentSpec(line_markers=(),        block_start="<!--",  block_end="-->"),
    # CSS
    ".css":  CommentSpec(line_markers=(),        block_start="/*",    block_end="*/"),
    ".scss": CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    ".less": CommentSpec(line_markers=("//",),   block_start="/*",    block_end="*/"),
    # SQL
    ".sql":  CommentSpec(line_markers=("--",),   block_start="/*",    block_end="*/"),
    # Lua
    ".lua":  CommentSpec(line_markers=("--",),   block_start="--[[",  block_end="]]"),
    # YAML / TOML
    ".yaml": CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
    ".yml":  CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
    ".toml": CommentSpec(line_markers=("#",),    block_start=None,     block_end=None),
}


# ---------------------------------------------------------------------------
# #if 0 pre-pass (C-family only)
# ---------------------------------------------------------------------------
_IF0_PATTERN = re.compile(
    r"^\s*#\s*if\s+0\s*$",    re.MULTILINE,
)
_ENDIF_PATTERN = re.compile(
    r"^\s*#\s*endif\b",       re.MULTILINE,
)


def _strip_ifdef_zero(text: str) -> str:
    """Strip ``#if 0 … #endif`` blocks, preserving newlines for line count.

    Handles nested ``#if`` / ``#endif`` pairs so only the outermost
    ``#if 0`` block is removed.
    """
    result: list[str] = []
    lines = text.split("\n")
    depth = 0  # nesting depth inside #if 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        if depth == 0:
            # Check for #if 0
            if _IF0_PATTERN.match(line):
                depth = 1
                result.append("")  # preserve line count
            else:
                result.append(line)
        else:
            # Inside #if 0 block
            if stripped.startswith("#") and re.match(r"#\s*if\b", stripped):
                depth += 1
            elif stripped.startswith("#") and re.match(r"#\s*endif\b", stripped):
                depth -= 1
            result.append("")  # always blank inside #if 0

        i += 1
    return "\n".join(result)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
class _State(enum.Enum):
    CODE = "CODE"
    IN_STRING = "IN_STRING"
    IN_LINE_COMMENT = "IN_LINE_COMMENT"
    IN_BLOCK_COMMENT = "IN_BLOCK_COMMENT"


def _has_any_marker(line: str, spec: CommentSpec) -> bool:
    """Fast-path check: does *line* need slow-path scanning?

    Returns *True* if the line contains any comment marker **or** any
    string-opening delimiter (``"``, ``'``, `` ` ``).  String delimiters
    must be checked because a string opened (or closed) on this line
    changes the state for subsequent lines.
    """
    for m in spec.line_markers:
        if m in line:
            return True
    if spec.block_start and spec.block_start in line:
        return True
    if spec.block_end and spec.block_end in line:
        return True
    # String delimiters affect cross-line state (e.g. triple-quotes)
    if '"' in line or "'" in line or '`' in line:
        return True
    return False


def strip_comments(
    text: str,
    extension: str,
    *,
    squash_blanks: bool = False,
) -> str:
    """Remove comments from *text* using an optimised 2-pass approach.

    For C-family extensions, ``#if 0 … #endif`` blocks are stripped
    as a pre-pass before comment removal.

    Pass 1 (fast-path):
        Lines that are in ``CODE`` state and do not contain any comment
        marker are passed through untouched — zero per-character work.

    Pass 2 (slow-path):
        Lines carrying a comment marker (or inheriting non-CODE state
        from a previous line) are scanned character-by-character with a
        state machine that tracks string literals and escape sequences,
        so only *genuine* comments are stripped.

    Args:
        text:           Source-code text.
        extension:      Lowercase file extension including the dot, e.g. ``".py"``.
        squash_blanks:  If *True*, collapse runs of 3+ blank lines to a
                        single blank line.  **CAUTION**: this changes line
                        count — do not enable when line-number traceability
                        matters (e.g. forensic reports).

    Returns:
        Text with comments removed.  If the extension has no known comment
        specification, the text is returned unchanged.
    """
    spec = COMMENT_SPECS.get(extension)
    if spec is None:
        return text

    # If no markers at all, nothing to strip
    if not spec.line_markers and not spec.block_start:
        return text

    # Pre-pass: strip #if 0 blocks for C-family
    if extension in _C_FAMILY_EXTS:
        text = _strip_ifdef_zero(text)

    result = _strip_2pass(text, spec)

    if squash_blanks:
        result = _squash_blank_lines(result)

    return result


def _strip_2pass(text: str, spec: CommentSpec) -> str:
    """Optimised 2-pass comment stripper.

    Splits input into lines and uses ``_has_any_marker`` to skip lines
    that cannot contain comments. Only lines with potential markers (or
    carrying non-CODE state from a previous block comment / string) go
    through the character-level scanner.
    """
    lines = text.split("\n")
    out_parts: list[str] = []
    state = _State.CODE
    string_delim: Optional[str] = None
    escaped = False

    line_markers = spec.line_markers
    block_start = spec.block_start or ""
    block_end = spec.block_end or ""

    for line_idx, line in enumerate(lines):
        # Fast-path: if we're in CODE state and the line has no markers,
        # pass through untouched (avoids per-character scanning).
        if state is _State.CODE and not _has_any_marker(line, spec):
            out_parts.append(line)
            continue

        # Slow-path: character-level state machine for this line.
        line_out: list[str] = []
        pos = 0
        length = len(line)

        while pos < length:
            ch = line[pos]

            # ---- IN_LINE_COMMENT ----
            if state is _State.IN_LINE_COMMENT:
                # Consume the rest of the line (don't emit)
                break

            # ---- IN_BLOCK_COMMENT ----
            if state is _State.IN_BLOCK_COMMENT:
                if block_end and line[pos: pos + len(block_end)] == block_end:
                    pos += len(block_end)
                    state = _State.CODE
                else:
                    pos += 1
                continue

            # ---- IN_STRING ----
            if state is _State.IN_STRING:
                if escaped:
                    line_out.append(ch)
                    escaped = False
                    pos += 1
                    continue
                if ch == "\\":
                    escaped = True
                    line_out.append(ch)
                    pos += 1
                    continue
                # Check for closing triple-quote
                if len(string_delim) == 3 and line[pos: pos + 3] == string_delim:
                    line_out.append(string_delim)
                    pos += 3
                    state = _State.CODE
                    string_delim = None
                    continue
                # Check for closing single-char quote
                if len(string_delim) == 1 and ch == string_delim:
                    line_out.append(ch)
                    pos += 1
                    state = _State.CODE
                    string_delim = None
                    continue
                line_out.append(ch)
                pos += 1
                continue

            # ---- CODE ----
            # String opening detection
            if ch in ('"', "'"):
                triple = ch * 3
                if line[pos: pos + 3] == triple:
                    line_out.append(triple)
                    pos += 3
                    state = _State.IN_STRING
                    string_delim = triple
                    continue
                line_out.append(ch)
                pos += 1
                state = _State.IN_STRING
                string_delim = ch
                continue

            # Backtick string (JS/Go template literals)
            if ch == "`":
                line_out.append(ch)
                pos += 1
                state = _State.IN_STRING
                string_delim = "`"
                continue

            # Block comment start
            if block_start and line[pos: pos + len(block_start)] == block_start:
                state = _State.IN_BLOCK_COMMENT
                pos += len(block_start)
                continue

            # Line comment start
            marker_matched = False
            for marker in line_markers:
                if line[pos: pos + len(marker)] == marker:
                    state = _State.IN_LINE_COMMENT
                    pos += len(marker)
                    marker_matched = True
                    break
            if marker_matched:
                continue

            # Regular code character
            line_out.append(ch)
            pos += 1

        # End of line
        if state is _State.IN_LINE_COMMENT:
            state = _State.CODE

        out_parts.append("".join(line_out))

    return "\n".join(out_parts)


# Regex: 3+ consecutive lines that are blank or whitespace-only → single blank line
_BLANK_EXPLOSION_RE = re.compile(r"(\n[ \t]*){3,}")


def _squash_blank_lines(text: str) -> str:
    """Collapse runs of 3+ blank lines to a single blank line.

    This prevents the visual 'explosion' of blank lines left behind
    when block comments spanning many lines are stripped.
    """
    return _BLANK_EXPLOSION_RE.sub("\n\n", text)
