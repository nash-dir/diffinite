"""Plagiarism dataset cross-validation test harness.

Tests Diffinite's Winnowing fingerprinting against the IR-Plag-Dataset
(Faidhi-Robinson L1–L6 levels), measuring TPR, FPR, and F1-Score.

Parameters: K=2, W=3, threshold=0.40
"""

from __future__ import annotations

from pathlib import Path
from collections import defaultdict

import pytest

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import jaccard_similarity

# ---------------------------------------------------------------------------
# Dataset paths & constants
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATASET_ROOT = _PROJECT_ROOT / "example" / "plagiarism"
_CASES = sorted(p.name for p in _DATASET_ROOT.iterdir() if p.is_dir()) if _DATASET_ROOT.is_dir() else []
_LEVELS = [f"L{i}" for i in range(1, 7)]
_DATA_EXISTS = _DATASET_ROOT.is_dir() and len(_CASES) > 0

# Parameters
PLAG_K = 2
PLAG_W = 3
PLAG_THRESHOLD = 0.40

pytestmark = pytest.mark.skipif(
    not _DATA_EXISTS,
    reason="IR-Plag-Dataset not found at example/plagiarism/",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_java(path: Path) -> str | None:
    """Read a Java source file with encoding fallback."""
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _fingerprint(text: str, k: int = PLAG_K, w: int = PLAG_W) -> set[int]:
    """Extract Winnowing fingerprints for a single source text."""
    cleaned = strip_comments(text, ".java")
    fps = extract_fingerprints(
        cleaned, k=k, w=w, normalize=False, mode="token", extension=".java",
    )
    return {fp.hash_value for fp in fps}


def _similarity(fp_a: set[int], fp_b: set[int]) -> float:
    """Compute Jaccard similarity."""
    return jaccard_similarity(fp_a, fp_b)


# ---------------------------------------------------------------------------
# Data collection & metrics
# ---------------------------------------------------------------------------
def _collect_all_scores():
    """Collect positive (plagiarized) and negative (non-plagiarized) scores."""
    pos_scores: dict[str, list[float]] = defaultdict(list)
    neg_scores: list[float] = []

    for case_name in _CASES:
        case_dir = _DATASET_ROOT / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = _read_java(orig_files[0])
        if not orig_text:
            continue
        orig_fp = _fingerprint(orig_text)

        # Plagiarized (1:N cross-matching per level)
        for level in _LEVELS:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = _read_java(jf)
                if text:
                    pos_scores[level].append(
                        _similarity(orig_fp, _fingerprint(text)),
                    )

        # Non-plagiarized (FPR measurement)
        non_plag_dir = case_dir / "non-plagiarized"
        for jf in sorted(non_plag_dir.rglob("*.java")):
            text = _read_java(jf)
            if text:
                neg_scores.append(
                    _similarity(orig_fp, _fingerprint(text)),
                )

    return pos_scores, neg_scores


def _compute_metrics(pos_scores, neg_scores, threshold):
    """Compute TPR per level, FPR, Precision, Recall, F1."""
    level_tpr = {}
    total_tp = 0
    total_fn = 0

    for level, scores in pos_scores.items():
        tp = sum(1 for s in scores if s >= threshold)
        fn = len(scores) - tp
        total_tp += tp
        total_fn += fn
        level_tpr[level] = tp / len(scores) if scores else 0.0

    fp = sum(1 for s in neg_scores if s >= threshold)
    tn = len(neg_scores) - fp
    fpr = fp / len(neg_scores) if neg_scores else 0.0

    precision = total_tp / (total_tp + fp) if (total_tp + fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "level_tpr": level_tpr,
        "fpr": fpr,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": total_tp,
        "fn": total_fn,
        "fp": fp,
        "tn": tn,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def plag_metrics():
    """Compute metrics once for the module."""
    pos_scores, neg_scores = _collect_all_scores()
    return _compute_metrics(pos_scores, neg_scores, PLAG_THRESHOLD)


# ---------------------------------------------------------------------------
# Tests — TPR per plagiarism level
# ---------------------------------------------------------------------------
class TestPlagiarismTPR:
    """True-positive rate per plagiarism level.

    Target TPRs reflect difficulty: L1–L4 (surface changes) ≥ 90%,
    L5 (control-flow) ≥ 70%, L6 (logic restructuring) ≥ 50%.
    """

    @pytest.mark.parametrize("level,min_tpr", [
        ("L1", 0.90),
        ("L2", 0.90),
        ("L3", 0.90),
        ("L4", 0.90),
        ("L5", 0.70),
        ("L6", 0.50),
    ])
    def test_level_tpr(self, plag_metrics, level, min_tpr):
        tpr = plag_metrics["level_tpr"].get(level, 0.0)
        assert tpr >= min_tpr, (
            f"{level}: TPR={tpr:.4f} < {min_tpr} "
            f"(K={PLAG_K}, W={PLAG_W}, T={PLAG_THRESHOLD})"
        )


# ---------------------------------------------------------------------------
# Tests — Aggregate metrics
# ---------------------------------------------------------------------------
class TestPlagiarismAggregates:
    """Aggregate F1-Score, recall, and precision checks."""

    def test_f1_above_target(self, plag_metrics):
        f1 = plag_metrics["f1"]
        assert f1 >= 0.85, (
            f"F1={f1:.4f} < 0.85 "
            f"(P={plag_metrics['precision']:.4f}, "
            f"R={plag_metrics['recall']:.4f})"
        )

    def test_recall_above_minimum(self, plag_metrics):
        recall = plag_metrics["recall"]
        assert recall >= 0.90, f"Recall={recall:.4f} < 0.90"

    def test_precision_improved(self, plag_metrics):
        precision = plag_metrics["precision"]
        assert precision > 0.77, (
            f"Precision={precision:.4f} ≤ 0.77 (baseline)"
        )
