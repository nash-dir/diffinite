"""CLI numeric input-range validation.

Degenerate values must be rejected at the argument boundary (exit code 2)
rather than crashing mid-run after the rendering phase, or — worse —
silently fabricating forensic numbers (e.g. --k-gram 0 collapses every file
to a single fingerprint and reports 100% similarity for unrelated files).
"""

import pytest

from diffinite.cli import main


@pytest.mark.parametrize("token", [
    "--k-gram=0",
    "--window=0",
    "--workers=0",
    "--max-index-entries=0",
    "--threshold=150",
    "--threshold=-1",
    "--threshold-deep=200",
    "--threshold-deep=-5",
    "--bates-start=0",
    "--bates-start=-3",
])
def test_out_of_range_rejected(token):
    with pytest.raises(SystemExit) as exc:
        main(["a", "b", token])
    assert exc.value.code == 2


def test_valid_boundaries_accepted(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    # Boundary-valid values must run without error (empty dirs → empty report).
    main([
        str(a), str(b), "-o", str(tmp_path / "out.pdf"),
        "--k-gram=1", "--window=1", "--workers=1",
        "--threshold=0", "--threshold-deep=100", "--bates-start=1",
    ])


class TestThresholdProvenance:
    """The deep threshold default must differ by channel: raw keeps 5%, normalize
    substitutes the ratified calibration default (false-positive <= 1%)."""

    def test_raw_default(self):
        from diffinite.cli import _resolve_threshold_deep
        assert _resolve_threshold_deep(None, normalize=False) == (5.0, "default")

    def test_normalize_default_substituted(self):
        from diffinite.cli import _resolve_threshold_deep
        from diffinite.calibration import NORMALIZE_DEFAULT_THRESHOLD
        val, prov = _resolve_threshold_deep(None, normalize=True)
        assert val == NORMALIZE_DEFAULT_THRESHOLD
        assert prov == "normalize-default"

    def test_explicit_value_wins_in_both_channels(self):
        from diffinite.cli import _resolve_threshold_deep
        assert _resolve_threshold_deep(12.0, normalize=False) == (12.0, "user")
        assert _resolve_threshold_deep(12.0, normalize=True) == (12.0, "user")
