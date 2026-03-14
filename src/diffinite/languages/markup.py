"""Markup languages: HTML, XML, SVG, CSS, SCSS, LESS."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_HTML_COMMENT = CommentSpec(line_markers=(), block_start="<!--", block_end="-->")

# ── HTML / XML / SVG ──────────────────────────────────────────────
register(LangSpec(
    name="HTML",
    extensions=(".html", ".htm"),
    comment=_HTML_COMMENT,
))

register(LangSpec(
    name="XML",
    extensions=(".xml",),
    comment=_HTML_COMMENT,
))

register(LangSpec(
    name="SVG",
    extensions=(".svg",),
    comment=_HTML_COMMENT,
))

# ── CSS (block comments only) ────────────────────────────────────
register(LangSpec(
    name="CSS",
    extensions=(".css",),
    comment=CommentSpec(line_markers=(), block_start="/*", block_end="*/"),
))

# ── SCSS / LESS (line + block comments) ──────────────────────────
register(LangSpec(
    name="SCSS",
    extensions=(".scss",),
    comment=CommentSpec(line_markers=("//",), block_start="/*", block_end="*/"),
))

register(LangSpec(
    name="LESS",
    extensions=(".less",),
    comment=CommentSpec(line_markers=("//",), block_start="/*", block_end="*/"),
))
