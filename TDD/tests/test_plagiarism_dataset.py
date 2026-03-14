"""Plagiarism dataset cross-validation test harness.

Tests Diffinite's multi-channel evidence scoring against the
IR-Plag-Dataset, measuring TPR, FPR, and F1-Score.

Uses the tuned academic profile parameters:
  K=2, W=3, threshold=0.40
  Weights: raw_winnowing=3.0, normalized_winnowing=1.0, others=0.0
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import compute_channel_scores, _ACADEMIC_WEIGHTS

DATASET_ROOT = PROJECT_ROOT / "example" / "plagiarism"
CASES = sorted(p.name for p in DATASET_ROOT.iterdir() if p.is_dir())
LEVELS = [f"L{i}" for i in range(1, 7)]

DATA_EXISTS = DATASET_ROOT.is_dir() and any(DATASET_ROOT.iterdir())

pytestmark = pytest.mark.skipif(
    not DATA_EXISTS,
    reason="IR-Plag-Dataset not found",
)

# Academic profile parameters (tuned via grid search)
ACADEMIC_K = 2
ACADEMIC_W = 3
ACADEMIC_THRESHOLD = 0.40
ACADEMIC_WEIGHTS = _ACADEMIC_WEIGHTS


# ── Helpers ──────────────────────────────────────────────────────────

def read_java(path: Path) -> str | None:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def fingerprint(text: str, k: int = ACADEMIC_K, w: int = ACADEMIC_W) -> dict:
    cleaned = strip_comments(text, ".java")
    fp_raw = extract_fingerprints(
        cleaned, k=k, w=w, normalize=False, mode="token", extension=".java",
    )
    fp_norm = extract_fingerprints(
        cleaned, k=k, w=w, normalize=True, mode="token", extension=".java",
    )
    return {
        "raw": {fp.hash_value for fp in fp_raw},
        "normalized": {fp.hash_value for fp in fp_norm},
        "text": text,
        "cleaned": cleaned,
    }


def similarity(fp_a: dict, fp_b: dict) -> float:
    scores = compute_channel_scores(
        fp_raw_a=fp_a["raw"], fp_raw_b=fp_b["raw"],
        fp_norm_a=fp_a["normalized"], fp_norm_b=fp_b["normalized"],
        source_a=fp_a["text"], source_b=fp_b["text"],
        cleaned_a=fp_a["cleaned"], cleaned_b=fp_b["cleaned"],
        extension=".java",
        weights=ACADEMIC_WEIGHTS,
    )
    return scores.get("composite", 0.0)


# ── Data collection ──────────────────────────────────────────────────

def _collect_all_scores():
    """Collect positive (plagiarized) and negative (non-plagiarized) scores."""
    pos_scores: dict[str, list[float]] = defaultdict(list)
    neg_scores: list[float] = []

    for case_name in CASES:
        case_dir = DATASET_ROOT / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = read_java(orig_files[0])
        if not orig_text:
            continue
        orig_fp = fingerprint(orig_text)

        # Plagiarized (1:N cross-matching)
        for level in LEVELS:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = read_java(jf)
                if text:
                    score = similarity(orig_fp, fingerprint(text))
                    pos_scores[level].append(score)

        # Non-plagiarized (FPR measurement)
        non_plag_dir = case_dir / "non-plagiarized"
        for jf in sorted(non_plag_dir.rglob("*.java")):
            text = read_java(jf)
            if text:
                score = similarity(orig_fp, fingerprint(text))
                neg_scores.append(score)

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


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def academic_metrics():
    """Compute academic-profile metrics once for the module."""
    pos_scores, neg_scores = _collect_all_scores()
    metrics = _compute_metrics(pos_scores, neg_scores, ACADEMIC_THRESHOLD)
    return metrics


# ── Tests ────────────────────────────────────────────────────────────

class TestPlagiarismTPR:
    """True-positive rate per plagiarism level (academic profile)."""

    @pytest.mark.parametrize("level,min_tpr", [
        ("L1", 0.90),
        ("L2", 0.90),
        ("L3", 0.90),
        ("L4", 0.90),
        ("L5", 0.70),
        ("L6", 0.50),
    ])
    def test_level_tpr(self, academic_metrics, level, min_tpr):
        tpr = academic_metrics["level_tpr"].get(level, 0.0)
        assert tpr >= min_tpr, (
            f"{level}: TPR={tpr:.4f} < {min_tpr} "
            f"(K={ACADEMIC_K}, W={ACADEMIC_W}, T={ACADEMIC_THRESHOLD})"
        )


class TestPlagiarismAggregates:
    """Aggregate F1-Score and recall checks."""

    def test_f1_above_target(self, academic_metrics):
        f1 = academic_metrics["f1"]
        assert f1 >= 0.85, (
            f"F1={f1:.4f} < 0.85 "
            f"(P={academic_metrics['precision']:.4f}, R={academic_metrics['recall']:.4f})"
        )

    def test_recall_above_minimum(self, academic_metrics):
        recall = academic_metrics["recall"]
        assert recall >= 0.90, f"Recall={recall:.4f} < 0.90"

    def test_precision_improved(self, academic_metrics):
        precision = academic_metrics["precision"]
        # Must be better than baseline industrial precision (0.7717)
        assert precision > 0.77, f"Precision={precision:.4f} ≤ 0.77 (baseline)"
