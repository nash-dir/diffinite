"""PDF 생성, TOC 북마크, Bates 번호 부여.

법정 제출용 PDF 보고서 생성 파이프라인.

구현:
    - ``xhtml2pdf``: HTML -> PDF 변환. CSS subset만 지원 (@page, @frame).
    - ``pypdf``: Divide-and-Conquer 병합. 파일별 개별 PDF -> 최종 통합.
    - ``reportlab``: Bates 번호 오버레이 (각 페이지 하단 중앙).
    - 북마크: 계층적 TOC (Cover -> 파일별 Diff -> Deep Compare).

CSS 설계:
    ``_CSS_BODY``에 모든 스타일을 중앙 집중. xhtml2pdf는 최신 CSS를
    지원하지 않으므로, 인라인 스타일과 테이블 레이아웃 사용.
    font-family는 한글 폰트(Noto Sans KR, Malgun Gothic) 포함.

라인 번호 열 너비:
    ``differ.py``의 ``_calc_ln_width()``가 산정한 동적 너비를 사용.
    긴 파일(10,000줄+)에서 라인 번호 열이 넘치는 것을 방지.

호출관계:
    ``pipeline._generate_pdf_report()`` -> ``build_cover_body()``
    ``pipeline._generate_pdf_report()`` -> ``build_diff_page_html()``
    ``pipeline._generate_pdf_report()`` -> ``html_to_pdf()``
    ``pipeline._generate_pdf_report()`` -> ``merge_with_bookmarks()``
    ``pipeline._generate_pdf_report()`` -> ``add_bates_numbers()``
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import html
import io
import unicodedata
import json
import logging
import pkgutil
import re as _re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from xhtml2pdf import pisa

from diffinite import __version__
from diffinite.calibration import assess_normalize_metadata, threshold_disclosure
from diffinite.notices import (
    CONTAINMENT_NOTE,
    INCONCLUSIVE_NOTICE,
    INTEGRITY_NOTICE,
    SCOPE_NOTICE,
    SHORT_CODE_NOTICE,
)
from diffinite.models import (
    DeepMatchResult,
    DiffResult,
    FileHashEntry,
    count_label,
    deep_compare_comment_mode,
    hash_only_label,
    line_diff_comment_mode,
    line_match_label,
    name_similarity_label,
    overlap_label,
    threshold_label,
    threshold_source_label,
)

if TYPE_CHECKING:
    # build_cover_body's ``metadata`` param is annotated with this. Importing it
    # only under TYPE_CHECKING keeps the runtime import inside the function (to
    # avoid a circular import via models) while letting the forward-ref string
    # resolve under get_type_hints / static analysis.
    from diffinite.models import AnalysisMetadata, AnalysisStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------
def _resolve_font_from_lang(pdf_lang: str) -> str | None:
    """Find the first available font path for a given language from JSON maps."""
    # 1. Load built-in map via pkgutil (safe for PyInstaller/zipapps)
    builtin_map = {}
    try:
        data = pkgutil.get_data("diffinite", "pdf_fonts.json")
        if data:
            builtin_map = json.loads(data.decode("utf-8"))
    except Exception as e:
        logger.warning("Failed to load built-in pdf_fonts.json: %s", e)

    # 2. Load user override map (expansion packs)
    user_map = {}
    user_path = Path.home() / ".diffinite_fonts.json"
    if user_path.exists():
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                user_map = json.load(f)
                logger.info("Loaded custom font expansion pack: %s", user_path)
        except Exception as e:
            logger.warning("Failed to load custom ~/.diffinite_fonts.json: %s", e)

    # 3. Merge maps safely (user overrides built-in per language)
    merged_map = builtin_map.copy()
    for lang, os_dict in user_map.items():
        if not isinstance(os_dict, dict):
            logger.warning("Invalid format in ~/.diffinite_fonts.json for lang '%s'."
                           " Expected a dictionary of platforms, got %s.", lang, type(os_dict).__name__)
            continue
        
        if lang not in merged_map:
            merged_map[lang] = dict(os_dict)
        else:
            # New dict — a shallow builtin_map.copy() shares the nested per-lang
            # dicts by reference, so .update() would mutate the built-in map.
            merged_map[lang] = {**merged_map[lang], **os_dict}

    if pdf_lang not in merged_map:
        logger.warning(
            "Language '%s' not found in font maps. "
            "Add it to ~/.diffinite_fonts.json to extend support.", pdf_lang
        )
        return None

    # 4. Filter for current OS (sys.platform)
    plat = sys.platform
    if plat.startswith("linux"):
        plat = "linux"

    os_dict = merged_map[pdf_lang]
    if plat not in os_dict or not isinstance(os_dict[plat], list):
        logger.warning(
            "No valid font path list defined for language '%s' on platform '%s'.",
            pdf_lang, plat
        )
        return None

    # 5. Find the first path that actually exists (allowing ~ for home dir)
    paths = os_dict[plat]
    for p in paths:
        if not isinstance(p, str):
            continue
        # expanduser() resolves tildes like ~/.fonts/... cleanly
        candidate = Path(p).expanduser().resolve()
        if candidate.exists():
            return str(candidate)

    logger.warning(
        "None of the configured fonts for '%s' on %s exist on this system: %s",
        pdf_lang, plat, paths
    )
    return None


class PdfFontError(ValueError):
    """Raised when an explicitly requested PDF font cannot be loaded."""


def register_pdf_font(font_path: str | Path, role: str) -> str:
    """Register a TrueType font with reportlab/xhtml2pdf; return its family name.

    xhtml2pdf's own ``@font-face`` loader copies the font to a
    ``NamedTemporaryFile`` and reopens it by name, which Windows does not allow,
    and it cannot read ``file://`` URIs at all; both failures were silent. So
    the font is registered here directly and the CSS refers to it by the
    returned name. The name is derived from the resolved path, so the same file
    is registered once per process and different files never share a name.

    Raises:
        PdfFontError: the file is missing or is not a TrueType font reportlab
            can embed (e.g. a CFF-outline .otf).
    """
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFError, TTFont
    from xhtml2pdf import default as xhtml2pdf_default

    path = Path(font_path).expanduser().resolve()
    if not path.is_file():
        raise PdfFontError(f"PDF font file not found: {path}")
    # 12 hex chars (48 bits): only distinguishes font files used in one process.
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    name = f"Diffinite{role}-{digest}"
    if name not in pdfmetrics.getRegisteredFontNames():
        try:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        except (TTFError, OSError, ValueError) as exc:
            raise PdfFontError(
                f"Cannot load PDF font {path} (TrueType .ttf/.ttc required): {exc}"
            ) from exc
        # One face serves every weight/style, as xhtml2pdf's loader also does.
        for bold in (0, 1):
            for italic in (0, 1):
                addMapping(name, bold, italic, name)
    # xhtml2pdf resolves CSS font-family names (lower-cased) through this table.
    xhtml2pdf_default.DEFAULT_FONT[name.lower()] = name
    return name


# ---------------------------------------------------------------------------
# Glyph coverage: every character is drawn by a font that has it, or shown
# as a visible code point. Nothing is dropped silently.
# ---------------------------------------------------------------------------
# reportlab ships these Adobe CID fonts (Unicode UCS-2 CMaps, not embedded:
# the PDF viewer supplies the glyphs). Coverage is checked against the
# national character set each Adobe character collection is built on.
_CID_FONTS: dict[str, tuple[str, str, str]] = {
    # lang: (css class, reportlab font, codec for the coverage check)
    # Adobe-Korea1-2 (Adobe TN 5093): KS X 1001 plus all 11,172 Hangul syllables, i.e. cp949.
    "ko": ("g-ko", "HYGothic-Medium", "cp949"),
    # Adobe-Japan1 (Adobe TN 5078) is built on JIS X 0208, i.e. Shift_JIS.
    "ja": ("g-ja", "HeiseiKakuGo-W5", "shift_jis"),
    # Adobe-GB1-2 and later (Adobe TN 5079) cover GBK.
    "zh-cn": ("g-zhcn", "STSong-Light", "gbk"),
    # Adobe-CNS1 (Adobe TN 5080) is built on Big Five.
    "zh-tw": ("g-zhtw", "MSung-Light", "big5"),
}
_CID_DEFAULT_ORDER = ("ko", "ja", "zh-cn", "zh-tw")
_MARKER_CLASS = "cpm"
# Drawn with base-14 Symbol (PDF 32000-1 Annex D.5 lists "minus" at 055), so
# the deletion count's minus sign keeps the serif text's metrics and baseline.
_SYMBOL_CHARS = frozenset("−")
_GLYPH_NOTICE_TAG = "<!--diffinite:glyph-notice-->"


def _fix_cid_cmaps() -> None:
    """reportlab maps MSung-Light (Adobe-CNS1) to the GB CMap; use the CNS one.

    Adobe-CNS1 fonts take the UniCNS-UCS2-H CMap (Adobe TN 5080); with the GB
    CMap a Traditional Chinese character outside GB 2312 is not drawn.
    """
    from reportlab.pdfbase import _cidfontdata

    _cidfontdata.defaultUnicodeEncodings["MSung-Light"] = ("cht", "UniCNS-UCS2-H")


class _FontPlan:
    """Which font draws each character in the PDF, and the CSS for it.

    Order: the user's font (``--pdf-font`` or ``--pdf-lang``), the platform
    monospace face, then the CID fonts (the ``--pdf-lang`` one first). A
    character in Windows-1252 that is not a control character is left to the
    page's own font (Times or the code face draw all of Windows-1252).
    """

    def __init__(
        self,
        user: Optional[tuple[str, frozenset]] = None,
        mono: Optional[tuple[str, frozenset]] = None,
        lang: Optional[str] = None,
    ) -> None:
        self.user = user
        self.mono = mono
        self.lang = lang if lang in _CID_FONTS else None
        self._key_cache: dict[tuple[str, tuple[str, ...]], str] = {}
        self._cover_cache: dict[tuple[str, str], bool] = {}

    @property
    def css(self) -> str:
        rules = []
        if self.mono:
            rules.append(
                f'.difftbl, td.digest, table.key td.sw, .{_MARKER_CLASS} '
                f'{{ font-family: "{self.mono[0]}", "Courier"; }}'
            )
            rules.append(f'.g-mono {{ font-family: "{self.mono[0]}"; }}')
        if self.user:
            rules.append(f'.g-user {{ font-family: "{self.user[0]}"; }}')
        rules.append('.g-sym { font-family: "Symbol"; }')
        for cls, face, _codec in _CID_FONTS.values():
            rules.append(f'.{cls} {{ font-family: "{face}"; }}')
        # CJK faces have no bold or italic; never let them be synthesized.
        rules.append(
            ".g-user, .g-mono, .g-ko, .g-ja, .g-zhcn, .g-zhtw "
            "{ font-weight: normal; font-style: normal; }"
        )
        return "\n".join(rules) + "\n"

    def cid_order(self, text: str) -> tuple[str, ...]:
        """CID fonts to try for *text*: the script's own font first.

        A run with kana is Japanese and a run with Hangul is Korean; otherwise
        the ``--pdf-lang`` font comes first. A font that covers every
        character of the run is then preferred, so a line is not set in a mix
        of Korean, Japanese and Chinese glyph forms.
        """
        order = ([self.lang] if self.lang else []) + [
            lang for lang in _CID_DEFAULT_ORDER if lang != self.lang
        ]
        if _RE_KANA.search(text):
            order.remove("ja")
            order.insert(0, "ja")
        elif _RE_HANGUL.search(text):
            order.remove("ko")
            order.insert(0, "ko")
        needed = {ch for ch in text if self._needs_cid(ch)}
        if needed:
            for lang in order:
                if all(self._cid_covers(lang, ch) for ch in needed):
                    order.remove(lang)
                    order.insert(0, lang)
                    break
        return tuple(order)

    def _needs_cid(self, ch: str) -> bool:
        return (
            not _is_page_font_char(ch)
            and unicodedata.category(ch) != "Cc"
            and not (self.user and ord(ch) in self.user[1])
            and not (self.mono and ord(ch) in self.mono[1])
        )

    def _cid_covers(self, lang: str, ch: str) -> bool:
        key = (lang, ch)
        hit = self._cover_cache.get(key)
        if hit is None:
            # The UCS-2 CMaps reach the Basic Multilingual Plane only.
            hit = ord(ch) <= 0xFFFF
            if hit:
                try:
                    ch.encode(_CID_FONTS[lang][2])
                except UnicodeEncodeError:
                    hit = False
            self._cover_cache[key] = hit
        return hit

    def key_for(self, ch: str, order: tuple[str, ...] = ()) -> str:
        """"" (page font), a ``g-*`` font class, or the marker class."""
        if _is_page_font_char(ch):
            return ""
        order = order or self.cid_order(ch)
        cache_key = (ch, order)
        key = self._key_cache.get(cache_key)
        if key is not None:
            return key
        if unicodedata.category(ch) == "Cc":
            key = _MARKER_CLASS
        elif ch in _SYMBOL_CHARS:
            key = "g-sym"
        elif self.user and ord(ch) in self.user[1]:
            key = "g-user"
        elif self.mono and ord(ch) in self.mono[1]:
            key = "g-mono"
        else:
            key = next(
                (_CID_FONTS[lang][0] for lang in order if self._cid_covers(lang, ch)),
                _MARKER_CLASS,
            )
        self._key_cache[cache_key] = key
        return key


_PAGE_FONT_CACHE: dict[str, bool] = {}


def _is_page_font_char(ch: str) -> bool:
    """True for characters the page's own fonts draw: Windows-1252, no controls.

    Times and Courier are base-14 fonts with WinAnsiEncoding (PDF 32000-1
    Annex D), i.e. Windows-1252; the code faces cover it as well. Tab, line
    feed and carriage return are layout, not glyphs.
    """
    hit = _PAGE_FONT_CACHE.get(ch)
    if hit is None:
        if ch in "\t\n\r":
            hit = True
        elif unicodedata.category(ch) == "Cc":
            hit = False
        else:
            try:
                ch.encode("cp1252")
                hit = True
            except UnicodeEncodeError:
                hit = False
        _PAGE_FONT_CACHE[ch] = hit
    return hit


@functools.lru_cache(maxsize=None)
def _ttf_cmap(name: str) -> frozenset:
    """Code points a registered TrueType font maps to a real glyph."""
    from reportlab.pdfbase import pdfmetrics

    face = pdfmetrics.getFont(name).face
    return frozenset(cp for cp, gid in face.charToGlyph.items() if gid)


def _mono_font_path() -> Optional[str]:
    if sys.platform == "win32":
        return "C:/Windows/Fonts/consola.ttf"
    if sys.platform == "darwin":
        return "/System/Library/Fonts/Menlo.ttc"
    return None


def _font_plan(pdf_font: Optional[str], pdf_lang: Optional[str] = None) -> _FontPlan:
    """Register the PDF fonts and return the plan that assigns them.

    If *pdf_font* is given it is tried first for every character the page
    font cannot draw; a font that cannot be loaded is logged and skipped. If
    not, but *pdf_lang* is given, the font path comes from the JSON map. The
    platform monospace face (Consolas / Menlo) sets diff code when present.
    """
    _fix_cid_cmaps()
    lang = pdf_lang.lower() if pdf_lang else None
    font_path = pdf_font
    if not font_path and lang:
        font_path = _resolve_font_from_lang(lang)

    user = None
    if font_path:
        try:
            name = register_pdf_font(font_path, "UserCJK")
        except PdfFontError as exc:
            logger.error("%s; the built-in CID fonts are used instead.", exc)
        else:
            user = (name, _ttf_cmap(name))

    mono = None
    mono_path = _mono_font_path()
    if mono_path and Path(mono_path).is_file():
        try:
            name = register_pdf_font(mono_path, "UserMono")
        except PdfFontError as exc:
            logger.warning("%s; code falls back to Courier.", exc)
        else:
            mono = (name, _ttf_cmap(name))
    return _FontPlan(user, mono, lang)


def _build_font_face_css(pdf_font: Optional[str], pdf_lang: Optional[str] = None) -> str:
    """CSS rules for the PDF fonts; must be placed after ``_CSS_BODY``."""
    return _font_plan(pdf_font, pdf_lang).css


# ---------------------------------------------------------------------------
# CSS (shared across all generated pages)
# ---------------------------------------------------------------------------
_CSS_BODY = """\
/* Shared by the PDF (xhtml2pdf CSS subset: no flexbox/grid, tables for
   layout) and the HTML reports. Black text, fine rules, no filled header
   bands; color is never the only carrier of meaning. */
