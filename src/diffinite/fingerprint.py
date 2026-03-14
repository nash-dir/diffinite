"""Winnowing fingerprint extraction.

Implements the Stanford MOSS-style document fingerprinting pipeline:

1. **Tokenise** source code into a token sequence.
2. **K-gram** the tokens with a sliding window of size *K*.
3. **Rolling hash** each K-gram using a Rabin-style polynomial hash.
4. **Winnow** the hash stream with window size *W*, selecting the
   minimum hash in each window to produce a compact fingerprint set.

The resulting fingerprints guarantee that any shared substring of length
≥ (W + K − 1) tokens between two documents will produce at least one
common fingerprint (the *density guarantee*).
"""

from __future__ import annotations

import re
from typing import Sequence

from diffinite.models import FingerprintEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_K: int = 5            # K-gram size (tokens) — tuned via grid search on
                              # SQLite 250K-line and AOSP Java corpora.
                              # K=5: highest Jaccard (0.9904), best speed,
                              # gap < 12pp from line-level ratio.
DEFAULT_W: int = 4            # Winnowing window size — tuned via sweep.
                              # Guarantees detection of shared substrings ≥ 8
                              # tokens (W + K - 1 = 4 + 5 - 1 = 8).
HASH_BASE: int = 257
HASH_MOD: int = (1 << 61) - 1  # Mersenne prime for low collision

# Simple tokeniser regex — splits on whitespace and common punctuation,
# keeping the tokens themselves (no empty strings).
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|[0-9]+(?:\.[0-9]+)?|[^\s]")

# Common keywords — curated subset used for token normalisation.
# Phase 3 Strategy A: maintain the exact legacy keyword set for backward
# compatibility.  Phase 5 will switch to per-extension keywords via
# ``get_spec(ext).keywords`` for improved precision.
from diffinite.languages import all_keywords as _all_keywords  # noqa: E402

# Legacy keyword set — identical to the pre-v0.4.0 hardcoded frozenset.
# all_keywords() is a superset (per-language keywords); using it directly
# would change fingerprint hashes and break existing forensic reports.
_COMMON_KEYWORDS = frozenset({
    # Control flow
    "if", "else", "for", "while", "do", "switch", "case", "break",
    "continue", "return", "try", "catch", "finally", "throw", "throws",
    # Declaration
    "class", "interface", "enum", "struct", "typedef", "extends",
    "implements", "import", "package", "from", "def", "function",
    "var", "let", "const", "static", "final", "abstract",
    # Types
    "void", "int", "long", "float", "double", "char", "boolean",
    "bool", "string", "byte", "short",
    # Access
    "public", "private", "protected", "default",
    # Logical
    "true", "false", "null", "None", "this", "self", "super",
    "new", "delete", "instanceof", "typeof", "sizeof",
    # Python specific
    "lambda", "yield", "async", "await", "with", "as", "in",
    "not", "and", "or", "is", "pass", "raise", "nonlocal", "global",
})


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------
def tokenize(source: str, *, normalize: bool = False) -> list[str]:
    """Tokenise *source* into a flat list of code tokens.

    Identifiers, numeric literals, and individual punctuation characters
    are each treated as separate tokens.  Whitespace is discarded.

    When *normalize* is ``True``, identifiers are replaced with ``"ID"``,
    numeric literals with ``"LIT"``, and string delimiters with ``"STR"``.
    Language keywords and operators are preserved as-is.  This makes the
    resulting fingerprints resilient to identifier renaming (Type-2 clones).

    Args:
        source:    Pre-processed source code (comments already stripped).
        normalize: If *True*, apply token-type normalisation.

    Returns:
        List of token strings.
    """
    raw_tokens = _TOKEN_RE.findall(source)
    if not normalize:
        return raw_tokens

    result: list[str] = []
    for tok in raw_tokens:
        if tok in _COMMON_KEYWORDS:
            result.append(tok)           # keyword — preserve
        elif tok[0].isalpha() or tok[0] == '_':
            result.append("ID")          # identifier → ID
        elif tok[0].isdigit():
            result.append("LIT")         # numeric literal → LIT
        elif tok in ('"', "'", '`'):
            result.append("STR")         # string delimiter → STR
        else:
            result.append(tok)           # operator / punctuation — preserve
    return result


