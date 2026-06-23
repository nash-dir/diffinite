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
# Per-test (not module-level): the calibrate() logic tests below are synthetic and
# must run even when the downloaded corpus is absent (e.g. in CI).
requires_corpus = pytest.mark.skipif(
    not _CASE.is_dir(), reason="IR-Plag corpus (example/plagiarism) not present"
)


@pytest.fixture(scope="module")
def scores():
    s = er.score_case(_CASE)
    assert s, "harness produced no scores for case-01"
    return s


def _synthetic_scores():
    """A controlled score set with a known calibration frontier: 8 large
    low-similarity negatives, 2 small high-similarity negatives, 10 large
    high-similarity positives. The only way to reach FP=0 while keeping recall is
    to set the floor above the small negatives — so `recommended` must pick it."""
    S = er.PairScore
    out = []
    for i in range(8):
        out.append(S(case="c", mode="normalize", label="neg", level=None,
                     jaccard=0.10, tokens_min=100))
    for i in range(2):
        out.append(S(case="c", mode="normalize", label="neg", level=None,
                     jaccard=0.90, tokens_min=20))
    for i in range(10):
        out.append(S(case="c", mode="normalize", label="pos", level=1,
                     jaccard=0.80, tokens_min=100))
    return out


def test_calibrate_recommended_picks_floor_excluding_small_negatives():
    # Exercises the `recommended` selection (max recall with >=50% coverage) that
    # the corpus smoke test left as dead code (empty frontier on case-01).
    frontier, rec = er.calibrate(_synthetic_scores(), fp_target=0.0, min_coverage=0.5)
    assert frontier
    assert rec is not None
    assert rec.fp_rate == 0.0            # target met
    assert rec.floor > 20               # floor excludes the small high-sim negatives
    assert rec.recall == 100.0          # ...so all positives survive
    assert rec.coverage >= 0.5


@requires_corpus
def test_corpus_has_both_labels(scores):
    assert any(s.label == "pos" for s in scores)
    assert any(s.label == "neg" for s in scores)
    # Both normalization modes are scored for every pair.
    assert {s.mode for s in scores} == {"raw", "normalize"}


@requires_corpus
def test_recall_saturated_at_low_threshold(scores):
    # Sanity: at threshold 5 every labelled copy is detected in both modes.
    assert er._rate(er.recall(scores, "normalize", 5)) == 100.0
    assert er._rate(er.recall(scores, "raw", 5)) == 100.0


@requires_corpus
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


@requires_corpus
def test_sweep_rows_shape(scores):
    rows = er.sweep_rows(scores)
    assert len(rows) == 2 * 101  # two modes x thresholds 0..100
    assert {"mode", "threshold", "fp_rate", "recall_all"} <= set(rows[0].keys())


@requires_corpus
def test_calibrate_frontier_invariants(scores):
    # A single small case may admit no FP<=5% point, but the invariants must hold
    # for whatever frontier is produced.
    frontier, rec = er.calibrate(scores, fp_target=5.0)
    assert isinstance(frontier, list)
    assert all(p.fp_rate <= 5.0 + 1e-9 for p in frontier)  # met by construction
    covs = [p.coverage for p in frontier]
    assert covs == sorted(covs, reverse=True)  # coverage falls as floor rises
    if rec is not None:
        assert rec.fp_rate <= 5.0 + 1e-9
        assert rec.coverage >= 0.5
        assert rec.floor > 0


@requires_corpus
def test_calibrate_lenient_target_is_reachable(scores):
    # At a forgiving FP target some operating point always exists.
    frontier, _ = er.calibrate(scores, fp_target=50.0)
    assert frontier
    assert all(p.fp_rate <= 50.0 + 1e-9 for p in frontier)
