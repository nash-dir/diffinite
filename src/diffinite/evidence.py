"""Multi-evidence channel scoring for forensic code comparison.

Implements independent analysis channels beyond Winnowing fingerprints,
inspired by SAFE CodeMatch's 5-algorithm approach.  Each channel captures
a different facet of code similarity, so their *combined* agreement
provides far stronger evidence than any single metric.

Channels
========

1. **Identifier Cosine Similarity** — Compares the identifier-name
   distributions of two files.  High Winnowing + low Identifier score
   signals intentional renaming (Type-2 disguise).

2. **Comment/String Overlap** — Compares author-written natural-language
   artefacts (comments, string literals) that are often inadvertently
   preserved during code copying.

3. **Composite Score** — Weighted average across all available channels,
   summarising overall similarity in a single number.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from diffinite.fingerprint import _COMMON_KEYWORDS

# ---------------------------------------------------------------------------
# Channel 3: Identifier Cosine Similarity
# ---------------------------------------------------------------------------
# Simple tokeniser — same regex as fingerprint.py
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|[0-9]+(?:\.[0-9]+)?|[^\s]")


def _extract_identifiers(source: str) -> list[str]:
    """Extract identifier tokens (excluding language keywords).

    Args:
        source: Source code text (comments already stripped).

    Returns:
        List of identifier strings.
    """
    tokens = _TOKEN_RE.findall(source)
    return [
        t for t in tokens
        if t not in _COMMON_KEYWORDS
        and (t[0].isalpha() or t[0] == '_')
    ]


def identifier_cosine(source_a: str, source_b: str) -> float:
    """Compute cosine similarity between identifier frequency vectors.

    A high score means the two files share the same variable/function
    names in similar proportions — strong evidence of copying.
    A low score when structure-based similarity is high indicates
    deliberate renaming (Type-2 clone disguise).

    Args:
        source_a: Comment-stripped source of file A.
        source_b: Comment-stripped source of file B.

    Returns:
        Cosine similarity ∈ [0.0, 1.0].
    """
    ids_a = Counter(_extract_identifiers(source_a))
    ids_b = Counter(_extract_identifiers(source_b))

    if not ids_a or not ids_b:
        return 0.0

    # Compute dot product and magnitudes
    all_keys = set(ids_a) | set(ids_b)
    dot = sum(ids_a.get(k, 0) * ids_b.get(k, 0) for k in all_keys)
    mag_a = math.sqrt(sum(v * v for v in ids_a.values()))
    mag_b = math.sqrt(sum(v * v for v in ids_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Channel 4: Comment/String Overlap
# ---------------------------------------------------------------------------
# Regex to extract string literals (double-quoted, single-quoted, backtick)
_STRING_LITERAL_RE = re.compile(
    r'"""[\s\S]*?"""|'
    r"'''[\s\S]*?'''|"
    r'"(?:[^"\\]|\\.)*"|'
    r"'(?:[^'\\]|\\.)*'|"
    r"`(?:[^`\\]|\\.)*`"
)


def extract_comments_and_strings(
    text: str, extension: str,
) -> list[str]:
    """Extract comment and string-literal content from source code.

    This is the **inverse** of ``parser.strip_comments()``: instead of
    removing comments, we collect them.  String literals are also
    collected because they carry author-specific content (messages,
    URLs, magic constants) that persists across code copying.

    Args:
        text:      Raw source code (with comments intact).
        extension: Lowercase file extension (e.g. ``".py"``).

    Returns:
        List of extracted comment/string fragments, each stripped of
        surrounding delimiters and whitespace.
    """
    from diffinite.parser import COMMENT_SPECS, strip_comments

    fragments: list[str] = []

    # 1. Extract comments by diffing raw vs. stripped
    stripped = strip_comments(text, extension)
    raw_lines = text.splitlines()
    stripped_lines = stripped.splitlines()

    for raw_line, clean_line in zip(raw_lines, stripped_lines):
        # The "comment part" is what was removed
        comment_part = raw_line[len(clean_line):].strip()
        if comment_part:
            # Remove comment markers
            spec = COMMENT_SPECS.get(extension)
            if spec:
                for marker in spec.line_markers:
                    if comment_part.startswith(marker):
                        comment_part = comment_part[len(marker):].strip()
                        break
            if comment_part:
                fragments.append(comment_part)

    # 2. Extract string literals
    for match in _STRING_LITERAL_RE.finditer(text):
        content = match.group()
        # Strip delimiters
        if content.startswith(('"""', "'''")):
            content = content[3:-3]
        elif content[0] in ('"', "'", '`'):
            content = content[1:-1]
        content = content.strip()
        if content and len(content) > 2:  # Ignore trivially short strings
            fragments.append(content)

    return fragments


