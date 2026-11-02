"""Ratified operating point for the ``--normalize`` fingerprint channel.

Single source of truth for the normalize-mode threshold and the conservative
inconclusive token guard. The threshold was measured by the validation harness
(``tests/validation/error_rate.py``) on the Karnalim IR-Plag corpus and ratified
by the maintainer at the **false-positive ≤ 1%** operating point. The token guard
was part of that configured profile but was non-binding on the measured corpus,
so it carries no separate calibrated precision claim.

Why these exist
---------------
The default ``--threshold-deep 5`` was only ever validated against the
*non-normalize* negative control. Under ``--normalize`` the measured
false-positive rate on independent, same-domain code is 100% at threshold 5
(see ``example/validation/error_rate.md``): identifier flattening collapses
distinct authors of small, structurally-standard code onto identical
fingerprints. Without a measured error rate the inference "Jaccard X% ⇒ copied"
does not stand. These constants are the maintainer-ratified answer.

Provenance: ``example/validation/calibration.json`` (regenerate with
``python -m tests.validation.error_rate``). At the ratified FP ≤ 1% point the
harness reported: floor 45 tokens, threshold 93, recall 21.7%, coverage 100%,
realized false-positive rate 0.95%.

Scope: these apply to the normalize channel only. The raw (non-normalize) path
keeps its historical 5% default so existing forensic reports reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Historical raw-channel compatibility value. Validation found it uncalibrated;
# it remains only so old reports can be reproduced without a silent default shift.
RAW_LEGACY_THRESHOLD: float = 5.0

# Minimum Jaccard (0–100 scale) to report a match under --normalize, when the
# user does not override --threshold-deep. Derived for false-positive ≤ 1%.
NORMALIZE_DEFAULT_THRESHOLD: float = 93.0

# Below this token count (the smaller of the two files in a pair), a --normalize
# match is conservatively reported as INCONCLUSIVE. At threshold 93 the guard was
# non-binding on IR-Plag, so it is compatibility behavior rather than a measured
# claim that 45 tokens separates reliable from unreliable results.
INCONCLUSIVE_TOKEN_FLOOR: int = 45

# Realized false-positive rate at the operating point above, for disclosure on
# reports. Percent. (Independent same-domain code flagged as matches.) This is a
# POINT estimate of 1/105 file pairs — see NORMALIZE_FP_CI95 for the interval; it
# is not a "known" 1% rate.
NORMALIZE_FP_RATE_PCT: float = 0.95

# Wilson 95% CI for the false-positive rate (percent). The point estimate rests
# on a single observation, so the true rate is consistent with anything up to the
# upper bound. Forensic reports must cite the interval, not the point.
NORMALIZE_FP_CI95: tuple[float, float] = (0.17, 5.2)

# Recall at the operating point (all levels pooled), for context. The pool is
# MISLEADING on its own — see NORMALIZE_RECALL_NEAR_VERBATIM_PCT: at threshold 93
# recall collapses to ~0% for heavily restructured copies (L4-L6).
NORMALIZE_RECALL_PCT: float = 21.7

# Recall on near-verbatim copies (L1) at the operating point. The honest framing:
# the calibrated threshold reliably flags near-verbatim copies and effectively
# nothing that is heavily restructured.
NORMALIZE_RECALL_NEAR_VERBATIM_PCT: float = 65.0

# Largest file (tokens) in the calibration corpus. The operating point is
# unvalidated above this size.
CALIBRATION_MAX_TOKENS: int = 212

# Frozen execution profile used to produce example/validation/calibration.json.
# tests/validation/error_rate.py stripped comments and invoked the then-default
# fingerprint extractor at K=5/W=4 without language-aware normalization. Keeping
# these values frozen prevents a future runtime-default change from silently
# expanding the artifact's measured false-positive claim to an untested channel.
NORMALIZE_CALIBRATION_PROFILE_ID: str = "ir-plag-file-pair-normalize-v1"
NORMALIZE_CALIBRATION_K: int = 5
NORMALIZE_CALIBRATION_W: int = 4
NORMALIZE_CALIBRATION_STRIP_COMMENTS: bool = True
NORMALIZE_CALIBRATION_LANG_AWARE: bool = False


@dataclass(frozen=True)
class NormalizeCalibrationAssessment:
    """Whether the published normalize statistics apply to one effective run."""

    profile_id: str
    threshold: float
    status: str
    profile_mismatches: tuple[str, ...]
    threshold_matches: bool

    @property
    def applicable(self) -> bool:
        return self.status == "applicable"


class NormalizeCalibrationMetadata(Protocol):
    """Minimal effective metadata needed to assess calibration applicability."""

    @property
    def threshold(self) -> float: ...

    @property
    def k(self) -> int: ...

    @property
    def w(self) -> int: ...

    @property
    def strip_comments(self) -> bool | None: ...

    @property
    def lang_aware(self) -> bool: ...


def assess_normalize_calibration(
    *,
    threshold: float,
    k: int | None,
    w: int | None,
    strip_comments: bool | None,
    lang_aware: bool | None,
) -> NormalizeCalibrationAssessment:
    """Compare an effective normalize run with the measured IR-Plag profile."""
    mismatches: list[str] = []
    if k != NORMALIZE_CALIBRATION_K:
        mismatches.append("k")
    if w != NORMALIZE_CALIBRATION_W:
        mismatches.append("w")
    if strip_comments is not NORMALIZE_CALIBRATION_STRIP_COMMENTS:
        mismatches.append("strip_comments")
    if lang_aware is not NORMALIZE_CALIBRATION_LANG_AWARE:
        mismatches.append("lang_aware")

    threshold_matches = threshold == NORMALIZE_DEFAULT_THRESHOLD
    if mismatches:
        status = "unvalidated-profile"
    elif threshold_matches:
        status = "applicable"
    else:
        status = "off-calibration-threshold"
    return NormalizeCalibrationAssessment(
        profile_id=NORMALIZE_CALIBRATION_PROFILE_ID,
        threshold=threshold,
        status=status,
        profile_mismatches=tuple(mismatches),
        threshold_matches=threshold_matches,
    )


def assess_normalize_metadata(
    metadata: NormalizeCalibrationMetadata,
) -> NormalizeCalibrationAssessment:
    """Assess a report metadata object without coupling to its concrete model."""
    return assess_normalize_calibration(
        threshold=metadata.threshold,
        k=metadata.k,
        w=metadata.w,
        strip_comments=metadata.strip_comments,
        lang_aware=metadata.lang_aware,
    )


def resolve_threshold_deep(threshold_deep: float | None, normalize: bool) -> tuple[float, str]:
    """Resolve effective threshold and provenance for CLI and library callers."""
    if threshold_deep is not None:
        return threshold_deep, "user"
    if normalize:
        return NORMALIZE_DEFAULT_THRESHOLD, "normalize-default"
    return RAW_LEGACY_THRESHOLD, "legacy-uncalibrated"


def normalize_disclosure(
    threshold: float,
    provenance: str,
    *,
    assessment: NormalizeCalibrationAssessment | None = None,
) -> str:
    """One-sentence false-positive disclosure for normalize-mode reports.

    Without a stated error rate the inference "Jaccard X% ⇒ copied" does not
    stand, so every normalize report carries this. The measured figure applies
    only at the shipped operating point; if the user set the threshold manually,
    say so rather than quote a rate that no longer holds.
    """
    if assessment is None:
        # Missing effective-profile evidence cannot support a measured claim.
        # Treat every unknown field as a mismatch rather than assuming defaults.
        assessment = assess_normalize_calibration(
            threshold=threshold,
            k=None,
            w=None,
            strip_comments=None,
            lang_aware=None,
        )
    if assessment.threshold != threshold:
        raise ValueError("Calibration assessment threshold does not match disclosure threshold")

    if assessment.status == "unvalidated-profile":
        mismatches = ", ".join(assessment.profile_mismatches)
        threshold_note = (
            f" The effective threshold {threshold:g} also differs from the measured "
            f"threshold {NORMALIZE_DEFAULT_THRESHOLD:g}."
            if not assessment.threshold_matches
            else ""
        )
        return (
            "Normalize (identifier-flattening) inflates false positives on "
            "independent same-domain code. The active fingerprint settings are an "
            f"unvalidated profile for {assessment.profile_id} (mismatch: {mismatches}); "
            "the published false-positive-rate and confidence-interval estimate "
            "does not apply. "
            f"Threshold {threshold:g} and the {INCONCLUSIVE_TOKEN_FLOOR}-token "
            "inconclusive guard remain conservative compatibility behavior, not a "
            "calibrated safety claim for this profile." + threshold_note
        )

    if assessment.status == "off-calibration-threshold":
        setting = "was set manually" if provenance == "user" else "is effective"
        return (
            "Normalize (identifier-flattening) inflates false positives on "
            "independent same-domain code; matches below the "
            f"{INCONCLUSIVE_TOKEN_FLOOR}-token floor are reported as inconclusive. "
            f"Threshold {threshold:g} {setting}; the published false-positive-rate "
            "and confidence-interval estimate applies only at threshold "
            f"{NORMALIZE_DEFAULT_THRESHOLD:g}, so it does not apply to this run."
        )

    base = (
        "Normalize (identifier-flattening) inflates the false-positive rate on "
        "independent same-domain code; matches below the conservative "
        f"{INCONCLUSIVE_TOKEN_FLOOR}-token guard are reported as inconclusive. "
        "The calibration corpus did not measure a separate precision benefit "
        "from that guard."
    )
    lo, hi = NORMALIZE_FP_CI95
    # The honest figure carries the interval and the non-uniform recall: the
    # calibrated threshold flags near-verbatim copies but ~0% of heavily
    # restructured ones, and was measured only on small files.
    measured = (
        f"the measured false-positive rate is {NORMALIZE_FP_RATE_PCT:.2g}% "
        f"(Wilson 95% CI {lo:.2g}–{hi:.2g}%, 1/105 file pairs) on the IR-Plag "
        f"corpus (files ≤{CALIBRATION_MAX_TOKENS} tokens). Recall is non-uniform: "
        f"~{NORMALIZE_RECALL_NEAR_VERBATIM_PCT:.0f}% for near-verbatim copies but "
        "~0% for heavily restructured ones — flagged matches indicate near-verbatim "
        "similarity, not a general copy verdict."
    )
    return (
        base + " At the shipped operating point (threshold "
        f"{NORMALIZE_DEFAULT_THRESHOLD:.0f}, calibrated for false-positive "
        f"≤ 1%), {measured}"
    )


def threshold_disclosure(
    threshold: float,
    provenance: str,
    normalize: bool,
    *,
    assessment: NormalizeCalibrationAssessment | None = None,
) -> str:
    """Canonical threshold disclosure for every deep fingerprint channel."""
    if normalize:
        return normalize_disclosure(
            threshold,
            provenance,
            assessment=assessment,
        )
    if provenance == "legacy-uncalibrated" and threshold == RAW_LEGACY_THRESHOLD:
        return (
            "Raw threshold 5 is the historical compatibility default and is not "
            "a calibrated safety threshold. Low-threshold results are similarity "
            "candidates for manual review, not legal copying determinations."
        )
    return (
        f"Raw threshold {threshold:g} was set manually. No calibrated false-positive "
        "estimate applies; results are similarity candidates for manual review, not "
        "legal copying determinations."
    )
