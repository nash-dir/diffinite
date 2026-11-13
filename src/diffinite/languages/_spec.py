"""LangSpec dataclass — single source of truth for language-specific settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from diffinite.models import CommentSpec


@dataclass(frozen=True)
class LangSpec:
    """Single source of truth for a language or language-family.

    한 언어에 대한 주석 처리와 키워드 정보를 담는다.
    새 언어를 추가하려면 이 객체 하나를 생성하고 register() 하면 된다.
    """

    # ── Identity ──────────────────────────────────────────────────
    name: str                                   # "Java", "Python" 등 사람용 이름
    extensions: tuple[str, ...]                 # (".java",), (".py", ".pyw") 등

    # ── Parser Layer ──────────────────────────────────────────────
    comment: CommentSpec                        # 주석 마커 (라인, 블록)
    has_ifdef_zero: bool = False                # #if 0 … #endif 전처리 여부

    # ── Fingerprint Layer ─────────────────────────────────────────
    keywords: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class LanguageCommentSpec(CommentSpec):
    """``CommentSpec`` plus string rules that only some languages need.

    ``parser`` reads these with ``getattr`` defaults, so a plain ``CommentSpec``
    behaves as before.  (They live here because ``models.py`` is owned by another
    change set; they can move into ``CommentSpec`` itself later.)
    """

    template_interpolation: bool = True
    """Whether ``${`` inside a template literal opens an interpolation.
    JS/TS template literals do; Go raw strings do not (Go spec, "String literals":
    a raw string is any character sequence between back quotes)."""

    verbatim_string_prefixes: tuple[str, ...] = ()
    """Prefixes that open a multi-line string with no backslash escapes, where a
    doubled quote is a literal quote.  C# ``@"..."`` and ``@$"..."`` (C# spec,
    "Verbatim string literals")."""

    cpp_raw_strings: bool = False
    """Whether ``R"delim(...)delim"`` (optionally prefixed ``u8``/``u``/``U``/``L``)
    is a raw string: no escapes, may span lines, ends only at ``)delim"``.
    C++11 [lex.string]; the delimiter is at most 16 characters."""