# ---------------------------------------------------------------------------
# Rolling hash
# ---------------------------------------------------------------------------
def rolling_hash(tokens: Sequence[str], k: int = DEFAULT_K) -> list[int]:
    """Compute Rabin rolling hashes over K-grams of *tokens*.

    Args:
        tokens: Token sequence from :func:`tokenize`.
        k:      K-gram size.

    Returns:
        List of hash values, one per K-gram.  Length = ``len(tokens) - k + 1``.
        Empty list if ``len(tokens) < k``.
    """
    n = len(tokens)
    if n < k:
        return []

    hashes: list[int] = []
    h: int = 0
    base_pow = pow(HASH_BASE, k - 1, HASH_MOD)

    # Seed the first window
    for i in range(k):
        th = hash(tokens[i]) & 0x7FFFFFFFFFFFFFFF
        h = (h * HASH_BASE + th) % HASH_MOD
    hashes.append(h)

    # Roll
    for i in range(k, n):
        old_th = hash(tokens[i - k]) & 0x7FFFFFFFFFFFFFFF
        new_th = hash(tokens[i]) & 0x7FFFFFFFFFFFFFFF
        h = ((h - old_th * base_pow) * HASH_BASE + new_th) % HASH_MOD
        hashes.append(h)

    return hashes


# ---------------------------------------------------------------------------
# Winnowing
# ---------------------------------------------------------------------------
def winnow(
    hash_values: list[int],
    w: int = DEFAULT_W,
) -> list[FingerprintEntry]:
    """Apply the Winnowing algorithm to select representative fingerprints.

    For each sliding window of size *w* over *hash_values*, the minimum
    hash (rightmost in case of ties) is selected.  Consecutive duplicate
    selections are suppressed.

    Args:
        hash_values: Hash sequence from :func:`rolling_hash`.
        w:           Window size.

    Returns:
        Deduplicated list of :class:`FingerprintEntry` objects.
    """
    n = len(hash_values)
    if n == 0:
        return []
    if n <= w:
        # Only one window — pick the global minimum
        min_val = min(hash_values)
        min_pos = len(hash_values) - 1 - hash_values[::-1].index(min_val)
        return [FingerprintEntry(hash_value=min_val, position=min_pos)]

    fingerprints: list[FingerprintEntry] = []
    prev_pos = -1

    for start in range(n - w + 1):
        window = hash_values[start: start + w]
        # Select the rightmost minimum
        min_val = min(window)
        # Find rightmost occurrence of min_val in window
        local_pos = w - 1 - window[::-1].index(min_val)
        global_pos = start + local_pos

        if global_pos != prev_pos:
            fingerprints.append(
                FingerprintEntry(hash_value=min_val, position=global_pos)
            )
            prev_pos = global_pos

    return fingerprints


_IMPORT_RE = re.compile(r"^(import|package)\s+.*;\s*$", re.MULTILINE)


def extract_fingerprints(
    source: str,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    *,
    normalize: bool = False,
    mode: str = "token",
    extension: str = "",
    filter_imports: bool = False,
) -> list[FingerprintEntry]:
    """Full pipeline: tokenise → K-gram hash → winnow → fingerprint set.

    Args:
        source:         Pre-processed source code (comments stripped).
        k:              K-gram size.
        w:              Winnowing window size.
        normalize:      If *True*, apply token-type normalisation before hashing
                        (only used in ``"token"`` mode).
        mode:           Tokenisation strategy:

                        * ``"token"`` — Phase 1 flat token normalisation (default).
                        * ``"ast"``   — Phase 2 tree-sitter AST linearization.
                        * ``"pdg"``   — Phase 4 PDG-normalised AST (future).

                        When set to ``"ast"`` or ``"pdg"`` and tree-sitter is
                        unavailable, falls back to ``"token"`` mode automatically.
        extension:      Lowercase file extension (e.g. ``".py"``), required for
                        AST/PDG modes.
        filter_imports: If *True*, strip ``import`` and ``package`` statements
                        before fingerprinting (reduces FP from shared Java imports).

    Returns:
        List of :class:`FingerprintEntry` fingerprints.
    """
    if filter_imports:
        source = _IMPORT_RE.sub("", source)

    tokens: list[str] | None = None

    if mode in ("ast", "pdg"):
        try:
            from diffinite.ast_normalizer import ast_tokenize, pdg_tokenize

            if mode == "pdg":
                tokens = pdg_tokenize(source, extension)
            if tokens is None:
                tokens = ast_tokenize(source, extension)
        except ImportError:
            pass  # tree-sitter not installed → fallback

    if tokens is None:
        # Fallback to Phase 1 token normalisation
        tokens = tokenize(source, normalize=normalize)

    hashes = rolling_hash(tokens, k)
    return winnow(hashes, w)

