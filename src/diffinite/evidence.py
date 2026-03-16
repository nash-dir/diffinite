"""다중 증거 채널 분석 엔진 — Diffinite의 핵심.

6개의 독립 증거 채널을 통해 코드 유사성의 다양한 측면을 정량화하고,
교차 채널 패턴으로 복사 유형을 분류하며, AFC(Altai) 테스트로 법적
보호 가능 표현만을 비교한다.

모듈 구성:
    1. **식별자 분석** — 코사인 유사도 (일반 + TF-IDF)
    2. **주석/문자열 채널** — Jaccard + TF-IDF 코사인
    3. **Composite 점수** — ROC AUC 비례 가중 앙상블
    4. **2단계 분류** — Strict (zero-FP) + Relaxed (재현율 보완)
    5. **AFC 파이프라인** — Computer Associates v. Altai (1992) 구현
    6. **법리 델타 분석** — 아이디어-표현 이분법 정량화

설계 원칙:
    - 각 채널은 독립적으로 해석 가능해야 한다 (단일 채널만으로도 의미).
    - 분류 임계값은 646쌍 코퍼스에서 grid search로 최적화.
    - SUSPICIOUS 등급은 정밀도 계산에서 제외 (참고용).
    - 법리 분석 임계값은 아직 직관적 추정 — 실데이터 교정 필요.

의존:
    - ``fingerprint.py``: ``_COMMON_KEYWORDS``, 토크나이저
    - ``ast_normalizer.py``: 선언부 식별자 추출, 구조 선형화
    - ``languages/``: Java-family 확장자 판별

호출관계 (주요):
    ``deep_compare._run_multi_channel()`` → ``compute_channel_scores()``
    ``deep_compare._run_multi_channel()`` → ``classify_similarity_pattern()``
    ``deep_compare._run_multi_channel()`` → ``afc_analysis()``
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from diffinite.fingerprint import _COMMON_KEYWORDS, TOKEN_RE

# ──────────────────────────────────────────────────────────────────────
# 식별자 코사인 유사도 채널
# ──────────────────────────────────────────────────────────────────────

# 노이즈 식별자 — 코사인 유사도를 부풀리지만 SSO를 나타내지 않는 토큰.
# Java 표준 타입명(scènes à faire)과 단일 문자 변수를 포함.
# _JAVA_FAMILY_EXTS 가드로 Java 계열에서만 타입명 필터링 적용.
#  - Single-character loop/generic variables
_JAVA_TYPE_STOPWORDS = frozenset({
    "String", "Object", "Integer", "Long", "Double", "Float",
    "Boolean", "Character", "Byte", "Short", "Number",
    "Void", "Class", "Comparable", "Iterable", "Iterator",
    "Serializable", "Cloneable", "Exception", "Throwable",
    "Override", "Deprecated", "SuppressWarnings",
})

# Extensions where Java-specific filters apply
_JAVA_FAMILY_EXTS = frozenset({".java", ".kt", ".scala", ".groovy"})


def _is_noise_identifier(token: str, extension: str = ".java") -> bool:
    """Check if *token* is a noise identifier that should be excluded.

    Filters:
    - Single-character identifiers (loop vars `i`, `j`, `k`; generics `V`, `K`, `T`)
    - Java standard type names (only for Java-family languages)
    """
    if len(token) == 1:
        return True  # i, j, k, V, K, T, E, etc.
    if extension in _JAVA_FAMILY_EXTS and token in _JAVA_TYPE_STOPWORDS:
        return True
    return False


def _extract_identifiers(source: str, extension: str = ".java") -> list[str]:
    """Extract identifier tokens (excluding keywords and noise identifiers).

    Filters out language keywords, single-character variables (loop/generics),
    and Java standard type names that are scènes à faire.

    Args:
        source: Source code text (comments already stripped).
        extension: File extension for language-specific filtering.

    Returns:
        List of identifier strings.
    """
    tokens = TOKEN_RE.findall(source)
    return [
        t for t in tokens
        if t not in _COMMON_KEYWORDS
        and (t[0].isalpha() or t[0] == '_')
        and not _is_noise_identifier(t, extension)
    ]



def identifier_cosine(
    source_a: str, source_b: str,
    extension: str = ".java",
) -> float:
    """Compute cosine similarity between identifier frequency vectors.

    A high score means the two files share the same variable/function
    names in similar proportions — strong evidence of copying.
    A low score when structure-based similarity is high indicates
    deliberate renaming (Type-2 clone disguise).

    Args:
        source_a: Comment-stripped source of file A.
        source_b: Comment-stripped source of file B.
        extension: File extension for language-specific filtering.

    Returns:
        Cosine similarity ∈ [0.0, 1.0].
    """
    ids_a = Counter(_extract_identifiers(source_a, extension))
    ids_b = Counter(_extract_identifiers(source_b, extension))

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

    ids_a = _extract_identifiers(source_a, extension=".java")
    ids_b = _extract_identifiers(source_b, extension=".java")

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


# -- Comment channel filtering constants --
_LICENSE_KEYWORDS = frozenset({
    "copyright", "license", "licensed", "apache", "gpl", "mit",
    "bsd", "mozilla", "lgpl", "permission", "redistribution",
    "warranty", "merchantability", "all rights reserved",
})
_JAVADOC_TAGS = frozenset({
    "@param", "@return", "@returns", "@throws", "@exception",
    "@see", "@since", "@version", "@author", "@deprecated",
    "@Override", "@override", "@link", "@code", "@inheritDoc",
    "@serial", "@serialField", "@serialData",
})


def _is_license_line(line: str) -> bool:
    """Check if a comment line is part of a license/copyright header."""
    lower = line.lower()
    return any(kw in lower for kw in _LICENSE_KEYWORDS)


def _strip_javadoc_tags(fragment: str) -> str:
    """Remove Javadoc/annotation tag markers from a comment fragment."""
    for tag in _JAVADOC_TAGS:
        fragment = fragment.replace(tag, "")
    return fragment.strip()


def extract_comments_and_strings(
    text: str, extension: str,
    *, filter_license: bool = True, filter_javadoc_tags: bool = True,
) -> list[str]:
    """Extract comment and string-literal content from source code.

    This is the **inverse** of ``parser.strip_comments()``: instead of
    removing comments, we collect them.  String literals are also
    collected because they carry author-specific content (messages,
    URLs, magic constants) that persists across code copying.

    Args:
        text:                Raw source code (with comments intact).
        extension:           Lowercase file extension (e.g. ``".py"``).
        filter_license:      If True, skip license/copyright header lines.
        filter_javadoc_tags: If True, strip Javadoc tag markers.

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
            if not comment_part:
                continue
            # Filter license/copyright lines
            if filter_license and _is_license_line(comment_part):
                continue
            # Strip Javadoc tags (Java-family only)
            if filter_javadoc_tags and extension in _JAVA_FAMILY_EXTS:
                comment_part = _strip_javadoc_tags(comment_part)
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


