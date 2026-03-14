"""LangSpec dataclass — single source of truth for language-specific settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from diffinite.models import CommentSpec


@dataclass(frozen=True)
class LangSpec:
    """Single source of truth for a language or language-family.

    한 언어에 대한 주석 처리, 키워드, AST 매핑 정보를 모두 담는다.
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

    # ── AST Layer (tree-sitter) ───────────────────────────────────
    tree_sitter_module: Optional[str] = None    # "tree_sitter_java"
    tree_sitter_func: str = "language"          # 모듈 내 팩토리 함수명

    # 언어별 AST 노드 타입 오버라이드 (None → 패키지 전역 기본값 사용)
    identifier_types: Optional[frozenset[str]] = None
    literal_types: Optional[frozenset[str]] = None
    string_types: Optional[frozenset[str]] = None
    structure_types: Optional[frozenset[str]] = None
    statement_types: Optional[frozenset[str]] = None
