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

# Noise identifiers — tokens that inflate cosine similarity without
# indicating SSO.  Includes:
#  - Java/generic type names (scènes à faire)
#  - Single-character loop/generic variables
_JAVA_TYPE_STOPWORDS = frozenset({
    "String", "Object", "Integer", "Long", "Double", "Float",
    "Boolean", "Character", "Byte", "Short", "Number",
    "Void", "Class", "Comparable", "Iterable", "Iterator",
    "Serializable", "Cloneable", "Exception", "Throwable",
    "Override", "Deprecated", "SuppressWarnings",
})


def _is_noise_identifier(token: str) -> bool:
    """Check if *token* is a noise identifier that should be excluded.

    Filters:
    - Single-character identifiers (loop vars `i`, `j`, `k`; generics `V`, `K`, `T`)
    - Java standard type names (scènes à faire)
    """
    if len(token) == 1:
        return True  # i, j, k, V, K, T, E, etc.
    if token in _JAVA_TYPE_STOPWORDS:
        return True
    return False


def _extract_identifiers(source: str) -> list[str]:
    """Extract identifier tokens (excluding keywords and noise identifiers).

    Filters out language keywords, single-character variables (loop/generics),
    and Java standard type names that are scènes à faire.

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
        and not _is_noise_identifier(t)
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
# TF-IDF weighted identifier similarity (Stage 2: FP reduction)
# ---------------------------------------------------------------------------
def _build_idf(all_identifiers_per_file: list[list[str]]) -> dict[str, float]:
    """Build a smoothed IDF dictionary from a corpus of identifier lists.

    Uses the smoothed formula: ``log((N+1) / (df+1)) + 1``
    where *N* = total number of documents, *df* = number of documents
    containing the term.

    Common identifiers like ``size``, ``get``, ``set`` that appear in
    many files will have low IDF; rare API-specific names like
    ``compareTo``, ``copyValueOf`` will have high IDF.

    Args:
        all_identifiers_per_file: List-of-lists — each inner list
            contains all identifiers from one source file.

    Returns:
        Dict mapping identifier → IDF weight.
    """
    N = len(all_identifiers_per_file)
    # Document frequency: how many files contain each identifier
    df: dict[str, int] = {}
    for ids in all_identifiers_per_file:
        for token in set(ids):  # unique per document
            df[token] = df.get(token, 0) + 1

    idf: dict[str, float] = {}
    for token, freq in df.items():
        idf[token] = math.log((N + 1) / (freq + 1)) + 1
    return idf


def _tfidf_vector(identifiers: list[str], idf: dict[str, float]) -> Counter:
    """Compute TF-IDF weighted vector from identifiers and IDF dict.

    TF is raw count, multiplied by IDF weight for each term.

    Args:
        identifiers: List of identifier tokens from a single file.
        idf: IDF dictionary from ``_build_idf()``.

    Returns:
        Counter with TF-IDF weights as values.
    """
    tf = Counter(identifiers)
    tfidf = Counter()
    for token, count in tf.items():
        weight = idf.get(token, 1.0)
        tfidf[token] = count * weight
    return tfidf


def identifier_cosine_tfidf(
    source_a: str, source_b: str,
    idf: dict[str, float] | None = None,
) -> float:
    """Compute TF-IDF weighted cosine similarity between identifier vectors.

    When ``idf`` is ``None``, falls back to plain ``identifier_cosine()``.
    Otherwise, applies TF-IDF weighting which down-weights common domain
    identifiers (``size``, ``get``, ``set``) and amplifies rare API-specific
    names (``compareTo``, ``copyValueOf``).

    Args:
        source_a: Comment-stripped source of file A.
        source_b: Comment-stripped source of file B.
        idf:      IDF dictionary from ``_build_idf()``, or None for fallback.

    Returns:
        Cosine similarity ∈ [0.0, 1.0].
    """
    if idf is None:
        return identifier_cosine(source_a, source_b)

    ids_a = _extract_identifiers(source_a)
    ids_b = _extract_identifiers(source_b)

    vec_a = _tfidf_vector(ids_a, idf)
    vec_b = _tfidf_vector(ids_b, idf)

    return _cosine_from_counters(vec_a, vec_b)


def declaration_cosine_tfidf(
    source_a: str, source_b: str, extension: str,
    idf: dict[str, float] | None = None,
) -> float:
    """Compute TF-IDF weighted cosine similarity using declaration identifiers.

    Same as ``declaration_identifier_cosine()`` but applies IDF weighting
    to down-weight boilerplate method names that appear across many files.

    Falls back to ``declaration_identifier_cosine()`` if ``idf`` is None
    or tree-sitter is unavailable.

    Args:
        source_a:  Comment-stripped source of file A.
        source_b:  Comment-stripped source of file B.
        extension: Lowercase file extension (e.g. ``".java"``).
        idf:       IDF dictionary, or None for fallback.

    Returns:
        Cosine similarity ∈ [0.0, 1.0].
    """
    if idf is None:
        return declaration_identifier_cosine(source_a, source_b, extension)

    try:
        from diffinite.ast_normalizer import extract_declaration_identifiers

        ids_a = extract_declaration_identifiers(source_a, extension)
        ids_b = extract_declaration_identifiers(source_b, extension)

        if ids_a is not None and ids_b is not None:
            vec_a = _tfidf_vector(ids_a, idf)
            vec_b = _tfidf_vector(ids_b, idf)
            return _cosine_from_counters(vec_a, vec_b)
    except ImportError:
        pass

    return declaration_identifier_cosine(source_a, source_b, extension)



def _cosine_from_counters(counter_a: Counter, counter_b: Counter) -> float:
    """Compute cosine similarity between two Counter objects."""
    if not counter_a or not counter_b:
        return 0.0
    all_keys = set(counter_a) | set(counter_b)
    dot = sum(counter_a.get(k, 0) * counter_b.get(k, 0) for k in all_keys)
    mag_a = math.sqrt(sum(v * v for v in counter_a.values()))
    mag_b = math.sqrt(sum(v * v for v in counter_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _jaccard_from_sets(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def declaration_identifier_cosine(
    source_a: str, source_b: str, extension: str,
) -> float:
    """Compute cosine similarity using only declaration-level identifiers.

    Unlike ``identifier_cosine()`` which includes ALL identifiers, this
    function uses tree-sitter to extract only **API surface** identifiers:
    class names, method names, formal parameter names, and return types.

    This produces a much stronger SSO signal because implementation-level
    local variable names are excluded, preventing dilution of the API
    name similarity.

    Falls back to standard ``identifier_cosine()`` if tree-sitter is
    unavailable for the given language.

    Args:
        source_a:  Comment-stripped source of file A.
        source_b:  Comment-stripped source of file B.
        extension: Lowercase file extension (e.g. ``".java"``).

    Returns:
        Cosine similarity ∈ [0.0, 1.0].
    """
    try:
        from diffinite.ast_normalizer import extract_declaration_identifiers

        ids_a = extract_declaration_identifiers(source_a, extension)
        ids_b = extract_declaration_identifiers(source_b, extension)

        if ids_a is not None and ids_b is not None:
            return _cosine_from_counters(Counter(ids_a), Counter(ids_b))
    except ImportError:
        pass

    # Fallback to all-identifiers cosine
    return identifier_cosine(source_a, source_b)


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
# Default channel weights — ROC AUC-proportional values derived from
# Stage 3 analysis of 646 pairs.  Higher AUC channels get more weight
# in the composite score to reduce noise from low-discriminative channels.
# Previous intuitive weights: raw=1.0, norm=2.0, ast=2.0, ident=1.5,
# comment=1.0, decl=0.0 (disabled).
_DEFAULT_WEIGHTS: dict[str, float] = {
    "raw_winnowing":        0.720,    # ROC AUC = 0.720 (highest)
    "normalized_winnowing":  0.717,   # ROC AUC = 0.717
    "ast_winnowing":         0.702,   # ROC AUC = 0.702
    "identifier_cosine":     0.587,   # ROC AUC = 0.587
    "comment_string_overlap": 0.528,  # ROC AUC = 0.528 (lowest)
    "declaration_cosine":     0.580,  # ROC AUC = 0.580 — now active in composite
}

# Academic profile weights — tuned via grid search on IR-Plag-Dataset.
# Short academic code (10–30 lines) shares many common identifiers and
# comments across independent submissions, so only structure-based
# Winnowing channels provide reliable discrimination.  Raw winnowing is
# weighted higher because it captures exact-copy patterns (L1–L3) that
# normalised fingerprints absorb.
_ACADEMIC_WEIGHTS: dict[str, float] = {
    "raw_winnowing":        3.0,
    "normalized_winnowing":  1.0,
    "ast_winnowing":         1.0,
    "identifier_cosine":     0.0,
    "comment_string_overlap": 0.0,
    "declaration_cosine":     0.0,
}

_PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "industrial": _DEFAULT_WEIGHTS,
    "academic": _ACADEMIC_WEIGHTS,
}


def get_weights_for_profile(profile: str = "industrial") -> dict[str, float]:
    """Return channel weights for the given profile.

    Args:
        profile: ``"industrial"`` (default) or ``"academic"``.

    Returns:
        Dict mapping channel names to weight values.
    """
    return _PROFILE_WEIGHTS.get(profile, _DEFAULT_WEIGHTS).copy()


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
    weights: Optional[dict[str, float]] = None,
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

    # Channel 6: Declaration Cosine (SSO-specific)
    if cleaned_a is not None and cleaned_b is not None and extension:
        scores["declaration_cosine"] = declaration_identifier_cosine(
            cleaned_a, cleaned_b, extension,
        )

    # Channel 4: Comment/String Overlap
    if source_a is not None and source_b is not None and extension:
        scores["comment_string_overlap"] = comment_string_overlap(
            source_a, source_b, extension,
        )

    # Composite weighted average
    if scores:
        active_weights = weights if weights is not None else _DEFAULT_WEIGHTS
        total_weight = 0.0
        weighted_sum = 0.0
        for channel, score in scores.items():
            w = active_weights.get(channel, 1.0)
            weighted_sum += score * w
            total_weight += w
        scores["composite"] = weighted_sum / total_weight if total_weight else 0.0

    return scores


# ---------------------------------------------------------------------------
# Cross-Channel Classification (Stage 4: Pattern-based SSO detection)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Classification threshold profiles
# ---------------------------------------------------------------------------
# Domain-specific threshold profiles derived from 646-pair corpus analysis.
# Academic code (short, high base similarity) requires stricter thresholds.
#   Academic neg: raw_max=0.62, decl_max=0.85, ast_max=1.0, ident_max=0.96
#   Industrial neg: raw_max=0.05, decl_max=0.40
# See TDD/corpus/domain_profile_analysis.py for derivation.

_CLASSIFICATION_PROFILES: dict[str, dict[str, float]] = {
    "industrial": {
        # Stage 3 grid-search optimised (84K combos, zero-FP objective)
        "dc_raw_min":    0.65,
        "dc_ident_min":  0.50,
        "sso_raw_max":   0.20,
        "sso_decl_min":  0.60,
        "sso_gap_min":   0.30,
        "sso_ast_min":   0.25,
        "obc_raw_max":   0.15,
        "obc_ident_max": 0.30,
        "obc_ast_min":   0.30,
        "conv_ident_min": 0.20,
        "conv_decl_max":  0.40,
        "conv_raw_max":   0.20,
    },
    "academic": {
        # Stricter thresholds for short academic code (neg_raw_max=0.62,
        # neg_decl_max=0.85). Must be above neg maxima to maintain zero-FP.
        "dc_raw_min":    0.70,   # (0.65) neg_raw_max=0.62, +margin
        "dc_ident_min":  0.60,   # (0.50) neg_ident very high
        "sso_raw_max":   0.15,   # (0.20) tighter for short code
        "sso_decl_min":  0.90,   # (0.60) neg_decl_max=0.85(!)
        "sso_gap_min":   0.40,   # (0.30) stricter gap
        "sso_ast_min":   0.40,   # (0.25) neg_ast reaches 1.0
        "obc_raw_max":   0.10,   # (0.15)
        "obc_ident_max": 0.25,   # (0.30)
        "obc_ast_min":   0.40,   # (0.30) above academic baseline
        "conv_ident_min": 0.20,
        "conv_decl_max":  0.30,  # (0.40) tighter
        "conv_raw_max":   0.15,  # (0.20) tighter
    },
}

# Backward-compatible module-level aliases (industrial profile)
_p = _CLASSIFICATION_PROFILES["industrial"]
_DC_RAW_MIN = _p["dc_raw_min"]
_DC_IDENT_MIN = _p["dc_ident_min"]
_SSO_RAW_MAX = _p["sso_raw_max"]
_SSO_DECL_MIN = _p["sso_decl_min"]
_SSO_GAP_MIN = _p["sso_gap_min"]
_SSO_AST_MIN = _p["sso_ast_min"]
_OBC_RAW_MAX = _p["obc_raw_max"]
_OBC_IDENT_MAX = _p["obc_ident_max"]
_OBC_AST_MIN = _p["obc_ast_min"]
_CONV_IDENT_MIN = _p["conv_ident_min"]
_CONV_DECL_MAX = _p["conv_decl_max"]
_CONV_RAW_MAX = _p["conv_raw_max"]
del _p

# AFC-specific thresholds for filtered pipeline (inflation ~1.3-1.7x)
_AFC_SSO_DECL_MIN = 0.75
_AFC_SSO_GAP_MIN = 0.35

# Normalized/raw ratio for Type-2 disguise detection (pos median=1.44)
_SSO_NORM_RAW_RATIO = 1.2


def _classify_strict(
    raw: float, norm: float, ident: float, decl: float, ast: float,
    *, afc_filtered: bool = False, profile: str = "industrial",
) -> str:
    """Stage 1: High-confidence classification using optimized thresholds.

    Returns a definitive classification or ``"INCONCLUSIVE"`` for
    cases that don't meet the strict criteria.
    """
    p = _CLASSIFICATION_PROFILES[profile]

    # AFC overrides for SSO thresholds (only when scores are filtered)
    sso_decl_min = _AFC_SSO_DECL_MIN if afc_filtered else p["sso_decl_min"]
    sso_gap_min = _AFC_SSO_GAP_MIN if afc_filtered else p["sso_gap_min"]

    # -- DIRECT_COPY: all channels high (verbatim or near-verbatim copy)
    if raw > p["dc_raw_min"] and ident > p["dc_ident_min"]:
        return "DIRECT_COPY"

    # -- SSO_COPYING: API surface preserved, implementation differs
    norm_raw_ok = (norm > raw * _SSO_NORM_RAW_RATIO) if raw > 0.01 else (norm > 0.05)
    if (raw < p["sso_raw_max"] and decl >= sso_decl_min
            and (ident - raw) >= sso_gap_min and ast > p["sso_ast_min"]
            and norm_raw_ok):
        return "SSO_COPYING"

    # -- OBFUSCATED_CLONE: raw and ident low, but AST reveals structure
    if raw < p["obc_raw_max"] and ident < p["obc_ident_max"] and ast > p["obc_ast_min"]:
        return "OBFUSCATED_CLONE"

    # -- DOMAIN_CONVERGENCE: similar domain vocabulary but different API
    if ident > p["conv_ident_min"] and decl < p["conv_decl_max"] and raw < p["conv_raw_max"]:
        return "DOMAIN_CONVERGENCE"

    return "INCONCLUSIVE"


# Relaxed thresholds — baseline values before Stage 3 optimisation.
# Used for Stage 2 SUSPICIOUS classification to recover recall.
_RELAXED_DC_RAW_MIN = 0.50    # (strict: 0.65)
_RELAXED_SSO_DECL_MIN = 0.50  # (strict: 0.60)
_RELAXED_SSO_GAP_MIN = 0.25   # (strict: 0.30)


def _classify_relaxed(
    raw: float, norm: float, ident: float, decl: float, ast: float,
    comment: float,
) -> str:
    """Stage 2: Medium-confidence classification using baseline thresholds.

    Only called when Stage 1 returns ``"INCONCLUSIVE"``.
    Returns ``"SUSPICIOUS_COPY"``, ``"SUSPICIOUS_SSO"``, or
    ``"INCONCLUSIVE"`` for borderline cases.

    SUSPICIOUS grades are **advisory** — they flag cases for manual
    review and are NOT counted as positive detections in precision
    metrics.
    """
    # ── SUSPICIOUS_COPY: raw 0.50–0.65 (just below strict DC threshold)
    if raw > _RELAXED_DC_RAW_MIN and ident > _DC_IDENT_MIN:
        return "SUSPICIOUS_COPY"

    # ── SUSPICIOUS_COPY via comment signal: code slightly modified but
    #    comments/strings identical (copying with cosmetic changes)
    if raw > 0.40 and comment > 0.60:
        return "SUSPICIOUS_COPY"

    # ── SUSPICIOUS_SSO: API similarity just below strict SSO threshold
    norm_raw_ok = (norm > raw * _SSO_NORM_RAW_RATIO) if raw > 0.01 else (norm > 0.05)
    if (raw < _SSO_RAW_MAX + 0.05  # slightly wider band
            and decl >= _RELAXED_SSO_DECL_MIN
            and (ident - raw) >= _RELAXED_SSO_GAP_MIN
            and ast > _SSO_AST_MIN
            and norm_raw_ok):
        return "SUSPICIOUS_SSO"

    return "INCONCLUSIVE"


def classify_similarity_pattern(
    scores: dict[str, float],
    *,
    afc_filtered: bool = False,
    profile: str = "industrial",
) -> str:
    """Classify the similarity pattern based on cross-channel evidence.

    Two-stage classification system:

    **Stage 1 (Strict)** — High-confidence classifications using
    optimised thresholds from Stage 3 grid search (zero-FP objective):

    +-----------------------+------+-------+------+------+
    | Scenario              | raw  | ident | decl |  ast |
    +-----------------------+------+-------+------+------+
    | DIRECT_COPY           | HIGH | HIGH  | HIGH | HIGH |
    | SSO_COPYING           | LOW  | HIGH  | HIGH | MED+ |
    | OBFUSCATED_CLONE      | LOW  | LOW   | LOW  | MED+ |
    | DOMAIN_CONVERGENCE    | LOW  | any   | LOW  | LOW  |
    +-----------------------+------+-------+------+------+\

    **Stage 2 (Relaxed)** — Medium-confidence classifications using
    baseline thresholds to recover recall for borderline cases:

    +-------------------+------+-------+------+------+\
    | Scenario          | raw  | ident | decl |  ast |\
    +-------------------+------+-------+------+------+\
    | SUSPICIOUS_COPY   | MED  | MED+  |  -   |  -   |\
    | SUSPICIOUS_SSO    | LOW  | MED   | MED  | MED  |\
    +-------------------+------+-------+------+------+\

    Args:
        scores:       Dict of channel scores as returned by
                      ``compute_channel_scores()``.
        afc_filtered: If True, use stricter AFC-specific thresholds
                      for SSO detection.  AFC filtration removes
                      boilerplate which inflates declaration_cosine
                      by ~1.3–1.7×, requiring higher thresholds.

    Returns:
        One of: ``"DIRECT_COPY"``, ``"SSO_COPYING"``,
        ``"OBFUSCATED_CLONE"``, ``"DOMAIN_CONVERGENCE"``,
        ``"SUSPICIOUS_COPY"``, ``"SUSPICIOUS_SSO"``,
        ``"INCONCLUSIVE"``.\
    """
    raw = scores.get("raw_winnowing", 0.0)
    norm = scores.get("normalized_winnowing", 0.0)
    ident = scores.get("identifier_cosine", 0.0)
    decl = scores.get("declaration_cosine", 0.0)
    ast = scores.get("ast_winnowing", 0.0)
    comment = scores.get("comment_string_overlap", 0.0)

    # Stage 1: strict (high confidence)
    cls = _classify_strict(raw, norm, ident, decl, ast,
                           afc_filtered=afc_filtered, profile=profile)
    if cls != "INCONCLUSIVE":
        return cls

    # Stage 2: relaxed (medium confidence — SUSPICIOUS grades)
    return _classify_relaxed(raw, norm, ident, decl, ast, comment)


# ---------------------------------------------------------------------------
# AFC Analysis  (Stage 6: Abstraction-Filtration-Comparison)
# ---------------------------------------------------------------------------
def afc_analysis(
    source_a: str, source_b: str, extension: str,
    *,
    skip_boilerplate: bool = True,
    idf: dict[str, float] | None = None,
) -> dict:
    """AFC test pipeline following the Altai (1992) 3-step analysis.

    1. **Abstraction**: Decompose programs hierarchically
       (file → class → method → statement)
    2. **Filtration**: Remove unprotectable elements
       (boilerplate, scènes à faire, language idioms)
    3. **Comparison**: Re-score only protectable expression

    Args:
        source_a:         Comment-stripped source of file A.
        source_b:         Comment-stripped source of file B.
        extension:        Lowercase file extension.
        skip_boilerplate: If True, filter boilerplate in declaration analysis.
        idf:              Optional IDF dict for TF-IDF weighting.

    Returns:
        Dict with keys:
          - ``raw_scores``: scores before filtration
          - ``filtered_scores``: scores after filtration
          - ``filtration_report``: what was filtered
          - ``classification``: pattern classification on filtered scores
    """
    from diffinite.fingerprint import extract_fingerprints
    from collections import Counter

    K, W = 5, 4

    # ── Step 0: Raw scores (pre-filtration baseline) ──
    fp_raw_a = {fp.hash_value for fp in extract_fingerprints(
        source_a, k=K, w=W, normalize=False, mode="token", extension=extension)}
    fp_raw_b = {fp.hash_value for fp in extract_fingerprints(
        source_b, k=K, w=W, normalize=False, mode="token", extension=extension)}
    fp_ast_a = {fp.hash_value for fp in extract_fingerprints(
        source_a, k=K, w=W, normalize=True, mode="ast", extension=extension)}
    fp_ast_b = {fp.hash_value for fp in extract_fingerprints(
        source_b, k=K, w=W, normalize=True, mode="ast", extension=extension)}

    raw_scores = {
        "raw_winnowing": _jaccard_from_sets(fp_raw_a, fp_raw_b),
        "ast_winnowing": _jaccard_from_sets(fp_ast_a, fp_ast_b),
        "identifier_cosine": identifier_cosine(source_a, source_b),
        "declaration_cosine": declaration_identifier_cosine(
            source_a, source_b, extension),
    }

    # ── Step 1: Abstraction — hierarchical decomposition ──
    filtration_report: list[str] = []

    try:
        from diffinite.ast_normalizer import (
            extract_declaration_identifiers,
            extract_class_declarations,
        )

        classes_a = extract_class_declarations(source_a, extension)
        classes_b = extract_class_declarations(source_b, extension)
        if classes_a:
            filtration_report.append(
                f"Abstraction: {len(classes_a)} class(es) in source A"
            )
        if classes_b:
            filtration_report.append(
                f"Abstraction: {len(classes_b)} class(es) in source B"
            )
    except ImportError:
        classes_a, classes_b = None, None

    # ── Step 2: Filtration — remove unprotectable elements ──
    # 2a. Boilerplate method filtering
    try:
        from diffinite.ast_normalizer import extract_declaration_identifiers

        ids_full_a = extract_declaration_identifiers(
            source_a, extension, skip_boilerplate=False)
        ids_filt_a = extract_declaration_identifiers(
            source_a, extension, skip_boilerplate=True)
        ids_full_b = extract_declaration_identifiers(
            source_b, extension, skip_boilerplate=False)
        ids_filt_b = extract_declaration_identifiers(
            source_b, extension, skip_boilerplate=True)

        if ids_full_a and ids_filt_a:
            removed = len(ids_full_a) - len(ids_filt_a)
            filtration_report.append(
                f"Filtration: removed {removed} boilerplate identifier(s) from A"
            )
        if ids_full_b and ids_filt_b:
            removed = len(ids_full_b) - len(ids_filt_b)
            filtration_report.append(
                f"Filtration: removed {removed} boilerplate identifier(s) from B"
            )
    except ImportError:
        ids_filt_a, ids_filt_b = None, None

    # 2b. Import filtering for raw winnowing
    fp_filt_a = {fp.hash_value for fp in extract_fingerprints(
        source_a, k=K, w=W, normalize=False, mode="token",
        extension=extension, filter_imports=True)}
    fp_filt_b = {fp.hash_value for fp in extract_fingerprints(
        source_b, k=K, w=W, normalize=False, mode="token",
        extension=extension, filter_imports=True)}

    # ── Step 3: Comparison — re-score on filtered content ──
    filtered_scores = {
        "raw_winnowing": _jaccard_from_sets(fp_filt_a, fp_filt_b),
        "ast_winnowing": raw_scores["ast_winnowing"],  # AST not affected by imports
        "identifier_cosine": raw_scores["identifier_cosine"],
    }

    # Declaration cosine with boilerplate filtering
    if ids_filt_a is not None and ids_filt_b is not None:
        filtered_scores["declaration_cosine"] = _cosine_from_counters(
            Counter(ids_filt_a), Counter(ids_filt_b)
        )
    else:
        filtered_scores["declaration_cosine"] = raw_scores["declaration_cosine"]

    # Apply TF-IDF if available
    if idf is not None:
        filtered_scores["identifier_cosine"] = identifier_cosine_tfidf(
            source_a, source_b, idf=idf
        )

    return {
        "raw_scores": raw_scores,
        "filtered_scores": filtered_scores,
        "filtration_report": filtration_report,
        "classification": classify_similarity_pattern(
            filtered_scores, afc_filtered=True
        ),
    }


# ---------------------------------------------------------------------------
# Legal defense pattern analysis (Idea-Expression Dichotomy)
# ---------------------------------------------------------------------------

_LEGAL_DISCLAIMER = (
    "본 분석은 코드의 구조적 유사도에 대한 기술적 정량 분석이며, "
    "저작권 침해 여부에 대한 법적 판단은 법원의 권한에 속합니다."
)


def _run_profile_scores(
    source_a: str, source_b: str, extension: str,
    *, k: int, w: int, normalize_ast: bool,
) -> dict[str, float]:
    """Run fingerprinting with given parameters and return 6-channel scores."""
    from diffinite.fingerprint import extract_fingerprints

    fp_raw_a = {fp.hash_value for fp in extract_fingerprints(
        source_a, k=k, w=w, normalize=False, mode="token", extension=extension)}
    fp_raw_b = {fp.hash_value for fp in extract_fingerprints(
        source_b, k=k, w=w, normalize=False, mode="token", extension=extension)}

    fp_norm_a = {fp.hash_value for fp in extract_fingerprints(
        source_a, k=k, w=w, normalize=True, mode="token", extension=extension)}
    fp_norm_b = {fp.hash_value for fp in extract_fingerprints(
        source_b, k=k, w=w, normalize=True, mode="token", extension=extension)}

    fp_ast_a = {fp.hash_value for fp in extract_fingerprints(
        source_a, k=k, w=w, normalize=normalize_ast, mode="ast",
        extension=extension)}
    fp_ast_b = {fp.hash_value for fp in extract_fingerprints(
        source_b, k=k, w=w, normalize=normalize_ast, mode="ast",
        extension=extension)}

    return compute_channel_scores(
        fp_raw_a=fp_raw_a, fp_raw_b=fp_raw_b,
        fp_norm_a=fp_norm_a, fp_norm_b=fp_norm_b,
        fp_ast_a=fp_ast_a, fp_ast_b=fp_ast_b,
        source_a=source_a, source_b=source_b,
        cleaned_a=source_a, cleaned_b=source_b,
        extension=extension,
    )


def _both_dropped_significantly(
    raw: dict[str, float], filtered: dict[str, float],
    drop_threshold: float = 0.20,
) -> bool:
    """Check if AFC filtration caused >20% composite drop."""
    raw_c = raw.get("composite", 0.0)
    filt_c = filtered.get("composite", 0.0)
    if raw_c < 0.1:
        return False
    return (raw_c - filt_c) / raw_c > drop_threshold


def _generate_legal_explanation(
    pattern: str,
    ind: dict[str, float],
    acad: dict[str, float],
    delta: float,
) -> str:
    """Generate natural-language technical interpretation."""
    raw_w = ind.get("raw_winnowing", 0.0)
    ast_w = acad.get("ast_winnowing", 0.0)
    ind_c = ind.get("composite", 0.0)
    acad_c = acad.get("composite", 0.0)

    explanations = {
        "CLEAN_ROOM_PROBABLE": (
            f"Industrial Profile(raw={raw_w:.2f})가 낮고 "
            f"Academic Profile(ast={ast_w:.2f})가 높으므로, "
            f"표현의 문자적 복제 없이 동일 아이디어를 독립 구현한 "
            f"클린룸 설계로 추정됩니다. (delta={delta:+.2f})"
        ),
        "LITERAL_COPYING": (
            f"Industrial(raw={raw_w:.2f})와 "
            f"Academic(composite={acad_c:.2f}) 모두 높은 유사도이며, "
            f"프로필 간 격차가 작습니다(delta={delta:+.2f}). "
            f"표현(Expression)까지 복제된 것을 시사합니다."
        ),
        "INDEPENDENT_CREATION": (
            f"두 프로필 모두 낮은 유사도입니다 "
            f"(Industrial={ind_c:.2f}, Academic={acad_c:.2f}). "
            f"독립 작성 코드로 판단됩니다."
        ),
        "MERGER_FILTERED": (
            f"AFC 필터링 후 유사도가 유의미하게 하락했습니다. "
            f"유사 부분은 디자인 패턴/표준 관용구 등 "
            f"'합체(Merger)' 요소로 추정됩니다."
        ),
        "INCONCLUSIVE": (
            f"명확한 법적 패턴에 부합하지 않습니다 "
            f"(Industrial={ind_c:.2f}, Academic={acad_c:.2f}, "
            f"delta={delta:+.2f}). 수동 검토가 필요합니다."
        ),
    }
    text = explanations.get(pattern, explanations["INCONCLUSIVE"])
    return f"{text}\n\n[면책조항] {_LEGAL_DISCLAIMER}"


def analyze_legal_defense_pattern(
    source_a: str, source_b: str, extension: str,
    *,
    idf: dict[str, float] | None = None,
) -> dict:
    """Dual-profile legal defense analysis (Idea-Expression Dichotomy).

    Runs two profiles and compares results to classify into legal
    defense categories:

    - **CLEAN_ROOM_PROBABLE**: Low industrial + high academic.
    - **LITERAL_COPYING**: Both profiles high, small delta.
    - **INDEPENDENT_CREATION**: Both profiles low.
    - **MERGER_FILTERED**: AFC filtration drops scores >20%.
    - **INCONCLUSIVE**: No clear match.

    Args:
        source_a:  Source code of file A.
        source_b:  Source code of file B.
        extension: File extension (e.g., ".java").
        idf:       Optional IDF dict for TF-IDF weighting.

    Returns:
        Dict with ``industrial_scores``, ``academic_scores``,
        ``delta``, ``legal_pattern``, ``explanation``.
    """
    # Industrial profile: K=5, W=4, no AST normalisation
    ind = _run_profile_scores(source_a, source_b, extension,
                              k=5, w=4, normalize_ast=False)

    # Academic profile: K=2, W=3, with AST normalisation
    acad = _run_profile_scores(source_a, source_b, extension,
                               k=2, w=3, normalize_ast=True)

    delta = acad.get("composite", 0.0) - ind.get("composite", 0.0)

    # Pattern classification
    raw_w = ind.get("raw_winnowing", 0.0)
    acad_ast = acad.get("ast_winnowing", 0.0)
    acad_c = acad.get("composite", 0.0)
    ind_c = ind.get("composite", 0.0)

    if raw_w < 0.20 and acad_ast > 0.70 and delta > 0.40:
        pattern = "CLEAN_ROOM_PROBABLE"
    elif raw_w > 0.60 and acad_c > 0.70 and abs(delta) < 0.15:
        pattern = "LITERAL_COPYING"
    elif ind_c < 0.20 and acad_c < 0.30:
        pattern = "INDEPENDENT_CREATION"
    else:
        pattern = "INCONCLUSIVE"

    # AFC check: merger/scenes-a-faire detection
    try:
        afc = afc_analysis(source_a, source_b, extension, idf=idf)
        if _both_dropped_significantly(afc["raw_scores"],
                                       afc["filtered_scores"]):
            pattern = "MERGER_FILTERED"
    except Exception:
        pass

    return {
        "industrial_scores": ind,
        "academic_scores": acad,
        "delta": delta,
        "legal_pattern": pattern,
        "explanation": _generate_legal_explanation(pattern, ind, acad, delta),
    }