def comment_string_overlap_tfidf(
    text_a: str, text_b: str, extension: str,
    idf: dict[str, float] | None = None,
) -> float:
    """TF-IDF weighted cosine similarity over comment/string tokens.

    Improvement over ``comment_string_overlap()`` which uses Jaccard.
    Tokenises comment fragments and applies IDF weighting to
    down-weight common patterns and amplify author-specific content.

    Falls back to ``comment_string_overlap()`` if ``idf`` is None.

    Args:
        text_a:    Raw source of file A.
        text_b:    Raw source of file B.
        extension: Lowercase file extension.
        idf:       IDF dictionary, or None for Jaccard fallback.

    Returns:
        Cosine similarity in [0.0, 1.0].
    """
    if idf is None:
        return comment_string_overlap(text_a, text_b, extension)

    frags_a = extract_comments_and_strings(text_a, extension)
    frags_b = extract_comments_and_strings(text_b, extension)

    # Tokenise fragments into word-level tokens
    tokens_a: list[str] = []
    tokens_b: list[str] = []
    for frag in frags_a:
        tokens_a.extend(TOKEN_RE.findall(frag.lower()))
    for frag in frags_b:
        tokens_b.extend(TOKEN_RE.findall(frag.lower()))

    if not tokens_a or not tokens_b:
        return 0.0

    vec_a = _tfidf_vector(tokens_a, idf)
    vec_b = _tfidf_vector(tokens_b, idf)

    return _cosine_from_counters(vec_a, vec_b)


