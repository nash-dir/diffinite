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

from collections.abc import Iterable
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

# Recall at the operating point for each of the restructured levels L4, L5 and L6
# (example/validation/calibration.json, fp_le_1.recall_by_level: 0.0 for each).
NORMALIZE_RECALL_RESTRUCTURED_PCT: float = 0.0

# Largest SMALLER-file size (tokens, min over each pair) among calibration pairs
# (max tokens_min, tests/validation/error_rate.py). The operating point is
# unvalidated for pairs whose files both exceed this. Disclosed, not enforced:
# assess_normalize_calibration does not check input size.
CALIBRATION_MAX_TOKENS: int = 212

# Largest single file (tokens, strip_comments + tokenize(normalize=False)) among
# the 467 IR-Plag files — the per-file counterpart of CALIBRATION_MAX_TOKENS.
CALIBRATION_MAX_FILE_TOKENS: int = 307

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
    """Whether one effective run matches the measured fingerprint profile and threshold.

    Language and file size are not assessed; see ``assess_normalize_calibration``.
    """

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
    comment_unstripped_extensions: Iterable[str] = (),
) -> NormalizeCalibrationAssessment:
    """Compare an effective normalize run with the measured IR-Plag profile.

    ``applicable`` means only that the fingerprint execution profile (K, W,
    comment stripping, lang-aware) and the threshold match the measured point.
    ``comment_unstripped_extensions`` lists Deep Compare input extensions with no
    registered comment syntax, whose comments were kept despite
    ``--strip-comments``. Any such extension means comments were not stripped as
    in the measured profile, so ``strip_comments`` is reported as a mismatch.
    Input language and file size are **not** checked: the calibration measured
    only small Java files, and those limits are carried by the disclosure text
    (``normalize_disclosure``), not by this status.
    """
    mismatches: list[str] = []
    if k != NORMALIZE_CALIBRATION_K:
        mismatches.append("k")
    if w != NORMALIZE_CALIBRATION_W:
        mismatches.append("w")
    if strip_comments is not NORMALIZE_CALIBRATION_STRIP_COMMENTS or (
        strip_comments and tuple(comment_unstripped_extensions)
    ):
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
        comment_unstripped_extensions=getattr(metadata, "deep_comment_unstripped_extensions", ()),
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

    # The inconclusive-match rule is stated once, under the Deep Compare table
    # and only when a row is marked (notices.INCONCLUSIVE_NOTICE), not here.
    lead = (
        "Normalization replaces identifiers and literals "
        "before fingerprinting, which raises the similarity of independently "
        "written code in the same domain."
    )

    if assessment.status == "unvalidated-profile":
        mismatches = ", ".join(
            _PROFILE_FIELD_LABELS.get(name, name) for name in assessment.profile_mismatches
        )
        threshold_note = (
            f" The threshold of {threshold:g}% also differs from the measured "
            f"threshold of {NORMALIZE_DEFAULT_THRESHOLD:g}%."
            if not assessment.threshold_matches
            else ""
        )
        return (
            lead + " The settings of this run differ from the measured profile "
            f"{assessment.profile_id} ({mismatches}). This is an unvalidated "
            "profile, and the measured false-positive rate does not apply." + threshold_note
        )

    if assessment.status == "off-calibration-threshold":
        setting = "was set manually" if provenance == "user" else "is in effect"
        return (
            lead + f" The threshold of {threshold:g}% {setting}. The measured "
            "false-positive rate applies only at the default threshold of "
            f"{NORMALIZE_DEFAULT_THRESHOLD:g}% and does not apply to this run."
        )

    lo, hi = NORMALIZE_FP_CI95
    return (
        lead + f" The default threshold of {NORMALIZE_DEFAULT_THRESHOLD:.0f}% was set "
        "using the IR-Plag Java corpus, where its false-positive rate was "
        f"{NORMALIZE_FP_RATE_PCT:.2g}% (1 of 105 independent file pairs; Wilson 95% "
        f"CI {lo:.2g}% to {hi:.2g}%). That false positive scored 100%. The pairs "
        "come from 7 assignments, so the true uncertainty is wider than this "
        "interval. In the measured pairs the smaller file had "
        f"{CALIBRATION_MAX_TOKENS} tokens or fewer (largest file "
        f"{CALIBRATION_MAX_FILE_TOKENS} tokens). Other languages and larger files "
        "were not measured, and the languages and file sizes of this run were not "
        "checked against that scope. At this threshold "
        f"{NORMALIZE_RECALL_NEAR_VERBATIM_PCT:.0f}% of near-verbatim copies (level L1) "
        f"and {NORMALIZE_RECALL_RESTRUCTURED_PCT:.0f}% of heavily restructured copies "
        "(levels L4 to L6) were detected."
    )


# Plain names for the profile fields named in the disclosure.
_PROFILE_FIELD_LABELS: dict[str, str] = {
    "k": "K-gram size",
    "w": "window size",
    "strip_comments": "comment stripping",
    "lang_aware": "language-aware tokenization",
}


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
            "Deep Compare lists file pairs whose Jaccard similarity is at least "
            f"{threshold:g}%, the default threshold. No false-positive rate has "
            "been measured for this threshold."
        )
    return (
        f"Deep Compare lists file pairs whose Jaccard similarity is at least "
        f"{threshold:g}%, a threshold set manually. No false-positive rate has "
        "been measured for this threshold."
    )


def threshold_console_warning(
    assessment: NormalizeCalibrationAssessment | None,
    threshold: float,
    provenance: str,
    *,
    comment_unstripped_extensions: Iterable[str] = (),
) -> str | None:
    """One console warning for a deep run, in the wording of the report notice.

    ``assessment`` is None for a raw (non-normalize) run. Returns None when the
    run is at the measured operating point and needs no warning.
    """
    if assessment is None:
        if provenance == "legacy-uncalibrated" and threshold == RAW_LEGACY_THRESHOLD:
            return (
                f"Deep Compare uses the default threshold of {threshold:g}%. No "
                "false-positive rate has been measured for this threshold."
            )
        return None
    if assessment.status == "unvalidated-profile":
        labels = []
        exts = sorted({e if e else "(no extension)" for e in comment_unstripped_extensions})
        for name in assessment.profile_mismatches:
            label = _PROFILE_FIELD_LABELS.get(name, name)
            if name == "strip_comments" and exts:
                label += " (comments kept in " + ", ".join(exts) + " files)"
            labels.append(label)
        return (
            "Normalized comparison: the settings of this run differ from the "
            f"measured profile ({'; '.join(labels)}). This is an unvalidated "
            "profile, and the measured false-positive rate does not apply to this run."
        )
    if assessment.status == "off-calibration-threshold":
        return (
            f"Normalized comparison: the threshold of {threshold:g}% differs from "
            f"the default threshold of {NORMALIZE_DEFAULT_THRESHOLD:g}%. The measured "
            "false-positive rate does not apply to this run."
        )
    return None
