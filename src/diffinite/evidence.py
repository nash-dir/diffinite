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

# Classification thresholds — data-driven values from Stage 3 grid search.
# See TDD/corpus/optimal_thresholds.json for derivation.
# Two-phase optimisation: Phase 1 → zero SSO/DC FP, Phase 2 → max F1.
#
# Format: PARAM = optimal_value  # (baseline was X.XX)
_DC_RAW_MIN = 0.65           # (baseline: 0.50) — raised to suppress short-code FP
_DC_IDENT_MIN = 0.50         # (baseline: 0.50)
_SSO_RAW_MAX = 0.20          # (baseline: 0.25) — tightened to block high-raw SSO FP
_SSO_DECL_MIN = 0.60         # (baseline: 0.50) — raised to suppress academic-code FP
_SSO_GAP_MIN = 0.30          # (baseline: 0.25) — raised for domain-convergence filtering
_SSO_AST_MIN = 0.25          # (baseline: 0.25)
_OBC_RAW_MAX = 0.15          # (baseline: 0.15)
_OBC_IDENT_MAX = 0.30        # (baseline: 0.30)
_OBC_AST_MIN = 0.30          # (baseline: 0.30)
_CONV_IDENT_MIN = 0.20       # (baseline: 0.20)
_CONV_DECL_MAX = 0.40        # (baseline: 0.40)
_CONV_RAW_MAX = 0.20         # (baseline: 0.20)

# AFC-specific thresholds — higher bar for SSO when scores come from
# filtered pipeline.  AFC filtration removes boilerplate identifiers
# which concentrates remaining identifiers and inflates declaration_cosine
# by ~1.3–1.7× (see TDD/corpus/afc_score_analysis.py).
# Guava:Lists filt_decl=0.7285 triggers SSO with normal thresholds.
_AFC_SSO_DECL_MIN = 0.75     # (normal: 0.60) — +0.15 to absorb filtration inflation
_AFC_SSO_GAP_MIN = 0.35      # (normal: 0.30) — slightly stricter for filtered scores

# Normalized/raw winnowing ratio threshold for Type-2 disguise detection.
# Positive pairs have median ratio 1.44 (identifier renaming inflates norm).
# Negative pairs have ratio ≈ 1.0 (no identifier changes).
# See TDD/corpus/norm_raw_analysis.py for derivation.
_SSO_NORM_RAW_RATIO = 1.2    # norm must exceed raw by 20%+ for SSO


def _classify_strict(
    raw: float, norm: float, ident: float, decl: float, ast: float,
    *, afc_filtered: bool = False,
) -> str:
    """Stage 1: High-confidence classification using optimized thresholds.

    Returns a definitive classification or ``"INCONCLUSIVE"`` for
    cases that don't meet the strict criteria.
    """
    sso_decl_min = _AFC_SSO_DECL_MIN if afc_filtered else _SSO_DECL_MIN
    sso_gap_min = _AFC_SSO_GAP_MIN if afc_filtered else _SSO_GAP_MIN

    # ── DIRECT_COPY: all channels high (verbatim or near-verbatim copy)
    if raw > _DC_RAW_MIN and ident > _DC_IDENT_MIN:
        return "DIRECT_COPY"

    # ── SSO_COPYING: API surface preserved, implementation differs
    norm_raw_ok = (norm > raw * _SSO_NORM_RAW_RATIO) if raw > 0.01 else (norm > 0.05)
    if (raw < _SSO_RAW_MAX and decl >= sso_decl_min
            and (ident - raw) >= sso_gap_min and ast > _SSO_AST_MIN
            and norm_raw_ok):
        return "SSO_COPYING"

    # ── OBFUSCATED_CLONE: raw and ident low, but AST reveals structure
    if raw < _OBC_RAW_MAX and ident < _OBC_IDENT_MAX and ast > _OBC_AST_MIN:
        return "OBFUSCATED_CLONE"

    # ── DOMAIN_CONVERGENCE: similar domain vocabulary but different API
    if ident > _CONV_IDENT_MIN and decl < _CONV_DECL_MAX and raw < _CONV_RAW_MAX:
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
                           afc_filtered=afc_filtered)
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



