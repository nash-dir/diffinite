"""LangSpec dataclass — single source of truth for language-specific settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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

