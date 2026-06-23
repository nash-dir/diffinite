"""Ratified operating point for the ``--normalize`` fingerprint channel.

Single source of truth for the normalize-mode threshold and the inconclusive
token floor. These are **not** guessed: they were derived by the validation
harness (``tests/validation/error_rate.py``) on the Karnalim IR-Plag corpus and
ratified by the maintainer at the **false-positive ≤ 1%** operating point.

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

# Minimum Jaccard (0–100 scale) to report a match under --normalize, when the
# user does not override --threshold-deep. Derived for false-positive ≤ 1%.
NORMALIZE_DEFAULT_THRESHOLD: float = 93.0

# Below this token count (the smaller of the two files in a pair), a --normalize
# match is reported as INCONCLUSIVE rather than as a confident similarity:
# precision is unsalvageable at any useful threshold for files this small.
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


def normalize_disclosure(threshold: float, provenance: str) -> str:
    """One-sentence false-positive disclosure for normalize-mode reports.

    Without a stated error rate the inference "Jaccard X% ⇒ copied" does not
    stand, so every normalize report carries this. The measured figure applies
    only at the shipped operating point; if the user set the threshold manually,
    say so rather than quote a rate that no longer holds.
    """
    base = (
        "Normalize (identifier-flattening) inflates the false-positive rate on "
        "independent same-domain code; matches below the "
        f"{INCONCLUSIVE_TOKEN_FLOOR}-token floor are reported as inconclusive."
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
    # When the user passes exactly the calibrated threshold, the calibrated figure
    # DOES apply; only an off-calibration manual threshold invalidates it.
    if provenance == "normalize-default" or threshold == NORMALIZE_DEFAULT_THRESHOLD:
        return (
            base + " At the shipped operating point (threshold "
            f"{NORMALIZE_DEFAULT_THRESHOLD:.0f}, calibrated for false-positive "
            f"≤ 1%), {measured}"
        )
    return (
        base + f" Threshold {threshold:.0f} was set manually; the calibrated "
        f"false-positive figure ({NORMALIZE_FP_RATE_PCT:.2g}%, CI {lo:.2g}–{hi:.2g}%, "
        f"at threshold {NORMALIZE_DEFAULT_THRESHOLD:.0f}) does not apply at this "
        "threshold."
    )