body {
    font-family: "Times New Roman", "Times", serif;
    font-size: 9.5pt;
    color: #111;
    background: #fff;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
}
p { margin: 0 0 5pt 0; }
h1 {
    font-size: 20pt;
    font-weight: bold;
    color: #000;
    margin: 0 0 10pt 0;
}
h2 {
    font-size: 12pt;
    font-weight: bold;
    color: #000;
    margin: 14pt 0 4pt 0;
    -pdf-keep-with-next: true;
    page-break-after: avoid;
}
h3 {
    font-size: 10pt;
    font-weight: bold;
    color: #000;
    margin: 10pt 0 3pt 0;
    -pdf-keep-with-next: true;
    page-break-after: avoid;
}
.newpage { page-break-before: always; }
.doc-tool {
    font-size: 9pt;
    color: #444;
    margin: 0 0 3pt 0;
}
.note {
    font-size: 8.5pt;
    color: #333;
    margin: 0 0 8pt 0;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
}
.alert {
    border: 0.75pt solid #000;
    padding: 5pt 7pt;
    margin: 6pt 0 10pt 0;
    color: #000;
}
.alert b { font-weight: bold; }
.num { text-align: right; }
.pct { white-space: nowrap; }
.flag { font-style: italic; color: #333; }
ol.notices {
    font-size: 9pt;
    margin: 2pt 0 8pt 0;
    padding-left: 14pt;
}
ol.notices li {
    margin: 0 0 3pt 0;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
}
/* Key/value tables: cover particulars, configuration, status */
table.kv {
    border-collapse: collapse;
    width: 100%;
    margin: 2pt 0 8pt 0;
    font-size: 8.5pt;
    table-layout: fixed;
}
table.kv td {
    padding: 1.5pt 6pt 1pt 0;
    vertical-align: top;
    text-align: left;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
}
table.kv td.k { color: #444; }
/* Rules are rows of their own, one cell spanning the table, so each prints
   as one unbroken line (per-cell borders leave a step at every column). */
tr.rule td, tr.hair td { padding: 0; height: 0; font-size: 1pt; line-height: 1pt; }
tr.rule td { border-top: 0.75pt solid #000; }
tr.hair td { border-top: 0.5pt solid #c8c8c8; }
/* Register tables: Summary, Deep Compare, SHA-256 */
table.summary, table.deep {
    border-collapse: collapse;
    width: 100%;
    margin: 2pt 0 10pt 0;
    font-size: 8.5pt;
    table-layout: fixed;
}
table.summary th, table.deep th {
    font-weight: bold;
    color: #000;
    background: none;
    text-align: left;
    vertical-align: bottom;
    padding: 2pt 4pt;
}
table.summary td, table.deep td {
    padding: 1.5pt 4pt;
    vertical-align: top;
    text-align: left;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
    overflow: hidden;
}
table.summary th.num, table.summary td.num,
table.deep th.num, table.deep td.num { text-align: right; }
td.digest {
    font-family: "Courier New", "Courier", monospace;
    font-size: 7.5pt;
}
div.unmatched {
    font-size: 9pt;
    margin: 2pt 0 8pt 0;
}
div.unmatched p {
    margin: 0 0 1.5pt 0;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
}
.meta {
    font-size: 9pt;
    color: #222;
    margin: 0 0 6pt 0;
    pdf-word-wrap: CJK;
    word-wrap: break-word;
}
/* ---- Side-by-side diff table ---- */
.difftbl {
    border-collapse: collapse;
    table-layout: fixed;
    width: 100%;
    font-family: "UserMono", "Consolas", "Courier New", monospace;
    font-size: 7pt;
    margin-bottom: 14pt;
}
/* Top padding of 1.5 pt: with 0.5 pt, CJK glyph tops (HeiseiKakuGo,
   HYGothic) touched the rule above the first row and the inline text
   background started 0.27 pt above the row, over the hairline. 1 pt leaves
   only 0.23 pt, so 1.5 pt keeps 0.73 pt for fonts with a taller ascent
   (measured in the rendered PDF). No bottom padding: the 7 pt line box
   already leaves 5.3 pt below the baseline; the row pitch is 12 pt.
   Right padding of 6 pt: with CJK line breaking a closing bracket or quote
   is never moved to the next line and may hang past the line end by one
   3.85 pt character, so code cells keep 6 pt. */
.difftbl th, .difftbl td {
    border: none;
    border-bottom: 0.25pt solid #e2e2e2;
    padding: 1.5pt 3pt 0 3pt;
    vertical-align: top;
    word-wrap: break-word;
    overflow: hidden;
}
.difftbl td.code { padding-right: 6pt; }
/* xhtml2pdf applies a cell's vertical padding twice to text placed directly
   in the cell (the line numbers) but once to a <pre> (the code). Measured
   from the row top: number baseline 4.83 pt + 2 x padding, code baseline
   5.2 pt + padding. 0.95 pt puts the 6.5 pt number on the 7 pt code
   baseline (0.03 pt apart) without making the row taller. */
.difftbl td.ln { padding-top: 0.95pt; padding-bottom: 0; }
.difftbl thead th {
    background: none;
    color: #000;
    font-weight: bold;
    font-size: 7.5pt;
    padding: 3pt 3pt;
    text-align: left;
    border-bottom: none;
}
.difftbl tr.rule td { border-top: 0.75pt solid #000; border-bottom: none; padding: 0; }
.ln {
    text-align: right;
    color: #555;
    font-size: 6.5pt;
    padding-right: 3pt;
}
.difftbl td.ln, .difftbl th.ln { border-right: 0.5pt solid #b4b4b4; }
.difftbl thead th.ln { text-align: right; color: #000; }
.difftbl td.lnb, .difftbl th.lnb { border-left: 1pt solid #000; }
.code {
    white-space: pre-wrap;
    word-wrap: break-word;
}
/* Hanging indent: a wrapped code line continues two characters in, so a
   continuation never looks like a new line (8 pt is two 7 pt monospace
   characters at the 0.55 em advance of Consolas and Courier). */
.code pre {
    margin: 0;
    padding: 0 0 0 8pt;
    text-indent: -8pt;
    font-size: inherit;
    font-family: inherit;
    white-space: pre-wrap;
    word-wrap: break-word;
}
/* Changed lines carry a rule as well as a tint, so they stay visible in
   black-and-white print; the side (A or B) tells deletion from addition. */
.del { background: #f6e0e0; }
.add { background: #e0efe0; }
.chg { background: #f3eedb; }
.moved-del { background: #ebe3f1; }
.moved-add { background: #e0e8f2; }
/* No counterpart line: white, without a bar, ruled above and below in a
   mid grey. A grey fill was hard to tell from the change tints in
   greyscale print; xhtml2pdf draws every border solid (no dotted or
   dashed style), so the distinction is white plus ruled lines. */
.empty { background: #fff; }
.difftbl td.empty { border-top: 0.5pt solid #9a9a9a; border-bottom: 0.5pt solid #9a9a9a; }
.difftbl td.bar { border-left: 2pt solid #222; }
.mv { font-weight: bold; color: #000; }
/* Word-level marks follow the redline convention: struck = only in A,
   underlined = only in B. */
.word-del { background-color: #e9c2c2; text-decoration: line-through; }
.word-add { background-color: #c4dfc4; text-decoration: underline; }
/* Changed whitespace: a light tint only. A struck or underlined run of
   spaces would read as dash characters in the source. */
.ws { background-color: #dedede; text-decoration: none; }
/* A character no PDF font can draw, shown as its code point: [U+1F600]. */
.cpm {
    font-family: "Courier New", "Courier", monospace;
    background-color: #dcdcdc;
    color: #000;
    font-weight: normal;
    font-style: normal;
}
/* Diff key */
table.key {
    border-collapse: collapse;
    font-size: 7.5pt;
    margin: 0 0 6pt 0;
}
table.key td {
    padding: 1pt 3pt 1pt 0;
    vertical-align: middle;
    border: none;
}
table.key td.sw {
    width: 14pt;
    border: 0.5pt solid #b4b4b4;
    font-family: "UserMono", "Consolas", "Courier New", monospace;
    font-size: 7pt;
    text-align: center;
}
table.key td.bar { border-left: 2pt solid #222; }
table.key td.gap { width: 10pt; }
/* Running header and footer (PDF frames) */
.runhead {
    width: 100%;
    font-size: 7.5pt;
    color: #222;
    border-bottom: 0.5pt solid #000;
}
.runhead td { padding: 0 0 2pt 0; vertical-align: bottom; border: none; }
.runfoot {
    width: 100%;
    font-size: 7.5pt;
    color: #222;
}
.runfoot td { padding: 0; vertical-align: bottom; border: none; }
"""

# Screen-only additions for the HTML reports (never given to xhtml2pdf).
_CSS_SCREEN = """\
body {
    max-width: 1500px;
    margin: 32px auto;
    padding: 0 32px;
    font-size: 15px;
    line-height: 1.45;
}
h1 { font-size: 28px; }
h2 { font-size: 19px; margin-top: 30px; }
h3 { font-size: 15px; }
.doc-tool, .meta, .note, ol.notices { font-size: 13px; }
table.kv, table.summary, table.deep { font-size: 13.5px; }
td.digest { font-family: Consolas, "Courier New", monospace; font-size: 12px; }
table.key { font-size: 12px; width: auto !important; }
table.key td { width: auto !important; white-space: nowrap; }
table.key td:empty { padding-left: 12px; }
table.key td.sw { min-width: 18px; }
table.kv td { padding: 2px 8px 2px 0; }
table.summary td, table.deep td { padding: 3px 6px; }
.difftbl { font-size: 12px; }
.difftbl thead th { font-size: 12px; }
.ln { font-size: 11px; }
.code pre { tab-size: 8; padding-left: 2ch; text-indent: -2ch; }
.difftbl th, .difftbl td { padding: 1px 4px; }
.difftbl td.ln { padding-top: 1px; padding-bottom: 1px; }
.difftbl td.code { padding-right: 8px; }
.empty {
    background: repeating-linear-gradient(135deg, #fff 0 3px, #e4e4e4 3px 4px);
}
.difftbl td.empty { border-top: none; border-bottom-color: #e2e2e2; }
tr.rule td, tr.hair td { font-size: 0; line-height: 0; }
a { color: #1f3a68; }
section.pair { margin-top: 36px; }
@media print {
    body { max-width: none; margin: 0; padding: 0; font-size: 9.5pt; }
    section.pair { break-before: page; margin-top: 0; }
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    a { color: inherit; text-decoration: none; }
}
"""

REPORT_TITLE = "Source Code Comparison Report"
DEEP_COMPARE_HEADING = "Deep Compare: Cross-Match Results"
"""The Deep Compare section heading; its PDF bookmark has the same words."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _break_path(path_str: str) -> str:
    """Return the path string escaped. (Word wrapping is handled by pdf-word-wrap: CJK in CSS)."""
    return path_str


def _ratio_badge(ratio: float) -> str:
    """Return the line (or word) match ratio as a plain percentage span.

    No color banding: a red/amber/green band reads as a verdict, and the
    report states how much is similar, not what that means.
    """
    # line_match_label shows 100.0% only for exactly 1.0, never a rounded 0.9996.
    return f'<span class="pct">{line_match_label(ratio)}</span>'


MINUS = "\u2212"
"""U+2212 MINUS SIGN, for deletion counts (a hyphen is not a minus)."""


def signed_count(n: int, sign: str) -> str:
    """A change count with its sign: "+1,098" or "\u22121,098"."""
    return f"{MINUS if sign == '-' else '+'}{count_label(n)}"


def _plural(n: int, singular: str, plural: Optional[str] = None) -> str:
    """"1 line", "2 lines" (count with thousands separators)."""
    return f"{count_label(n)} {singular if n == 1 else (plural or singular + 's')}"


_RE_CELL_WIDTH = _re.compile(r'<t[hd]\b[^>]*?style="[^"]*?width:\s*([0-9.]+(?:%|pt|px))')


def colgroup_html(widths: Sequence[str]) -> str:
    """``<colgroup>`` declaring each column's width ("" when none are given).

    A browser lays out a ``table-layout: fixed`` table from its first row.
    In the ruled tables that row is a spanning rule, so without ``<col>``
    widths every column comes out equally wide. xhtml2pdf ignores
    ``<colgroup>`` and keeps taking the widths from the cells.
    """
    if not widths:
        return ""
    cols = "".join(f'<col style="width: {w};">' if w else "<col>" for w in widths)
    return f"<colgroup>{cols}</colgroup>\n"


def ruled_table(
    cls: str,
    ncols: int,
    rows: Sequence[str],
    header: str = "",
) -> str:
    """A register table with a rule above and below and hairlines between rows.

    Each rule is a row of its own whose single cell spans every column, so it
    prints as one unbroken line; xhtml2pdf draws per-cell borders as separate
    segments that leave a step at every column joint. The column widths come
    from the header cells (or the first row's) and are repeated in a
    ``<colgroup>`` for browsers.
    """
    rule = f'<tr class="rule"><td colspan="{ncols}"></td></tr>\n'
    hair = f'<tr class="hair"><td colspan="{ncols}"></td></tr>\n'
    widths = _RE_CELL_WIDTH.findall(header or (rows[0] if rows else ""))
    out = [f'<table class="{cls}">\n', colgroup_html(widths), rule]
    if header:
        out += [header, rule]
    for i, row in enumerate(rows):
        if i:
            out.append(hair)
        out.append(row)
    out += [rule, "</table>\n"]
    return "".join(out)


def build_hash_table_html(
    hashes_a: list[FileHashEntry],
    hashes_b: list[FileHashEntry],
) -> str:
    """Build an HTML table showing the full SHA-256 digest of every analyzed file.

    Used when ``--hash`` is specified to embed integrity data
    directly in the PDF/HTML cover page. The full 64-hex digest is printed
    (wrapped with ``word-break``) so a reader can check a file against the
    printed value without the manifest.
    """
    parts: list[str] = []
    parts.append('<h2>Evidence Integrity: SHA-256 Hashes</h2>\n')

    for label, hashes in [("Directory A", hashes_a), ("Directory B", hashes_b)]:
        if not hashes:
            continue
        parts.append(f'<h3>{html.escape(label)}</h3>\n')
        header = (
            '<tr><th class="num" style="width: 5%;">#</th>'
            '<th style="width: 43%;">File</th>'
            '<th style="width: 40%;">SHA-256</th>'
            '<th class="num" style="width: 12%;">Size (bytes)</th></tr>\n'
        )
        rows = [
            # Full digest: an abbreviated hash cannot be checked against a file.
            f'<tr>'
            f'<td class="num">{count_label(idx)}</td>'
            f'<td>{_break_path(html.escape(h.rel_path))}</td>'
            f'<td class="digest" style="word-break:break-all">{html.escape(h.sha256)}</td>'
            f'<td class="num">{count_label(h.size_bytes)}</td>'
            f'</tr>\n'
            for idx, h in enumerate(hashes, 1)
        ]
        parts.append(ruled_table("summary", 4, rows, header))

    parts.append(f'<p class="note">{html.escape(INTEGRITY_NOTICE)}</p>\n')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Glyph assignment (tag-safe)
# ---------------------------------------------------------------------------
import re as _re

_RE_HTML_TAG = _re.compile(r'(<[^>]+>)')
# Kana (Hiragana, Katakana, Katakana Phonetic Extensions, halfwidth Katakana)
# and Hangul (Jamo, Compatibility Jamo, Syllables): Unicode 15.1 Blocks.txt.
_RE_KANA = _re.compile(r'[぀-ヿㇰ-ㇿｦ-ﾟ]')
_RE_HANGUL = _re.compile(r'[ᄀ-ᇿ㄰-㆏가-힯]')
# One HTML character reference, or one character.
_RE_TEXT_TOKEN = _re.compile(r'&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);|.', _re.S)


def code_point_marker(ch: str) -> str:
    """The visible stand-in for a character no PDF font can draw: [U+1F600]."""
    return f"[U+{ord(ch):04X}]"


def _apply_glyph_fonts(
    html_text: str,
    plan: _FontPlan,
    counts: Optional[dict[str, int]] = None,
) -> str:
    """Set each text run in a font that has its glyphs.

    Only text nodes are changed (never tags or attributes). A character the
    page font cannot draw goes in a ``<span class="g-...">`` for the font
    chosen by *plan*; a character no font covers is replaced by its code
    point in a ``<span class="cpm">`` and counted in *counts*.
    """
    parts = _RE_HTML_TAG.split(html_text)
    for i, part in enumerate(parts):
        if not part or part.startswith('<'):
            continue
        if all(_is_page_font_char(ch) for ch in part):
            continue
        order = plan.cid_order(part)
        out: list[str] = []
        run: list[str] = []
        run_key = ""

        def flush() -> None:
            if run:
                text = "".join(run)
                out.append(f'<span class="{run_key}">{text}</span>' if run_key else text)
                run.clear()

        for tok in _RE_TEXT_TOKEN.findall(part):
            if len(tok) > 1:  # a character reference: always plain text
                key, piece = "", tok
            else:
                key = plan.key_for(tok, order)
                piece = tok
                if key == _MARKER_CLASS:
                    piece = code_point_marker(tok)
                    if counts is not None:
                        counts[tok] = counts.get(tok, 0) + 1
            if key != run_key:
                flush()
                run_key = key
            run.append(piece)
        flush()
        parts[i] = "".join(out)
    return "".join(parts)


def _glyph_notice_html(counts: dict[str, int]) -> str:
    """The cover notice for characters shown as code points ("" when none)."""
    total = sum(counts.values())
    if not total:
        return ""
    if total == 1:
        text = (
            "1 character could not be drawn by the PDF fonts and is shown as a "
            "Unicode code point in square brackets; the HTML report shows it as written."
        )
    else:
        text = (
            f"{count_label(total)} characters could not be drawn by the PDF fonts and "
            "are shown as Unicode code points in square brackets; the HTML report "
            "shows them as written."
        )
    return f"<li>{html.escape(text)}</li>"


def _uncovered_counts(html_texts: Sequence[str], plan: _FontPlan) -> dict[str, int]:
    """Count the characters in *html_texts* that *plan* shows as code points."""
    counts: dict[str, int] = {}
    for text in html_texts:
        if text:
            _apply_glyph_fonts(text, plan, counts)
    return counts


def _encode_glyph_notice(counts: dict[str, int]) -> str:
    """The cover placeholder, carrying the counts found on the diff pages."""
    if not counts:
        return _GLYPH_NOTICE_TAG
    data = " ".join(f"{ord(ch):X}:{n}" for ch, n in sorted(counts.items()))
    return f"<!--diffinite:glyph-notice {data}-->"


_RE_GLYPH_NOTICE = _re.compile(r"<!--diffinite:glyph-notice((?: [0-9A-F]+:[0-9]+)*)-->")


def _expand_glyph_notice(body: str, plan: _FontPlan, own_counts: dict[str, int]) -> str:
    """Replace the cover placeholder with the notice, or remove it.

    The placeholder lists characters the built-in fonts cannot draw on the
    diff pages; those the user's font does draw are dropped from the count.
    """
    def repl(m: "_re.Match[str]") -> str:
        counts = dict(own_counts)
        for item in m.group(1).split():
            cp, n = item.split(":")
            ch = chr(int(cp, 16))
            if plan.key_for(ch) == _MARKER_CLASS:
                counts[ch] = counts.get(ch, 0) + int(n)
        return _glyph_notice_html(counts)

    return _RE_GLYPH_NOTICE.sub(repl, body)


def _html_wrap(
    title: str,
    body: str,
    annotation_html: str = "",
    *,
    has_footer: bool = False,
    has_header: bool = False,
    pdf_font: Optional[str] = None,
    pdf_lang: Optional[str] = None,
) -> str:
    """Wrap body content in a full HTML document with CSS (the PDF path).

    Every character is assigned a font that draws it, or replaced by a
    visible code point; the cover's glyph notice is filled in here, where the
    fonts are known.
    """
    plan = _font_plan(pdf_font, pdf_lang)
    counts: dict[str, int] = {}
    body = _apply_glyph_fonts(body, plan, counts)
    body = _expand_glyph_notice(body, plan, counts)
    if annotation_html:
        annotation_html = _apply_glyph_fonts(annotation_html, plan)

    # A4 landscape. The footer frame's line shares its baseline with the Bates
    # stamp (_BATES_BASELINE, see add_bates_numbers) so page, file and Bates
    # labels read as one line; the header frame carries the running title.
    margin_bottom = "1.5cm" if has_footer else "1.2cm"
    margin_top = "1.7cm" if has_header else "1.2cm"

    frames = ""
    if has_footer:
        frames += """
    @frame footer_frame {
        -pdf-frame-content: pageFooter;
        left: 1.2cm;
        right: 1.2cm;
        bottom: 0.3cm;
        height: 0.6cm;
    }"""
    if has_header:
        frames += """
    @frame header_frame {
        -pdf-frame-content: pageHeader;
        left: 1.2cm;
        right: 1.2cm;
        top: 0.7cm;
        height: 0.8cm;
    }"""

    font_face_css = plan.css

    page_css = f"""@page {{
    size: A4 landscape;
    margin: {margin_top} 1.2cm {margin_bottom} 1.2cm;{frames}
}}"""

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
{page_css}
{_CSS_BODY}
{font_face_css}</style>
</head>
<body>
{annotation_html}
{body}
</body>
</html>
"""


def _build_annotation_html(
    *,
    show_page_number: bool = False,
    show_file_number: bool = False,
    file_index: int = 0,
    total_files: int = 0,
    show_filename: bool = False,
    filename: str = "",
    running_title: str = "",
) -> tuple[str, bool, bool]:
    """Build the running header/footer divs for xhtml2pdf's @frame mechanism.

    Header: *running_title* on the left, the A-side path on the right when
    ``show_filename``. Footer: file number on the left, page number within
    this section on the right; the center is left free for the Bates stamp.
    """
    parts: list[str] = []
    has_footer = show_page_number or show_file_number
    has_header = bool(running_title) or (show_filename and bool(filename))

    if has_footer:
        left_cell = ""
        right_cell = ""
        if show_file_number and total_files > 0:
            left_cell = f'File {file_index} of {total_files}'
        if show_page_number:
            right_cell = 'Page <pdf:pagenumber> of <pdf:pagecount>'
        parts.append(
            f'<div id="pageFooter">'
            f'<table class="runfoot"><tr>'
            f'<td style="text-align:left;width:35%;">{left_cell}</td>'
            f'<td style="width:30%;"></td>'
            f'<td style="text-align:right;width:35%;">{right_cell}</td>'
            f'</tr></table>'
            f'</div>'
        )

    if has_header:
        right = html.escape(filename) if show_filename and filename else ""
        parts.append(
            f'<div id="pageHeader">'
            f'<table class="runhead"><tr>'
            f'<td style="text-align:left;width:30%;">{html.escape(running_title)}</td>'
            f'<td style="text-align:right;width:70%;">{right}</td>'
            f'</tr></table>'
            f'</div>'
        )

    return "\n".join(parts), has_footer, has_header


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------
def excluded_inputs_html(analysis_status: "AnalysisStatus") -> str:
    """The Excluded Inputs section: one table row per input, so a long list
    breaks across PDF pages; "" when the list is not shown inline."""
    from diffinite.notices import EXCLUDED_INPUTS_HEADING, excluded_input_rows

    rows = excluded_input_rows(analysis_status)
    if not rows:
        return ""
    return f"<h2>{EXCLUDED_INPUTS_HEADING}</h2>\n" + kv_table_html([
        (html.escape(path), html.escape(reason)) for path, reason in rows
    ])


def kv_table_html(rows: Sequence[tuple[str, str]]) -> str:
    """Two-column label/value table with fine rules (labels/values are trusted HTML).

    Every cell carries its width: xhtml2pdf otherwise collapses the label
    column when a label cell is blank.
    """
    if not rows:
        return ""
    return ruled_table("kv", 2, [
        f'<tr><td class="k" style="width: 22%;">{label or "&nbsp;"}</td>'
        f'<td style="width: 78%;">{value}</td></tr>\n'
        for label, value in rows
    ])


def pdf_conventions(
    *,
    show_page_number: bool = False,
    show_file_number: bool = False,
    show_filename: bool = False,
    show_bates_number: bool = False,
    bates_prefix: str = "",
    bates_suffix: str = "",
    bates_start: int = 1,
) -> list[tuple[str, str]]:
    """Describe the PDF's page furniture for the cover (label, plain text)."""
    rows: list[tuple[str, str]] = []
    if show_page_number:
        rows.append((
            "Page numbers",
            "Page n of N in the footer, counted separately for the cover "
            "section and for each file pair",
        ))
    if show_file_number:
        rows.append((
            "File numbers",
            "File n of N in the footer; n is the row number in the Summary table",
        ))
    if show_filename:
        rows.append(("Running header", "Path of File A on every diff page"))
    if show_bates_number:
        detail = f"Bottom center of every page, numbered from {bates_start}"
        if bates_prefix:
            detail += f', prefix "{bates_prefix}"'
        if bates_suffix:
            detail += f', suffix "{bates_suffix}"'
        rows.append(("Bates numbers", detail))
    return rows


def config_rows(metadata: "AnalysisMetadata") -> list[tuple[str, str]]:
    """Analysis Configuration rows (label, HTML) shared by every HTML/PDF page."""
    rows: list[tuple[str, str]] = [
        ("Mode", html.escape(metadata.exec_mode)),
        ("K-gram size (K)", count_label(metadata.k)),
        ("Window size (W)", count_label(metadata.w)),
        ("Jaccard threshold", html.escape(threshold_label(metadata.threshold))),
        ("Threshold source", html.escape(threshold_source_label(metadata.threshold_provenance))),
        ("Identifier normalization", "on" if metadata.normalize else "off"),
    ]
    if metadata.lang_aware:
        rows.append(("Language-aware tokenization", "on"))
    rows += [
        ("Line diff autojunk", "on" if metadata.autojunk else "off"),
        (
            "Ignore policy",
            f"{_plural(len(metadata.ignore_patterns), 'rule')}; SHA-256 "
            + html.escape(metadata.ignore_file_sha256 or "none"),
        ),
        (
            "Selection filter",
            ("applied" if metadata.filter_applied else "none")
            + f"; {_plural(len(metadata.filter_paths), 'path')}; SHA-256 "
            + html.escape(metadata.filter_file_sha256 or "none"),
        ),
    ]
    from diffinite.notices import policy_config_rows

    rows += [(label, html.escape(value)) for label, value in policy_config_rows(metadata)]
    return rows


def report_notices(metadata: Optional["AnalysisMetadata"]) -> list[str]:
    """Scope and Limitations notices (plain text), in report order."""
    notices = [SCOPE_NOTICE, SHORT_CODE_NOTICE]
    if metadata is not None and metadata.exec_mode == "deep":
        notices.append(threshold_disclosure(
            metadata.threshold,
            metadata.threshold_provenance,
            metadata.normalize,
            assessment=assess_normalize_metadata(metadata) if metadata.normalize else None,
        ))
    return notices


def limitations_html(metadata: Optional["AnalysisMetadata"]) -> str:
    """The Scope and Limitations section (HTML)."""
    items = "".join(f"<li>{html.escape(n)}</li>\n" for n in report_notices(metadata))
    return f'<h2>Scope and Limitations</h2>\n<ol class="notices">\n{items}</ol>\n'


def incomplete_notice(
    metadata: Optional["AnalysisMetadata"],
    analysis_status: Optional["AnalysisStatus"],
) -> Optional[str]:
    """Plain-text completeness warning, or None when the analysis is complete.

    Each recorded reason is stated once, in plain words; the internal reason
    codes stay in the JSON report.
    """
    sentences: list[str] = []
    incomplete = analysis_status is not None and analysis_status.state == "incomplete"
    if incomplete:
        for reason in analysis_status.reasons:
            sentence = INCOMPLETE_REASON_TEXT.get(reason, _UNKNOWN_REASON_TEXT)
            if sentence not in sentences:
                sentences.append(sentence)
    index_sentence = INCOMPLETE_REASON_TEXT["deep-index-truncated"]
    if metadata is not None and metadata.deep_index_truncated and index_sentence not in sentences:
        sentences.append(index_sentence)
    if not sentences:
        return None
    if incomplete:
        return (
            f"{INCOMPLETE_LEAD} " + " ".join(sentences)
            + " The Analysis Status section gives the counts."
        )
    return " ".join(sentences)


INCOMPLETE_LEAD = "Incomplete analysis."

INCOMPLETE_REASON_TEXT: dict[str, str] = {
    "collection-file-skipped": "Some input files could not be read.",
    "collection-file-unhashed": "Some input files could not be hashed.",
    "diff-worker-failure": (
        "A comparison process failed, so some file pairs were not compared."
    ),
    "diff-pair-error": (
        "Some file pairs were not compared because a file could not be read or decoded."
    ),
    "diff-payload-truncated": (
        "Some side-by-side diffs were over the size limit and are not included."
    ),
    "deep-file-or-worker-failure": "Some files could not be processed by Deep Compare.",
    "deep-index-truncated": (
        "The Deep Compare index reached the --max-index-entries limit, so some "
        "cross-matches are not reported."
    ),
}
"""``AnalysisStatus.reasons`` code to the sentence shown in reports."""

_UNKNOWN_REASON_TEXT = "Another part of the analysis did not complete."


def alert_html(text: Optional[str]) -> str:
    """The incomplete-analysis box: only the lead-in is bold."""
    if not text:
        return ""
    if text.startswith(INCOMPLETE_LEAD):
        rest = text[len(INCOMPLETE_LEAD):]
        return (
            f'<div class="alert"><b>{html.escape(INCOMPLETE_LEAD)}</b>'
            f"{html.escape(rest)}</div>\n"
        )
    return f'<div class="alert">{html.escape(text)}</div>\n'


def status_rows(analysis_status: "AnalysisStatus") -> list[tuple[str, str]]:
    """Analysis Status as labelled rows (label, plain text).

    The rows are ``notices.analysis_status_rows``, so the PDF, HTML and
    Markdown reports and the extension use the same labels and values.
    """
    from diffinite.notices import analysis_status_rows

    return analysis_status_rows(analysis_status)


def build_cover_body(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    strip_comments: bool,
    *,
    deep_results: Optional[list[DeepMatchResult]] = None,
    metadata: Optional["AnalysisMetadata"] = None,
    analysis_status: Optional["AnalysisStatus"] = None,
    hash_table_html: Optional[str] = None,
    include_uncompared: bool = True,
    uncompared_mode: str = "",
    conventions: Sequence[tuple[str, str]] = (),
) -> str:
    """Build the cover-page body fragment (no DOCTYPE/html/head wrapper).

    The particulars, configuration, status, limitations, Summary (exhibit
    index), unmatched lists, Deep Compare table and SHA-256 table follow one
    another without forced page breaks.
    """
    unit = "word" if by_word else "line"
    comment_mode = line_diff_comment_mode(strip_comments, metadata)
    deep_comment_mode = deep_compare_comment_mode(strip_comments, metadata)
    if deep_comment_mode in ("not-applicable", comment_mode):
        comment_rows = [("Comments", html.escape(comment_mode))]
    else:
        # --normalize --lang-aware drops lexer comment tokens in the deep channel
        # regardless of --strip-comments; report each channel truthfully.
        comment_rows = [
            ("Comments (line diff)", html.escape(comment_mode)),
            ("Comments (Deep Compare)", html.escape(deep_comment_mode)),
        ]

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    particulars = [
        ("Directory A", _break_path(html.escape(dir_a))),
        ("Directory B", _break_path(html.escape(dir_b))),
        ("Report generated", generated),
        ("Tool", f"Diffinite {html.escape(__version__)}"),
        ("Comparison unit", unit),
        *comment_rows,
        ("Matched pairs", count_label(len(results))),
        (
            "Unmatched files",
            f"{count_label(len(unmatched_a))} in A; {count_label(len(unmatched_b))} in B",
        ),
        *((html.escape(k), html.escape(v)) for k, v in conventions),
    ]
    particulars_html = kv_table_html(particulars)

    meta_html = ""
    if metadata is not None:
        meta_html = "<h2>Analysis Configuration</h2>\n" + kv_table_html(config_rows(metadata))
    status_html = ""
    alert = alert_html(incomplete_notice(metadata, analysis_status))
    if analysis_status is not None:
        status_html += "<h2>Analysis Status</h2>\n" + kv_table_html([
            (html.escape(label), html.escape(value))
            for label, value in status_rows(analysis_status)
        ])
        status_html += excluded_inputs_html(analysis_status)

    summary_rows: list[str] = []
    for idx, r in enumerate(results, 1):
        hash_label = hash_only_label(r)
        if r.error is not None:
            # Never compared: no percentage and no +0/-0 that read as a result.
            status = (
                '<td><em>Not compared ('
                + html.escape(r.error)
                + ')</em></td>'
            )
            added = deleted = '<td class="num">n/a</td>'
        elif hash_label is not None:
            status = f'<td>{html.escape(hash_label)}</td>'
            added = deleted = '<td class="num">n/a</td>'
        else:
            status = f'<td class="num">{_ratio_badge(r.ratio)}</td>'
            added = f'<td class="num">{signed_count(r.additions, "+")}</td>'
            deleted = f'<td class="num">{signed_count(r.deletions, "-")}</td>'
        summary_rows.append(
            f"<tr>"
            f'<td class="num">{count_label(idx)}</td>'
            f"<td>{_break_path(html.escape(r.match.rel_path_a))}</td>"
            f"<td>{_break_path(html.escape(r.match.rel_path_b))}</td>"
            f'<td class="num">{name_similarity_label(r.match.similarity)}</td>'
            f"{status}"
            f"{added}"
            f"{deleted}"
            f"</tr>\n"
        )

    # Unmatched lists
    # Resolve mode: new uncompared_mode takes precedence over legacy bool
    _show_uncompared = (uncompared_mode or ("inline" if include_uncompared else "none")) == "inline"
    unmatched_html = ""
    if _show_uncompared and (unmatched_a or unmatched_b):
        unmatched_html += "<h2>Unmatched Files</h2>\n"
        # One plain line per path: a list item would put a bullet glyph into
        # the PDF text layer, and a copied path would carry it.
        for side, label, files in (("A", dir_a, unmatched_a), ("B", dir_b, unmatched_b)):
            if not files:
                continue
            unmatched_html += f"<h3>Only in {side} ({html.escape(label)})</h3>\n"
            unmatched_html += "<div class='unmatched'>\n"
            for f in files:
                unmatched_html += f"  <p>{_break_path(html.escape(f))}</p>\n"
            unmatched_html += "</div>\n"

    deep_html = ""
    if deep_results:
        deep_html += f"<h2>{DEEP_COMPARE_HEADING}</h2>\n"
        deep_header = (
            '<tr><th style="width: 30%;">File A</th><th style="width: 30%;">File B</th>'
            '<th class="num" style="width: 10%;">Shared hashes</th>'
            '<th class="num" style="width: 12%;">Jaccard</th>'
            '<th class="num" style="width: 9%;">A in B</th>'
            '<th class="num" style="width: 9%;">B in A</th></tr>\n'
        )
        deep_rows: list[str] = []
        any_inconclusive = False
        for dr in deep_results:
            for b_file, shared, jaccard, inconclusive in dr.matched_files_b:
                jbadge = f'<span class="pct">{overlap_label(jaccard)}</span>'
                if inconclusive:
                    any_inconclusive = True
                    jbadge += '<br><span class="flag">inconclusive</span>'
                a_in_b, b_in_a = dr.containment(b_file, shared)
                deep_rows.append(
                    f"<tr>"
                    f"<td>{_break_path(html.escape(dr.file_a))}</td>"
                    f"<td>{_break_path(html.escape(b_file))}</td>"
                    f'<td class="num">{count_label(shared)}</td>'
                    f'<td class="num">{jbadge}</td>'
                    f'<td class="num">{overlap_label(a_in_b)}</td>'
                    f'<td class="num">{overlap_label(b_in_a)}</td>'
                    f"</tr>\n"
                )
        deep_html += ruled_table("deep", 6, deep_rows, deep_header)
        deep_html += f'<p class="note">{html.escape(CONTAINMENT_NOTE)}</p>\n'
        if any_inconclusive:
            deep_html += f'<p class="note">{html.escape(INCONCLUSIVE_NOTICE)}</p>\n'

    summary_header = (
        '<tr><th class="num" style="width: 4%;">#</th>'
        '<th style="width: 30%;">File A</th><th style="width: 30%;">File B</th>'
        '<th class="num" style="width: 10%;">Name similarity</th>'
        f'<th class="num" style="width: 10%;">{unit.capitalize()} match</th>'
        '<th class="num" style="width: 8%;">Added</th>'
        '<th class="num" style="width: 8%;">Deleted</th></tr>\n'
    )
    # Characters the built-in PDF fonts cannot draw on the diff pages; the
    # notice is completed (or removed) by _html_wrap, which knows the fonts.
    glyph_counts = _uncovered_counts(
        [
            pair_heading_html(i, r.match.rel_path_a, r.match.rel_path_b) + (r.html_diff or "")
            for i, r in enumerate(results, 1)
        ],
        _font_plan(None, None),
    )
    limitations = limitations_html(metadata).replace(
        "</ol>", _encode_glyph_notice(glyph_counts) + "</ol>"
    )

    body = f"""\
<p class="doc-tool">Diffinite</p>
<h1>{REPORT_TITLE}</h1>
{alert}
{particulars_html}
{meta_html}
{status_html}
{limitations}

<h2>Summary</h2>
{ruled_table("summary", 7, summary_rows, summary_header)}

{unmatched_html}
{deep_html}
"""
    if hash_table_html:
        body += hash_table_html
    return body


# ---------------------------------------------------------------------------
# Diff page
# ---------------------------------------------------------------------------
_RE_CODE_CHANGED = _re.compile(r'<td class="code (del|add|chg|moved-del|moved-add)">')
_RE_MOVED_LN = _re.compile(r'(<td class="ln (?:lnb )?moved-(?:del|add)"[^>]*>)(\d+)(</td>)')
_RE_PRE_BLOCK = _re.compile(r'<pre>(.*?)</pre>', _re.S)
_RE_THEAD = _re.compile(r'<thead><tr>(.*?)</tr></thead>', _re.S)
_RE_THEAD_ROW = _re.compile(r'<thead>.*?</thead>', _re.S)
# CSS Text Level 3 initial value of tab-size, i.e. what the HTML report shows.
_TAB_SIZE = 8


def _pdf_preserve_whitespace(pre_inner: str) -> str:
    """Keep indentation and runs of spaces visible in xhtml2pdf.

    xhtml2pdf collapses whitespace inside ``white-space: pre-wrap`` cells, so
    leading indentation disappeared from the PDF while the HTML showed it.
    Tabs are expanded to the HTML report's tab stops; every space that is not
    a single space between two non-space characters becomes a no-break space,
    which xhtml2pdf keeps while still wrapping long lines.
    """
    parts = _RE_HTML_TAG.split(pre_inner)
    texts: list[Optional[str]] = []
    col = 0
    for part in parts:
        if part.startswith("<"):
            texts.append(None)
            continue
        expanded = []
        for ch in html.unescape(part):
            if ch == "\t":
                n = _TAB_SIZE - col % _TAB_SIZE
                expanded.append(" " * n)
                col += n
            else:
                expanded.append(ch)
                col += 1
        texts.append("".join(expanded))
    flat = "".join(t for t in texts if t is not None)
    if " " not in flat:
        return pre_inner
    keep = [
        ch == " " and 0 < i < len(flat) - 1 and flat[i - 1] != " " and flat[i + 1] != " "
        for i, ch in enumerate(flat)
    ]
    out: list[str] = []
    pos = 0
    for part, text in zip(parts, texts):
        if text is None:
            out.append(part)
            continue
        pieces = []
        for ch in text:
            if ch == " " and not keep[pos]:
                pieces.append("&nbsp;")
            else:
                pieces.append(html.escape(ch, quote=False))
            pos += 1
        out.append("".join(pieces))
    return "".join(out)


def _dir_label(path: Optional[str]) -> str:
    """The last component of a directory path, for pane headers ("" if none)."""
    if not path:
        return ""
    return Path(str(path).rstrip("/\\")).name or str(path)


def _prepare_diff_table(
    html_diff: str,
    *,
    for_pdf: bool = False,
    dir_a: Optional[str] = None,
    dir_b: Optional[str] = None,
) -> str:
    """Add print-safe markers to a ``differ.generate_html_diff`` table.

    Presentation only (the rows and their text are unchanged): the header row
    names the side and, when given, the directory ("A: dirA/path"); it
    repeats on every PDF page, the B line-number column gets a divider, each
    changed code cell gets a rule beside it, and moved-block line numbers get
    an "M" so the distinction survives black-and-white printing.
    """
    if not html_diff or 'class="difftbl"' not in html_diff:
        return html_diff
    out = html_diff
    for side, dir_label in (("A", dir_a), ("B", dir_b)):
        name = _dir_label(dir_label)
        if name:
            out = out.replace(
                f'<th class="code">{side}: ', f'<th class="code">{side}: {html.escape(name)}/', 1
            )
    # Header rules as spanning rows (unbroken lines); the three rows repeat
    # at the top of every PDF page.
    rule = '<tr class="rule"><td colspan="4"></td></tr>'
    out = _RE_THEAD.sub(
        lambda m: f"<thead>{rule}<tr>{m.group(1)}</tr>{rule}</thead>", out, count=1
    )
    repeat = "3" if rule in out else "1"
    out = out.replace('<table class="difftbl">', f'<table class="difftbl" repeat="{repeat}">', 1)
    out = out.replace('</th><th class="ln"', '</th><th class="ln lnb"', 1)
    out = out.replace('</pre></td><td class="ln ', '</pre></td><td class="ln lnb ')
    out = _RE_CODE_CHANGED.sub(r'<td class="code \1 bar">', out)
    out = _RE_MOVED_LN.sub(r'\1\2&nbsp;<span class="mv">M</span>\3', out)

    # Column widths: declared in a <colgroup> for browsers (the first row
    # is a spanning rule, which would otherwise make all four columns equally
    # wide) and used for the PDF line capacity below.
    thead = _RE_THEAD_ROW.search(out)
    widths = [
        (_RE_CELL_WIDTH.findall(th) or [""])[0]
        for th in _re.findall(r"<th(?:\s[^>]*)?>", thead.group(0))
    ] if thead else []
    code_pt = _pdf_code_cell_width_pt(widths)

    def pre(m: "_re.Match[str]") -> str:
        inner = m.group(1)
        hang = _hanging_indent_style(inner, for_pdf=for_pdf)
        if for_pdf:
            inner = _pdf_preserve_whitespace(inner)
            inner = _pdf_break_long_runs(inner, _pdf_run_capacity(code_pt, inner))
        return f"<pre{hang}>{inner}</pre>"

    out = _RE_PRE_BLOCK.sub(pre, out)
    if widths:
        out = _re.sub(
            r'(<table class="difftbl"[^>]*>)',
            lambda m: m.group(1) + colgroup_html(widths).rstrip(),
            out, count=1,
        )
    return out


# A4 landscape (ISO 216, 297 mm = 841.89 pt) less the 1.2 cm side margins
# set in _html_wrap: the width of the PDF diff table.
_PDF_FRAME_WIDTH_PT = 841.89 - 2 * (1.2 / 2.54 * 72)
# .difftbl td padding: 3 pt left; td.code adds 6 pt right.
_PDF_CODE_PADDING_PT = 3 + 6
# A run is broken for the widest code face that may be used: Courier, whose
# advance is 0.6 em (font metrics), 0.6 x 7 pt = 4.2 pt.
_PDF_CODE_MAX_ADVANCE_PT = 0.6 * 7


def _pdf_code_cell_width_pt(widths: Sequence[str]) -> float:
    """Text width of one code cell in the PDF, from the line-number widths."""
    ln_pt = 0.0
    for w in widths:
        if w.endswith("px"):
            ln_pt += float(w[:-2]) * 0.75  # CSS: 1 px = 0.75 pt
        elif w.endswith("pt"):
            ln_pt += float(w[:-2])
    return (_PDF_FRAME_WIDTH_PT - ln_pt) / 2 - _PDF_CODE_PADDING_PT


def _pdf_run_capacity(code_pt: float, pre_inner: str) -> int:
    """Characters of a continuation line, after the hanging indent."""
    indent = min(_leading_columns(pre_inner), _HANG_MAX_INDENT) + _HANG_EXTRA_CHARS
    usable = code_pt - indent * _PDF_CODE_ADVANCE_PT
    return max(1, int(usable // _PDF_CODE_MAX_ADVANCE_PT))


def _char_cells(ch: str) -> int:
    """Width of *ch* in code-character cells, as drawn in the PDF."""
    if ord(ch) > 0xFFFF:
        return len(code_point_marker(ch))  # no PDF font: drawn as [U+XXXXX]
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _pdf_break_long_runs(pre_inner: str, capacity: int) -> str:
    """Break runs with no space in them at *capacity* cells with ``<br/>``.

    xhtml2pdf wraps code only at a plain space. A longer run (a long string
    literal, a URL, an HTML fragment in a comment) was set on one line past
    the cell and the page edge, and the part beyond the page was lost. The
    break changes no character; the run continues on the next line at the
    hanging indent, as a wrapped line does.
    """
    out: list[str] = []
    run = 0
    for part in _RE_HTML_TAG.split(pre_inner):
        if not part or part.startswith("<"):
            out.append(part)
            continue
        pieces: list[str] = []
        for tok in _RE_TEXT_TOKEN.findall(part):
            if tok == " ":
                run = 0
                pieces.append(tok)
                continue
            ch = html.unescape(tok) if len(tok) > 1 else tok
            cells = sum(_char_cells(c) for c in ch) if ch else 1
            if run and run + cells > capacity:
                pieces.append("<br/>")
                run = 0
            run += cells
            pieces.append(tok)
        out.append("".join(pieces))
    return "".join(out)


# A wrapped code line continues two characters in from its own indentation,
# so a continuation never lines up with the start of a line. Indentation
# beyond 32 columns (four 8-column tab stops) is not followed further, so a
# deeply indented line keeps most of the pane for its wrapped text.
_HANG_EXTRA_CHARS = 2
_HANG_MAX_INDENT = 32
# Advance of one character of the 7 pt code face in the PDF: Consolas and
# Courier both advance 0.55 em (font metrics), 0.55 x 7 pt = 3.85 pt.
_PDF_CODE_ADVANCE_PT = 0.55 * 7


def _leading_columns(pre_inner: str) -> int:
    """Columns of leading whitespace in a code cell (tabs to 8-column stops)."""
    text = html.unescape(_RE_HTML_TAG.sub("", pre_inner))
    col = 0
    for ch in text:
        if ch == "\t":
            col += _TAB_SIZE - col % _TAB_SIZE
        elif ch in (" ", " "):
            col += 1
        else:
            break
    return col


def _hanging_indent_style(pre_inner: str, *, for_pdf: bool) -> str:
    """`` style="..."`` for an indented code line's hanging indent ("" if none).

    Unindented lines use the stylesheet's two-character hanging indent.
    """
    indent = min(_leading_columns(pre_inner), _HANG_MAX_INDENT)
    if not indent:
        return ""
    n = indent + _HANG_EXTRA_CHARS
    if for_pdf:
        width = f"{n * _PDF_CODE_ADVANCE_PT:.2f}pt"
    else:
        width = f"{n}ch"
    return f' style="padding-left: {width}; text-indent: -{width};"'


def diff_key_html(html_diff: str) -> str:
    """A one-line key for the marks that occur in this diff table (or "")."""
    items: list[tuple[str, str, str]] = []
    if 'class="code del' in html_diff:
        items.append(("del bar", "&nbsp;", "Line only in A"))
    if 'class="code add' in html_diff:
        items.append(("add bar", "&nbsp;", "Line only in B"))
    if 'class="code chg' in html_diff:
        items.append(("chg bar", "&nbsp;", "Line changed (word level)"))
    if 'class="word-del"' in html_diff:
        items.append(("", '<span class="word-del">abc</span>', "Text only in A"))
    if 'class="word-add"' in html_diff:
        items.append(("", '<span class="word-add">abc</span>', "Text only in B"))
    if ' ws"' in html_diff:
        items.append(("", '<span class="word-del ws">&nbsp;&nbsp;&nbsp;</span>', "Whitespace changed"))
    if "moved-" in html_diff:
        items.append(("moved-add bar", '<span class="mv">M</span>', "Line in a moved block"))
    if 'class="code empty' in html_diff:
        items.append(("empty", "&nbsp;", "No counterpart line"))
    if not items:
        return ""
    # xhtml2pdf stretches a table to the full frame unless every cell has a
    # width, so widths are set in points: about 3.8 pt per character of the
    # 7.5 pt serif label (measured on the rendered key), plus a little air.
    cells = []
    total = 26
    for cls, sample, label in items:
        bar = " border-left: 2pt solid #222;" if "bar" in cls.split() else ""
        if cls == "empty":
            bar = " border-top: 0.5pt solid #9a9a9a; border-bottom: 0.5pt solid #9a9a9a;"
        label_w = round(len(label) * 3.8) + 6
        total += 18 + label_w + 12
        cells.append(
            f'<td class="sw {cls}" style="width: 18pt;{bar}">{sample}</td>'
            f'<td style="width: {label_w}pt; padding-left: 3pt;">{label}</td>'
            f'<td style="width: 12pt;"></td>'
        )
    return (
        f'<table class="key" style="width: {total}pt;"><tr>'
        f'<td style="width: 26pt;">Key:</td>{"".join(cells)}</tr></table>\n'
    )


def pair_heading_html(index: Optional[int], path_a: str, path_b: str) -> str:
    """``<h2>`` for one compared pair: "1. a.py vs. b.py"."""
    num = f"{index}. " if index is not None else ""
    return f"<h2>{num}{html.escape(path_a)} vs. {html.escape(path_b)}</h2>\n"


def pair_result_html(
    r: DiffResult,
    unit: str,
    *,
    for_pdf: bool = False,
    dir_a: Optional[str] = None,
    dir_b: Optional[str] = None,
) -> str:
    """The body of one pair's section, after its heading (PDF and HTML)."""
    if r.error:
        return f"<p>Not compared ({html.escape(r.error)})</p>\n"
    hash_label = hash_only_label(r)
    if hash_label is not None:
        return f"<p>{html.escape(hash_label)}</p>\n"
    diff_html = r.html_diff
    return (
        f'<p class="meta">{unit.capitalize()} match: '
        f"{_ratio_badge(r.ratio)} &nbsp;&nbsp;&nbsp; "
        f"Added: {signed_count(r.additions, '+')} {unit if r.additions == 1 else unit + 's'}"
        " &nbsp;&nbsp;&nbsp; "
        f"Deleted: {signed_count(r.deletions, '-')} {unit if r.deletions == 1 else unit + 's'}"
        "</p>\n"
        f"{diff_key_html(diff_html)}"
        f"{_prepare_diff_table(diff_html, for_pdf=for_pdf, dir_a=dir_a, dir_b=dir_b)}\n"
    )


def build_diff_page_html(
    result: DiffResult,
    index: int,
    unit: str,
    *,
    show_page_number: bool = False,
    show_file_number: bool = False,
    total_files: int = 0,
    show_filename: bool = False,
    pdf_font: Optional[str] = None,
    pdf_lang: Optional[str] = None,
    dir_a: Optional[str] = None,
    dir_b: Optional[str] = None,
) -> str:
    """Build a single-file diff page HTML.

    *dir_a* / *dir_b* (optional) add the directory name to the pane headers,
    e.g. "A: AOSP_Google/ArrayList.java".
    """
    r = result
    body = (
        pair_heading_html(index, r.match.rel_path_a, r.match.rel_path_b)
        + pair_result_html(r, unit, for_pdf=True, dir_a=dir_a, dir_b=dir_b)
    )
    annotation_html, has_footer, has_header = _build_annotation_html(
        show_page_number=show_page_number,
        show_file_number=show_file_number,
        file_index=index,
        total_files=total_files,
        show_filename=show_filename,
        filename=r.match.rel_path_a,
        running_title=REPORT_TITLE,
    )
    return _html_wrap(
        f"{REPORT_TITLE}: {r.match.rel_path_a}",
        body,
        annotation_html=annotation_html,
        has_footer=has_footer,
        has_header=has_header,
        pdf_font=pdf_font,
        pdf_lang=pdf_lang,
    )


# ---------------------------------------------------------------------------
# HTML → PDF
# ---------------------------------------------------------------------------
def _install_flush_vertical_borders() -> None:
    """Draw vertical cell borders with butt caps in xhtml2pdf tables.

    xhtml2pdf gives every border a projecting ("squared") cap, which extends
    a line by half its width past each end. On a vertical border that puts a
    stub of the 2 pt change bar into the next, unchanged row. A butt cap ends
    the line at the cell edge; bars on adjacent rows still meet end to end.
    """
    from xhtml2pdf import tables as _x2p_tables

    original = _x2p_tables.TableData.add_style
    if getattr(original, "_diffinite_butt", False):
        return

    def add_style(self, data):  # type: ignore[no-untyped-def]
        if (
            isinstance(data, tuple)
            and len(data) >= 6
            and data[0] in ("LINEBEFORE", "LINEAFTER")
            and data[5] == "squared"
        ):
            data = data[:5] + ("butt",) + data[6:]
        return original(self, data)

    add_style._diffinite_butt = True  # type: ignore[attr-defined]
    _x2p_tables.TableData.add_style = add_style


_install_flush_vertical_borders()


def _install_hanging_indent_background_fix() -> None:
    """Leave the background of a hanging-indent paragraph to its table cell.

    xhtml2pdf paints a paragraph's inherited background as a block as wide
    as its longest line. With a negative first-line indent (the hanging
    indent of wrapped code) that block is wider than the cell by about the
    indent, so the row tint ran past the table's right edge. The code cells
    are the only such paragraphs, and their cell already paints the same
    background, so the block is not drawn for them.
    """
    from xhtml2pdf.xhtml2pdf_reportlab import PmlParagraph

    original = PmlParagraph.draw
    if getattr(original, "_diffinite_hang", False):
        return

    def draw(self):  # type: ignore[no-untyped-def]
        style = self.style
        if getattr(style, "firstLineIndent", 0) < 0 and style.backColor is not None:
            bg = style.backColor
            style.backColor = None
            try:
                return original(self)
            finally:
                style.backColor = bg
        return original(self)

    draw._diffinite_hang = True  # type: ignore[attr-defined]
    PmlParagraph.draw = draw


_install_hanging_indent_background_fix()


def html_to_pdf(html_content: str, output_path: str) -> bool:
    """Convert an HTML string to a PDF file via xhtml2pdf.

    Returns False (never raises) on failure so the caller's per-page skip path
    runs. xhtml2pdf parses/lays out HTML recursively, so a pathological page can
    raise RecursionError/MemoryError straight out of CreatePDF; without this
    guard one bad page would abort the entire report (cover + all rendered
    diffs + the N:M analysis).
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(str(out), "w+b") as fh:
            status = pisa.CreatePDF(html_content, dest=fh)
    except Exception as exc:  # noqa: BLE001 — incl. RecursionError/MemoryError
        logger.error("PDF conversion failed for %s: %s", output_path, exc)
        return False
    if status.err:
        logger.error("PDF conversion error for %s", output_path)
        return False
    return True


# ---------------------------------------------------------------------------
# Merge with bookmarks
# ---------------------------------------------------------------------------
def merge_with_bookmarks(
    cover_pdf: str,
    diff_pdfs: list[tuple[str, DiffResult]],
    output_path: str,
    *,
    deep_pdf: Optional[str] = None,
) -> list[dict]:
    """Merge PDFs and insert hierarchical bookmarks (TOC).

    Args:
        cover_pdf:  Path to the cover page PDF.
        diff_pdfs:  List of ``(pdf_path, DiffResult)`` tuples.
        output_path: Final merged PDF destination.
        deep_pdf:   Optional path to the deep-compare summary PDF.

    Returns:
        List of dictionaries containing pagination boundaries for each DiffResult.
    """
    writer = PdfWriter()
    page_offset = 0
    layout_data = []

    # Cover page
    if Path(cover_pdf).exists() and Path(cover_pdf).stat().st_size > 0:
        reader = PdfReader(cover_pdf)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item("Cover and Summary", page_offset)
        page_offset += len(reader.pages)

    # Diff pages with bookmarks
    for pair_no, (pdf_path, result) in enumerate(diff_pdfs, 1):
        if not Path(pdf_path).exists() or Path(pdf_path).stat().st_size == 0:
            logger.warning("Skipping empty or missing PDF: %s", pdf_path)
            continue

        reader = PdfReader(pdf_path)
        for page in reader.pages:
            writer.add_page(page)

        label = f"{pair_no}. {result.match.rel_path_a} vs. {result.match.rel_path_b}"
        writer.add_outline_item(label, page_offset)
        
        page_count = len(reader.pages)
        layout_data.append({
            'file_a': result.match.rel_path_a,
            'file_b': result.match.rel_path_b,
            'sim': result.match.similarity,   # filename (name) similarity, 0–100
            'ratio': result.ratio,            # content match (difflib), 0.0–1.0
            'binary': result.binary,
            'hash_match': result.hash_match,
            'error': result.error,            # set => the pair was never compared
            'start_page': page_offset + 1,
            'end_page': page_offset + page_count
        })
        page_offset += page_count

    # Deep compare page
    if deep_pdf and Path(deep_pdf).exists() and Path(deep_pdf).stat().st_size > 0:
        reader = PdfReader(deep_pdf)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item(DEEP_COMPARE_HEADING, page_offset)
        page_offset += len(reader.pages)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "wb") as fh:
        writer.write(fh)
    writer.close()
    logger.info("  Merged PDF with bookmarks: %s (%s bytes)",
                out.resolve(), count_label(out.stat().st_size))
    return layout_data


# ---------------------------------------------------------------------------
# Bates numbering
# ---------------------------------------------------------------------------
def _drop_unreferenced_objects(writer: PdfWriter) -> None:
    """Drop objects no page refers to any more (the pre-compression content streams)."""
    try:
        writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    except TypeError:  # older pypdf within the supported range uses the earlier names
        writer.compress_identical_objects(remove_identicals=False, remove_orphans=True)


# Bates labels are drawn either with base-14 Times-Roman, the footer's face
# (WinAnsi = cp1252 encoding, PDF 32000-1 Annex D), or, for Hangul, with
# reportlab's built-in Adobe-Korea1 CID font HYGothic-Medium, whose
# UniKS-UCS2-H CMap covers all 11,172 Hangul syllables and the KS X 1001
# compatibility jamo.
_BATES_LATIN_FONT = "Times-Roman"
# The footer's type size (.runfoot in _CSS_BODY), so the stamp reads as part
# of the footer line.
_BATES_FONT_SIZE = 7.5
# Measured on rendered reports: xhtml2pdf sets the footer frame's line (frame
# bottom 0.3 cm, height 0.6 cm, see _html_wrap) on a baseline 20.4 pt above
# the page edge; the stamp uses the same baseline (checked by a test).
_BATES_BASELINE = 20.4
_BATES_HANGUL_FONT = "HYGothic-Medium"


def _is_bates_hangul(ch: str) -> bool:
    # U+AC00-D7A3 Hangul Syllables, U+3131-318E Hangul Compatibility Jamo
    # (Unicode 15.1 Blocks.txt; the assigned code points of both blocks).
    return "\uAC00" <= ch <= "\uD7A3" or "\u3131" <= ch <= "\u318E"


def bates_font_for(text: str) -> str:
    """Return the font that can draw *text* as a Bates label, or raise ValueError.

    Characters outside cp1252 and Hangul cannot be drawn by either font, and
    the stamped label would then differ from the Bates Range in the exhibit
    index, so they are refused instead of being printed as black squares.
    A label containing Hangul is drawn entirely in HYGothic-Medium, which is
    only relied on for ASCII besides Hangul, so Hangul mixed with non-ASCII
    Latin (``é``, ``€``) is refused as well. Pass the whole label text
    (prefix + suffix) so a Hangul prefix and a Latin-1 suffix are caught.
    """
    needs_hangul = False
    non_ascii_latin: Optional[str] = None
    for ch in text:
        if unicodedata.category(ch) == "Cc":
            raise ValueError(
                f"Bates prefix/suffix contains a control character (U+{ord(ch):04X}); "
                "it would not be printed and the stamp would differ from the index."
            )
        try:
            ch.encode("cp1252")
            if not ch.isascii() and non_ascii_latin is None:
                non_ascii_latin = ch
            continue
        except UnicodeEncodeError:
            pass
        if not _is_bates_hangul(ch):
            raise ValueError(
                f"Bates prefix/suffix character {ch!r} (U+{ord(ch):04X}) cannot be "
                "drawn by the Bates stamp fonts; use Latin (Windows-1252) "
                "characters or Hangul."
            )
        needs_hangul = True
    if needs_hangul and non_ascii_latin is not None:
        raise ValueError(
            f"Bates prefix/suffix character {non_ascii_latin!r} "
            f"(U+{ord(non_ascii_latin):04X}) cannot be drawn together with Hangul; "
            "a label with Hangul may use only ASCII Latin characters."
        )
    return _BATES_HANGUL_FONT if needs_hangul else _BATES_LATIN_FONT


def _bates_canvas_font(text: str) -> str:
    font = bates_font_for(text)
    if font == _BATES_HANGUL_FONT:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(font))
    return font


def add_bates_numbers(
    input_path: str,
    output_path: str,
    *,
    start: int = 1,
    prefix: str = "",
    suffix: str = "",
) -> None:
    """Stamp Bates numbers on each page of a merged PDF.

    Preserves existing bookmarks/outline by cloning the full document
    before overlaying Bates numbers.

    Args:
        start: First Bates number (default 1).
        prefix: Bates prefix, e.g. ``"PLAINTIFF-"``.
        suffix: Bates suffix, e.g. ``"-CONFIDENTIAL"``.
    """
    bates_font = _bates_canvas_font(prefix + suffix)  # refuse before writing
    reader = PdfReader(input_path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    total_pages = len(writer.pages)
    digits = max(4, len(str(start + total_pages - 1)))

    for i, page in enumerate(writer.pages):
        box = page.mediabox
        pw = float(box.width)
        ph = float(box.height)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        bates = f"{prefix}{str(start + i).zfill(digits)}{suffix}"
        c.setFont(bates_font, _BATES_FONT_SIZE)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(pw / 2, _BATES_BASELINE, bates)
        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        # merge_page leaves the combined content stream uncompressed (~10x larger
        # files on text-heavy reports); recompress it. Rendering is unchanged.
        page.compress_content_streams()
    # The pre-compression streams stay in the writer as orphans; drop them.
    _drop_unreferenced_objects(writer)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "wb") as fh:
        writer.write(fh)
    writer.close()
    logger.info("  Bates numbers added: %s", out.resolve())


def stamp_bates_inplace(
    pdf_path: str,
    start_number: int,
    digits: int,
    *,
    prefix: str = "",
    suffix: str = "",
) -> None:
    """Stamp Bates numbers on a single PDF file in-place."""
    bates_font = _bates_canvas_font(prefix + suffix)  # refuse before writing
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        box = page.mediabox
        pw = float(box.width)
        ph = float(box.height)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        bates = f"{prefix}{str(start_number + i).zfill(digits)}{suffix}"
        c.setFont(bates_font, _BATES_FONT_SIZE)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(pw / 2, _BATES_BASELINE, bates)
        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        # Merge on the writer's copy (merging a reader page is deprecated in pypdf),
        # then recompress the merged content stream; see add_bates_numbers.
        writer_page = writer.add_page(page)
        writer_page.merge_page(overlay_page)
        writer_page.compress_content_streams()
    _drop_unreferenced_objects(writer)

    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    writer.close()