# ──────────────────────────────────────────────────────────────────────
# Composite 다채널 점수 산정
# ──────────────────────────────────────────────────────────────────────
# Industrial 기본 가중치: ROC AUC 비례.
# 646쌍 코퍼스 Stage 3 분석에서 도출. AUC가 높은 채널이 composite에 더 기여.
# 초기 직관적 가중치(raw=1.0, norm=2.0, ...)는 코퍼스 기반 최적화로 대체됨.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "raw_winnowing":        0.720,    # ROC AUC = 0.720
    "normalized_winnowing":  0.717,   # ROC AUC = 0.717
    "ast_winnowing":         0.702,   # ROC AUC = 0.702
    "identifier_cosine":     0.587,   # ROC AUC = 0.587
    "comment_string_overlap": 0.847,  # ROC AUC = 0.847 (주석 채널 강화 후 재측정)
    "declaration_cosine":     0.580,  # ROC AUC = 0.580
}

# Academic 프로파일 가중치: IR-Plag-Dataset grid search 최적화.
# 학술 코드(10–30줄)는 짧아서 식별자/주석이 독립 작성에서도 높은 cosine을 보임.
# 따라서 구조 기반 Winnowing 채널만 사용하고 ident/comment = 0.
# raw를 3.0으로 높인 이유: L1–L3(정확 복사) 탐지를 normalized가 흡수하는 것을 보정.
_ACADEMIC_WEIGHTS: dict[str, float] = {
    "raw_winnowing":        3.0,
    "normalized_winnowing":  1.0,
    "ast_winnowing":         1.0,
    "identifier_cosine":     0.0,   # 학술 코드는 식별자 유사도 가치 없음
    "comment_string_overlap": 0.0,  # 학술 코드는 주석 유사도 가치 없음
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


# ──────────────────────────────────────────────────────────────────────
# 2단계 분류 시스템 (Stage 4: 교차 채널 패턴 기반 SSO 탐지)
# ──────────────────────────────────────────────────────────────────────

from diffinite.models import ClassificationThresholds, IDEXThresholds

# 646쌍 코퍼스 분석으로 도출. 학술 코드는 짧은 파일 때문에 기본 유사도가 높으므로
# 임계값을 상향 조정. neg_max(음성 최대값) 이상으로 설정해야 zero-FP 유지.
#   Academic neg: raw_max=0.62, decl_max=0.85, ast_max=1.0, ident_max=0.96
#   Industrial neg: raw_max=0.05, decl_max=0.40
# 도출 근거: TDD/corpus/domain_profile_analysis.py

INDUSTRIAL_THRESHOLDS = ClassificationThresholds()
"""Industrial 프로파일 (기본값). 84K 조합 grid search 최적화 (zero-FP 목표)."""

ACADEMIC_THRESHOLDS = ClassificationThresholds(
    dc_raw_min=0.70,
    dc_ident_min=0.60,
    sso_raw_max=0.15,
    sso_decl_min=0.90,
    sso_gap_min=0.40,
    sso_ast_min=0.40,
    obc_raw_max=0.10,
    obc_ident_max=0.25,
    obc_ast_min=0.40,
    conv_ident_min=0.20,
    conv_decl_max=0.30,
    conv_raw_max=0.15,
    susp_raw_min=0.55,
    susp_ident_min=0.55,
    susp_sso_ident_min=0.55,
    susp_sso_decl_min=0.55,
    susp_sso_ast_min=0.40,
    comment_boost_min=0.60,
)
"""Academic 프로파일. neg_max 분석 기반 상향 조정."""

_THRESHOLDS_MAP: dict[str, ClassificationThresholds] = {
    "industrial": INDUSTRIAL_THRESHOLDS,
    "academic": ACADEMIC_THRESHOLDS,
}


def _get_thresholds(profile: str = "industrial") -> ClassificationThresholds:
    """프로파일 이름으로 임계값 dataclass를 반환한다."""
    return _THRESHOLDS_MAP.get(profile, INDUSTRIAL_THRESHOLDS)


# Backward-compatible module-level aliases (industrial profile)
_DC_RAW_MIN = INDUSTRIAL_THRESHOLDS.dc_raw_min
_DC_IDENT_MIN = INDUSTRIAL_THRESHOLDS.dc_ident_min
_SSO_RAW_MAX = INDUSTRIAL_THRESHOLDS.sso_raw_max
_SSO_DECL_MIN = INDUSTRIAL_THRESHOLDS.sso_decl_min
_SSO_GAP_MIN = INDUSTRIAL_THRESHOLDS.sso_gap_min
_SSO_AST_MIN = INDUSTRIAL_THRESHOLDS.sso_ast_min
_OBC_RAW_MAX = INDUSTRIAL_THRESHOLDS.obc_raw_max
_OBC_IDENT_MAX = INDUSTRIAL_THRESHOLDS.obc_ident_max
_OBC_AST_MIN = INDUSTRIAL_THRESHOLDS.obc_ast_min
_CONV_IDENT_MIN = INDUSTRIAL_THRESHOLDS.conv_ident_min
_CONV_DECL_MAX = INDUSTRIAL_THRESHOLDS.conv_decl_max
_CONV_RAW_MAX = INDUSTRIAL_THRESHOLDS.conv_raw_max

# AFC 전용 임계값 — Filtration이 유사도를 부풀리는 "inflation" 효과(1.3–1.7×)를 보정.
# 예: 보일러플레이트 제거 후 Jaccard가 0.40 → 0.65로 상승 가능.
_AFC_SSO_DECL_MIN = 0.75
_AFC_SSO_GAP_MIN = 0.35

# Normalized/raw 비율: Type-2 난독화 탐지용.
# 양성 중앙값(positive median) = 1.44. 이하에서 raw와 norm 차이가 작으면
# 식별자 변경 없는 복사로 판단.
_SSO_NORM_RAW_RATIO = 1.2


def _classify_strict(
    raw: float, norm: float, ident: float, decl: float, ast: float,
    *, afc_filtered: bool = False, profile: str = "industrial",
) -> str:
    """Stage 1: 고확신 분류 (zero-FP 목표).

    최적화된 임계값으로 확실한 패턴만 분류.
    어떤 패턴에도 해당하지 않으면 ``INCONCLUSIVE`` 반환 → Stage 2로 위임.

    주의:
        ``afc_filtered=True``일 때 SSO 임계값이 높아지는 이유:
        Filtration이 보일러플레이트를 제거하면 유사도 점수가 평균 1.3–1.7×
        부풀려지므로(inflation), 판단 기준도 상향 보정해야 한다.
    """
    p = _get_thresholds(profile)

    # AFC overrides for SSO thresholds (only when scores are filtered)
    sso_decl_min = _AFC_SSO_DECL_MIN if afc_filtered else p.sso_decl_min
    sso_gap_min = _AFC_SSO_GAP_MIN if afc_filtered else p.sso_gap_min

    # -- DIRECT_COPY: all channels high (verbatim or near-verbatim copy)
    if raw > p.dc_raw_min and ident > p.dc_ident_min:
        return "DIRECT_COPY"

    # -- SSO_COPYING: API surface preserved, implementation differs
    norm_raw_ok = (norm > raw * _SSO_NORM_RAW_RATIO) if raw > 0.01 else (norm > 0.05)
    if (raw < p.sso_raw_max and decl >= sso_decl_min
            and (ident - raw) >= sso_gap_min and ast > p.sso_ast_min
            and norm_raw_ok):
        return "SSO_COPYING"

    # -- OBFUSCATED_CLONE: raw and ident low, but AST reveals structure
    if raw < p.obc_raw_max and ident < p.obc_ident_max and ast > p.obc_ast_min:
        return "OBFUSCATED_CLONE"

    # -- DOMAIN_CONVERGENCE: similar domain vocabulary but different API
    if ident > p.conv_ident_min and decl < p.conv_decl_max and raw < p.conv_raw_max:
        return "DOMAIN_CONVERGENCE"

    return "INCONCLUSIVE"


# Relaxed 임계값은 ClassificationThresholds의 susp_* 필드로 통합됨.
# 아래 상수는 backward-compatibility용.
_RELAXED_DC_RAW_MIN = INDUSTRIAL_THRESHOLDS.susp_raw_min
_RELAXED_SSO_DECL_MIN = INDUSTRIAL_THRESHOLDS.susp_sso_decl_min
_RELAXED_SSO_GAP_MIN = 0.25   # (strict: 0.30 → 완화)


def _classify_relaxed(
    raw: float, norm: float, ident: float, decl: float, ast: float,
    comment: float,
    *, profile: str = "industrial",
) -> str:
    """Stage 2: 중확신 분류 (재현율 보완).

    Stage 1이 ``INCONCLUSIVE``일 때만 호출된다.
    ``SUSPICIOUS_COPY`` / ``SUSPICIOUS_SSO`` / ``INCONCLUSIVE`` 반환.

    설계 의도:
        단일 임계값 시스템의 precision-recall 트레이드오프를
        2단계로 분리하여 양쪽 모두 최적화:
        - Stage 1 (Strict): 정밀도 우선 → 법적 증거로 사용 가능
        - Stage 2 (Relaxed): 재현율 우선 → 수동 검토 권고용
    """

    p = _get_thresholds(profile)

    # ── SUSPICIOUS_COPY: raw 0.50–0.65 (just below strict DC threshold)
    if raw > p.susp_raw_min and ident > p.susp_ident_min:
        return "SUSPICIOUS_COPY"

    # ── SUSPICIOUS_COPY via comment signal: code slightly modified but
    #    comments/strings identical (copying with cosmetic changes)
    if raw > 0.40 and comment > p.comment_boost_min:
        return "SUSPICIOUS_COPY"

    # ── SUSPICIOUS_SSO: API similarity just below strict SSO threshold
    norm_raw_ok = (norm > raw * _SSO_NORM_RAW_RATIO) if raw > 0.01 else (norm > 0.05)
    if (raw < p.sso_raw_max + 0.05  # slightly wider band
            and decl >= p.susp_sso_decl_min
            and (ident - raw) >= _RELAXED_SSO_GAP_MIN
            and ast > p.susp_sso_ast_min
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
    return _classify_relaxed(raw, norm, ident, decl, ast, comment,
                             profile=profile)


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
    raw_source_a: str | None = None,
    raw_source_b: str | None = None,
) -> dict[str, float]:
    """Run fingerprinting with given parameters and return 6-channel scores.

    Args:
        source_a:       Comment-stripped source of file A (for fingerprinting).
        source_b:       Comment-stripped source of file B (for fingerprinting).
        raw_source_a:   Raw (with comments) source A for comment channel.
                        If None, ``source_a`` is used (comment channel will be 0).
        raw_source_b:   Raw (with comments) source B for comment channel.
    """
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
        source_a=raw_source_a if raw_source_a is not None else source_a,
        source_b=raw_source_b if raw_source_b is not None else source_b,
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

    # Pattern classification (IDEXThresholds로 외부화)
    t = IDEXThresholds()
    raw_w = ind.get("raw_winnowing", 0.0)
    acad_ast = acad.get("ast_winnowing", 0.0)
    acad_c = acad.get("composite", 0.0)
    ind_c = ind.get("composite", 0.0)

    if raw_w < t.cr_raw_max and acad_ast > t.cr_ast_min and delta > t.cr_delta_min:
        pattern = "CLEAN_ROOM_PROBABLE"
    elif raw_w > t.lc_raw_min and acad_c > t.lc_acad_min and abs(delta) < t.lc_delta_max:
        pattern = "LITERAL_COPYING"
    elif ind_c < t.ic_ind_max and acad_c < t.ic_acad_max:
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




