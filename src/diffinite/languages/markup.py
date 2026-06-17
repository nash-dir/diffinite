"""Markup languages: HTML, XML, SVG, CSS, SCSS, LESS."""

from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

# HTML/XML/SVG: 따옴표는 속성값(데이터)이므로 문자열로 취급하지 않는다.
# 그렇지 않으면 어트리뷰트 안의 따옴표가 같은 줄의 <!-- --> 주석을 가려 버린다.
_HTML_COMMENT = CommentSpec(
    line_markers=(), block_start="<!--", block_end="-->",
    string_delims=(), template_delims=(),
)

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
# CSS도 따옴표를 데이터로 취급한다(content/url 등). 한쪽만 닫힌 따옴표가
# 같은 줄의 /* */ 주석을 가리는 오류를 막는다.
register(LangSpec(
    name="CSS",
    extensions=(".css",),
    comment=CommentSpec(
        line_markers=(), block_start="/*", block_end="*/",
        string_delims=(), template_delims=(),
    ),
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