def comment_string_overlap(
    text_a: str, text_b: str, extension: str,
) -> float:
    """Compute Jaccard similarity over comment/string fragments.

    Args:
        text_a: Raw source of file A (comments intact).
        text_b: Raw source of file B (comments intact).
        extension: Lowercase file extension.

    Returns:
        Jaccard similarity ∈ [0.0, 1.0].
    """
    frags_a = set(extract_comments_and_strings(text_a, extension))
    frags_b = set(extract_comments_and_strings(text_b, extension))

    if not frags_a and not frags_b:
        return 0.0

    intersection = len(frags_a & frags_b)
    union = len(frags_a | frags_b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Composite multi-channel scoring
# ---------------------------------------------------------------------------
# Default channel weights — channels with higher forensic significance
# get more weight.  Weights are normalised at runtime.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "raw_winnowing":        1.0,
    "normalized_winnowing":  2.0,
    "ast_winnowing":         2.0,
    "identifier_cosine":     1.5,
    "comment_string_overlap": 1.0,
}


def _jaccard_from_sets(set_a: set[int], set_b: set[int]) -> float:
    """Compute Jaccard similarity between two hash sets."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def compute_channel_scores(
    *,
    # Winnowing fingerprint sets (hash values)
    fp_raw_a: Optional[set[int]] = None,
    fp_raw_b: Optional[set[int]] = None,
    fp_norm_a: Optional[set[int]] = None,
    fp_norm_b: Optional[set[int]] = None,
    fp_ast_a: Optional[set[int]] = None,
    fp_ast_b: Optional[set[int]] = None,
    # Source texts for identifier/comment analysis
    source_a: Optional[str] = None,
    source_b: Optional[str] = None,
    cleaned_a: Optional[str] = None,
    cleaned_b: Optional[str] = None,
    extension: str = "",
) -> dict[str, float]:
    """Compute scores across all available evidence channels.

    Only channels whose inputs are provided will be computed.  The
    ``composite`` score is the weighted average of available channels.

    Args:
        fp_raw_a / fp_raw_b:   Raw Winnowing fingerprint hash sets.
        fp_norm_a / fp_norm_b: Normalised Winnowing fingerprint hash sets.
        fp_ast_a / fp_ast_b:   AST Winnowing fingerprint hash sets.
        source_a / source_b:   Raw source texts (for comment extraction).
        cleaned_a / cleaned_b: Comment-stripped source (for identifier extraction).
        extension:             File extension for comment parsing.

    Returns:
        Dict with channel names as keys and scores (0.0–1.0) as values,
        plus a ``"composite"`` weighted average.
    """
    scores: dict[str, float] = {}

    # Channel 1: Raw Winnowing
    if fp_raw_a is not None and fp_raw_b is not None:
        scores["raw_winnowing"] = _jaccard_from_sets(fp_raw_a, fp_raw_b)

    # Channel 2: Normalised Winnowing
    if fp_norm_a is not None and fp_norm_b is not None:
        scores["normalized_winnowing"] = _jaccard_from_sets(fp_norm_a, fp_norm_b)

    # Channel 5: AST Winnowing
    if fp_ast_a is not None and fp_ast_b is not None:
        scores["ast_winnowing"] = _jaccard_from_sets(fp_ast_a, fp_ast_b)

    # Channel 3: Identifier Cosine
    if cleaned_a is not None and cleaned_b is not None:
        scores["identifier_cosine"] = identifier_cosine(cleaned_a, cleaned_b)

    # Channel 4: Comment/String Overlap
    if source_a is not None and source_b is not None and extension:
        scores["comment_string_overlap"] = comment_string_overlap(
            source_a, source_b, extension,
        )

    # Composite weighted average
    if scores:
        total_weight = 0.0
        weighted_sum = 0.0
        for channel, score in scores.items():
            w = _DEFAULT_WEIGHTS.get(channel, 1.0)
            weighted_sum += score * w
            total_weight += w
        scores["composite"] = weighted_sum / total_weight if total_weight else 0.0

    return scores
