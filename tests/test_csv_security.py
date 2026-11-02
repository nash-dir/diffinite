"""Security boundaries for spreadsheet-compatible evidence indexes."""

import pytest

from diffinite.pipeline import _csv_safe_cell


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("https://example.invalid")', '\'=HYPERLINK("https://example.invalid")'),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-1+2", "'-1+2"),
        ("@SUM(1,2)", "'@SUM(1,2)"),
        ("  =1+1", "'  =1+1"),
        ("\t=1+1", "'\t=1+1"),
    ],
)
def test_csv_formula_payloads_are_forced_to_text(value, expected):
    assert _csv_safe_cell(value) == expected


@pytest.mark.parametrize("value", ["ordinary.py", "한글.java", "1 - 3", 7, 99.5, ""])
def test_csv_safe_values_are_unchanged(value):
    assert _csv_safe_cell(value) == value
