"""Tests for the ratified normalize operating point and its disclosure text."""

from diffinite.calibration import (
    INCONCLUSIVE_TOKEN_FLOOR,
    NORMALIZE_DEFAULT_THRESHOLD,
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


def test_disclosure_warns_when_threshold_set_manually():
    # A user-set threshold invalidates the calibrated FP figure; say so.
    s = normalize_disclosure(50.0, "user")
    assert "manual" in s.lower()
    assert "does not apply" in s.lower()
