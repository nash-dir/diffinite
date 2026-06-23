"""Tests for the ratified normalize operating point and its disclosure text."""

from diffinite.calibration import (
    INCONCLUSIVE_TOKEN_FLOOR,
    NORMALIZE_DEFAULT_THRESHOLD,
    NORMALIZE_FP_CI95,
    NORMALIZE_FP_RATE_PCT,
    normalize_disclosure,
)


def test_constants_in_sane_ranges():
    assert 0 < NORMALIZE_DEFAULT_THRESHOLD <= 100
    assert INCONCLUSIVE_TOKEN_FLOOR > 0
    assert 0 <= NORMALIZE_FP_RATE_PCT <= 100


def test_disclosure_cites_measured_fp_at_shipped_point():
    s = normalize_disclosure(NORMALIZE_DEFAULT_THRESHOLD, "normalize-default")
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" in s          # the measured rate, exact
    assert "inconclusive" in s.lower()
    assert str(INCONCLUSIVE_TOKEN_FLOOR) in s


def test_disclosure_carries_confidence_interval_and_recall_caveat():
    # Daubert: the rate must come with its interval, and recall must not be
    # presented as uniform when it collapses on restructured copies.
    s = normalize_disclosure(NORMALIZE_DEFAULT_THRESHOLD, "normalize-default")
    lo, hi = NORMALIZE_FP_CI95
    assert f"{lo:.2g}" in s and f"{hi:.2g}" in s        # CI present
    assert "ci" in s.lower()
    assert "non-uniform" in s.lower() or "near-verbatim" in s.lower()


def test_disclosure_warns_when_threshold_set_manually():
    # An OFF-calibration user threshold invalidates the calibrated FP figure.
    s = normalize_disclosure(50.0, "user")
    assert "manual" in s.lower()
    assert "does not apply" in s.lower()


def test_disclosure_applies_when_user_sets_threshold_equal_to_default():
    # B5 fix: passing exactly the calibrated threshold must NOT say "does not
    # apply" — the calibrated figure is valid at its own operating point.
    s = normalize_disclosure(NORMALIZE_DEFAULT_THRESHOLD, "user")
    assert "does not apply" not in s.lower()
    assert f"{NORMALIZE_FP_RATE_PCT:.2g}%" in s
