"""Regression guard for the WS-A normalize error-rate harness.

Fast smoke test (one IR-Plag case) that (a) exercises the harness end to end and
(b) locks in the measured phenomenon the harness exists to expose: identifier
flattening (``--normalize``) inflates the false-positive rate on independent,
same-domain code. If a future change ever makes normalize *not* worse on
precision than raw, that is either a real improvement worth re-baselining or a
broken measurement — either way this test should fail and force a look.
"""

import pytest

from tests.validation import error_rate as er

_CASE = er.CORPUS_ROOT / "case-01"
pytestmark = pytest.mark.skipif(
    not _CASE.is_dir(), reason="IR-Plag corpus (example/plagiarism) not present"
)


@pytest.fixture(scope="module")
def scores():
    s = er.score_case(_CASE)
    assert s, "harness produced no scores for case-01"
    return s


def test_corpus_has_both_labels(scores):
    assert any(s.label == "pos" for s in scores)
    assert any(s.label == "neg" for s in scores)
    # Both normalization modes are scored for every pair.
    assert {s.mode for s in scores} == {"raw", "normalize"}


def test_recall_saturated_at_low_threshold(scores):
    # Sanity: at threshold 5 every labelled copy is detected in both modes.
    assert er._rate(er.recall(scores, "normalize", 5)) == 100.0
    assert er._rate(er.recall(scores, "raw", 5)) == 100.0


def test_normalize_inflates_false_positives(scores):
    """The collapse signature: integrated over all thresholds, normalize's
    false-positive rate on independent submissions is >= raw's, and strictly
    greater somewhere (it never *helps* precision on independent code)."""
    raw_auc = sum(er._rate(er.fp_rate(scores, "raw", t)) for t in range(101))
    norm_auc = sum(er._rate(er.fp_rate(scores, "normalize", t)) for t in range(101))
    assert norm_auc >= raw_auc
    assert norm_auc > raw_auc, (
        "normalize was not worse than raw on independent code anywhere — "
        "the false-positive phenomenon disappeared; re-baseline or investigate"
    )


def test_sweep_rows_shape(scores):
    rows = er.sweep_rows(scores)
    assert len(rows) == 2 * 101  # two modes x thresholds 0..100
    assert {"mode", "threshold", "fp_rate", "recall_all"} <= set(rows[0].keys())
