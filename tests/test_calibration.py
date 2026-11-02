"""Tests for the ratified normalize operating point and its disclosure text."""

import pytest

from diffinite.calibration import (
    INCONCLUSIVE_TOKEN_FLOOR,
    NORMALIZE_CALIBRATION_K,
    NORMALIZE_CALIBRATION_LANG_AWARE,
    NORMALIZE_CALIBRATION_STRIP_COMMENTS,
    NORMALIZE_CALIBRATION_W,
    NORMALIZE_DEFAULT_THRESHOLD,
    NORMALIZE_FP_CI95,
    NORMALIZE_FP_RATE_PCT,
    assess_normalize_calibration,
    normalize_disclosure,
)


def _validated_assessment(threshold=NORMALIZE_DEFAULT_THRESHOLD):
    return assess_normalize_calibration(
        threshold=threshold,
        k=NORMALIZE_CALIBRATION_K,
        w=NORMALIZE_CALIBRATION_W,
        strip_comments=NORMALIZE_CALIBRATION_STRIP_COMMENTS,
        lang_aware=NORMALIZE_CALIBRATION_LANG_AWARE,
    )


def test_constants_in_sane_ranges():
    assert 0 < NORMALIZE_DEFAULT_THRESHOLD <= 100
    assert INCONCLUSIVE_TOKEN_FLOOR > 0
    assert 0 <= NORMALIZE_FP_RATE_PCT <= 100


def test_disclosure_cites_measured_fp_at_shipped_point():
    s = normalize_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
        assessment=_validated_assessment(),
    )
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" in s          # the measured rate, exact
    assert "inconclusive" in s.lower()
    assert str(INCONCLUSIVE_TOKEN_FLOOR) in s


def test_disclosure_carries_confidence_interval_and_recall_caveat():
    # Daubert: the rate must come with its interval, and recall must not be
    # presented as uniform when it collapses on restructured copies.
    s = normalize_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
        assessment=_validated_assessment(),
    )
    lo, hi = NORMALIZE_FP_CI95
    assert f"{lo:.2g}" in s and f"{hi:.2g}" in s        # CI present
    assert "ci" in s.lower()
    assert "non-uniform" in s.lower() or "near-verbatim" in s.lower()


def test_disclosure_warns_when_threshold_set_manually():
    # An OFF-calibration user threshold invalidates the calibrated FP figure.
    assessment = _validated_assessment(50.0)
    s = normalize_disclosure(50.0, "user", assessment=assessment)
    assert "manual" in s.lower()
    assert "does not apply" in s.lower()
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" not in s


def test_disclosure_applies_when_user_sets_threshold_equal_to_default():
    # B5 fix: passing exactly the calibrated threshold must NOT say "does not
    # apply" — the calibrated figure is valid at its own operating point.
    s = normalize_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "user",
        assessment=_validated_assessment(),
    )
    assert "does not apply" not in s.lower()
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" in s


def test_missing_profile_assessment_fails_closed_without_measured_rate():
    disclosure = normalize_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
    )

    assert "unvalidated profile" in disclosure.lower()
    assert "does not apply" in disclosure.lower()
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" not in disclosure
    assert "wilson 95% ci" not in disclosure.lower()


@pytest.mark.parametrize(
    ("override", "mismatch"),
    [
        ({"k": NORMALIZE_CALIBRATION_K + 1}, "k"),
        ({"w": NORMALIZE_CALIBRATION_W + 1}, "w"),
        ({"strip_comments": not NORMALIZE_CALIBRATION_STRIP_COMMENTS}, "strip_comments"),
        ({"lang_aware": not NORMALIZE_CALIBRATION_LANG_AWARE}, "lang_aware"),
    ],
)
def test_measured_rate_is_withheld_for_unvalidated_profiles(override, mismatch):
    profile = {
        "k": NORMALIZE_CALIBRATION_K,
        "w": NORMALIZE_CALIBRATION_W,
        "strip_comments": NORMALIZE_CALIBRATION_STRIP_COMMENTS,
        "lang_aware": NORMALIZE_CALIBRATION_LANG_AWARE,
    }
    profile.update(override)
    assessment = assess_normalize_calibration(
        threshold=NORMALIZE_DEFAULT_THRESHOLD,
        **profile,
    )
    disclosure = normalize_disclosure(
        NORMALIZE_DEFAULT_THRESHOLD,
        "normalize-default",
        assessment=assessment,
    )

    assert assessment.status == "unvalidated-profile"
    assert mismatch in assessment.profile_mismatches
    assert "unvalidated profile" in disclosure.lower()
    assert "does not apply" in disclosure.lower()
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" not in disclosure
    assert "wilson 95% ci" not in disclosure.lower()
