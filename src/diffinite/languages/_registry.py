"""Language specification registry.

Provides ``register()``, ``get_spec()``, ``all_extensions()``,
``all_keywords()`` and ``all_specs()`` for the language package.
"""

from __future__ import annotations

from typing import Optional

from diffinite.languages._spec import LangSpec

_REGISTRY: dict[str, LangSpec] = {}


def register(spec: LangSpec) -> None:
    """Register a LangSpec for each of its extensions.

    Called automatically when a language module is imported at package
    initialisation time.

    Raises:
        ValueError: If an extension is already registered by another spec.
    """
    for ext in spec.extensions:
        if ext in _REGISTRY:
            raise ValueError(
                f"Extension {ext!r} already registered by "
                f"{_REGISTRY[ext].name!r}"
            )
        _REGISTRY[ext] = spec


def get_spec(ext: str) -> Optional[LangSpec]:
    """Look up a LangSpec by file extension (e.g. ``'.py'``)."""
    return _REGISTRY.get(ext)


def all_extensions() -> list[str]:
    """Return all registered extensions, sorted."""
    return sorted(_REGISTRY.keys())


def all_keywords() -> frozenset[str]:
    """Return the union of all language keywords (backward-compatible)."""
    return frozenset().union(*(s.keywords for s in set(_REGISTRY.values())))


def all_specs() -> list[LangSpec]:
    """Return a deduplicated, name-sorted list of all LangSpecs."""
    return sorted(set(_REGISTRY.values()), key=lambda s: s.name)
