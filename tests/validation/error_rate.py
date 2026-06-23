"""Normalize-mode precision/recall measurement harness (WS-A) — the keystone.

Fills the *measured methodological validation* gap. The fingerprint engine's
recall (it catches renamed/restructured plagiarism) was demonstrated, but the
**false-positive rate of ``--normalize`` on independent same-domain code was
never measured**, and the default ``--threshold-deep 5`` was only ever validated
against the *non-normalize* negative control. Without an error rate, the
inference "Jaccard X% ⇒ copied" does not stand (a Daubert-style gap, not a
coding defect). This harness produces that number.

Corpus — Karnalim IR-Plag (``example/plagiarism``). Each ``case-NN/`` is one
programming assignment with three labelled groups:

  * ``original/``            — the reference solution
  * ``plagiarized/L1..L6/*`` — obfuscated copies of ``original`` (L1 verbatim
                               → L6 heavily restructured) → **POSITIVES** (recall)
  * ``non-plagiarized/*``    — *different students'* independent solutions to the
                               **same** assignment → **NEGATIVES** (precision)

Independence claim (the evidentiary load-bearing assumption): a non-plagiarized
submission is an independent answer to the identical task, so any similarity it
shows to ``original`` is, by construction, a false positive. This makes the
non-plagiarized group a same-domain, naturally small-file negative set — exactly
the regime where identifier flattening collapses distinct authors onto identical
fingerprints.

What it computes, for each mode (``raw`` vs ``normalize``):
  * false-positive rate on the negative set, swept across thresholds 0–100,
    stratified by submission token count;
  * recall on the positive set, per obfuscation level, swept across thresholds.

Outputs (committed as reproducible evidence; fingerprints are deterministic):
  * ``example/validation/pr_curve.csv``  — full sweep, machine-readable
  * ``example/validation/error_rate.md`` — headline false-positive sentences +
    per-level recall, the one-paragraph answer a report can cite.

This module does **not** choose an operating threshold — that is a
forensic-defensibility decision (WS-B) ratified by the maintainer from these
curves, never guessed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from diffinite.differ import read_file
from diffinite.evidence import jaccard_similarity
from diffinite.fingerprint import extract_fingerprints, tokenize
from diffinite.parser import strip_comments

# Project-root-relative location of the corpus and the output artifacts.
_REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = _REPO_ROOT / "example" / "plagiarism"
OUTPUT_DIR = _REPO_ROOT / "example" / "validation"

# The default deep threshold the tool ships with, on the 0–100 scale. Recorded
# here only so the summary can answer "what is the FP rate at the *current*
# default" — the headline question the review raised.
DEFAULT_THRESHOLD = 5.0

# Token-count strata. The collapse is a small-file phenomenon, so the bins are
# chosen to isolate it; boundaries are descriptive, not operating points.
_SIZE_BINS: tuple[tuple[str, int, int], ...] = (
    ("small (<150 tok)", 0, 150),
    ("medium (150–600)", 150, 600),
    ("large (>=600)", 600, 1 << 30),
)


def _size_bin(tokens: int) -> str:
    for label, lo, hi in _SIZE_BINS:
        if lo <= tokens < hi:
            return label
    return _SIZE_BINS[-1][0]


@dataclass(frozen=True)
class Doc:
    """A submission rendered as a single fingerprintable document."""

    raw_fp: frozenset[int]
    norm_fp: frozenset[int]
    tokens: int


@dataclass(frozen=True)
class PairScore:
    """One (original, submission) comparison, in one normalization mode."""

    case: str
    mode: str            # "raw" | "normalize"
    label: str           # "pos" | "neg"
    level: int | None    # 1..6 for positives, None for negatives
    jaccard: float       # 0.0–1.0
    tokens_min: int      # min token count across the two docs (stratification key)


def _build_doc(submission_dir: Path) -> Doc | None:
    """Concatenate every source file in *submission_dir* into one document and
    fingerprint it in both modes. Returns None if nothing readable is found."""
    texts: list[str] = []
    for f in sorted(submission_dir.rglob("*")):
        if not f.is_file():
            continue
        text = read_file(str(f))
        if text is None:
            continue
        texts.append(strip_comments(text, f.suffix.lower()))
    if not texts:
        return None
    cleaned = "\n".join(texts)
    raw = {fp.hash_value for fp in extract_fingerprints(cleaned, normalize=False)}
    norm = {fp.hash_value for fp in extract_fingerprints(cleaned, normalize=True)}
    return Doc(
        raw_fp=frozenset(raw),
        norm_fp=frozenset(norm),
        tokens=len(tokenize(cleaned, normalize=False)),
    )


def score_case(case_dir: Path) -> list[PairScore]:
    """Score one IR-Plag case: original vs every plagiarized/non-plagiarized
    submission, in both modes."""
    case = case_dir.name
    original = _build_doc(case_dir / "original")
    if original is None:
        return []

    scores: list[PairScore] = []

    def _emit(sub: Doc | None, label: str, level: int | None) -> None:
        if sub is None:
            return
        tmin = min(original.tokens, sub.tokens)
        for mode, a, b in (
            ("raw", original.raw_fp, sub.raw_fp),
            ("normalize", original.norm_fp, sub.norm_fp),
        ):
            scores.append(PairScore(
                case=case, mode=mode, label=label, level=level,
                jaccard=jaccard_similarity(set(a), set(b)), tokens_min=tmin,
            ))

    # Negatives: independent solutions to the same assignment.
    neg_root = case_dir / "non-plagiarized"
    if neg_root.is_dir():
        for sub_dir in sorted(p for p in neg_root.iterdir() if p.is_dir()):
            _emit(_build_doc(sub_dir), "neg", None)

    # Positives: obfuscated copies, grouped by level L1..L6.
    plag_root = case_dir / "plagiarized"
    if plag_root.is_dir():
        for level_dir in sorted(p for p in plag_root.iterdir() if p.is_dir()):
            try:
                level = int(level_dir.name.lstrip("Ll"))
            except ValueError:
                continue
            for sub_dir in sorted(p for p in level_dir.iterdir() if p.is_dir()):
                _emit(_build_doc(sub_dir), "pos", level)

    return scores


def score_corpus(root: Path = CORPUS_ROOT) -> list[PairScore]:
    """Score every case under *root*."""
    scores: list[PairScore] = []
    for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        scores.extend(score_case(case_dir))
    return scores


# ──────────────────────────────────────────────────────────────────────
# Sweep + reporting
# ──────────────────────────────────────────────────────────────────────
def fp_rate(scores: list[PairScore], mode: str, threshold: float,
            *, size_bin: str | None = None) -> tuple[int, int]:
    """Return (flagged, total) for negatives at a threshold (0–100 scale)."""
    negs = [s for s in scores if s.mode == mode and s.label == "neg"
            and (size_bin is None or _size_bin(s.tokens_min) == size_bin)]
    flagged = sum(1 for s in negs if s.jaccard * 100 >= threshold)
    return flagged, len(negs)


def recall(scores: list[PairScore], mode: str, threshold: float,
           *, level: int | None = None) -> tuple[int, int]:
    """Return (flagged, total) for positives at a threshold (0–100 scale)."""
    pos = [s for s in scores if s.mode == mode and s.label == "pos"
           and (level is None or s.level == level)]
    flagged = sum(1 for s in pos if s.jaccard * 100 >= threshold)
    return flagged, len(pos)


def _rate(flagged_total: tuple[int, int]) -> float:
    f, t = flagged_total
    return (f / t * 100) if t else 0.0


def sweep_rows(scores: list[PairScore]) -> list[dict]:
    """Full sweep for CSV: one row per (mode, threshold) with FP and recall."""
    rows: list[dict] = []
    levels = sorted({s.level for s in scores if s.label == "pos" and s.level})
    for mode in ("raw", "normalize"):
        for t in range(0, 101):
            row = {"mode": mode, "threshold": t}
            row["fp_rate"] = round(_rate(fp_rate(scores, mode, t)), 2)
            for label, lo, hi in _SIZE_BINS:
                row[f"fp_{label.split()[0]}"] = round(
                    _rate(fp_rate(scores, mode, t, size_bin=label)), 2)
            for lv in levels:
                row[f"recall_L{lv}"] = round(_rate(recall(scores, mode, t, level=lv)), 2)
            row["recall_all"] = round(_rate(recall(scores, mode, t)), 2)
            rows.append(row)
    return rows


@dataclass(frozen=True)
class CalibrationPoint:
    """One (token-floor, threshold) operating point on the calibration frontier."""

    floor: int           # withhold a verdict below this token count (inconclusive)
    threshold: int       # min Jaccard*100 to flag, among files at/above the floor
    fp_rate: float       # false-positive rate on negatives at/above the floor
    recall: float        # recall on positives at/above the floor
    coverage: float      # fraction of negatives that clear the floor (are judged)


def calibrate(scores: list[PairScore], *, fp_target: float = 5.0,
              mode: str = "normalize",
              min_coverage: float = 0.5) -> tuple[list[CalibrationPoint], CalibrationPoint | None]:
    """Derive the (floor, threshold) frontier for a false-positive target.

    The 'both' policy (raise threshold **and** add an inconclusive floor) is
    synergistic: excluding the files below the floor — where precision is
    unsalvageable at any useful threshold — lets the threshold for the *remaining*
    (larger) files come down while still meeting *fp_target*. This sweeps every
    candidate floor and, for each, finds the lowest threshold meeting the target
    on the files that clear it, recording the recall and coverage there.

    Returns ``(frontier, recommended)``. The recommendation is a transparent
    rule — highest recall among points that still judge at least *min_coverage*
    of the negatives — but the final pick is the maintainer's (forensic call).
    """
    floors = sorted({s.tokens_min for s in scores}) + [1 << 30]
    total_neg = sum(1 for s in scores if s.mode == mode and s.label == "neg")
    frontier: list[CalibrationPoint] = []

    for floor in floors:
        negs = [s for s in scores if s.mode == mode and s.label == "neg"
                and s.tokens_min >= floor]
        pos = [s for s in scores if s.mode == mode and s.label == "pos"
               and s.tokens_min >= floor]
        if not negs:
            continue
        coverage = len(negs) / total_neg if total_neg else 0.0
        chosen_t = None
        for t in range(0, 101):
            fp = sum(1 for s in negs if s.jaccard * 100 >= t) / len(negs) * 100
            if fp <= fp_target:
                chosen_t = t
                break
        if chosen_t is None:
            continue
        fp_at = sum(1 for s in negs if s.jaccard * 100 >= chosen_t) / len(negs) * 100
        rc = (sum(1 for s in pos if s.jaccard * 100 >= chosen_t) / len(pos) * 100
              if pos else 0.0)
        frontier.append(CalibrationPoint(
            floor=floor if floor != (1 << 30) else -1,
            threshold=chosen_t, fp_rate=round(fp_at, 2),
            recall=round(rc, 2), coverage=round(coverage, 3),
        ))

    eligible = [p for p in frontier if p.coverage >= min_coverage and p.floor != -1]
    recommended = max(eligible, key=lambda p: p.recall) if eligible else None
    return frontier, recommended


def write_csv(rows: list[dict], path: Path) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_md_summary(scores: list[PairScore], path: Path) -> None:
    levels = sorted({s.level for s in scores if s.label == "pos" and s.level})
    n_neg = sum(1 for s in scores if s.label == "neg" and s.mode == "raw")
    n_pos = sum(1 for s in scores if s.label == "pos" and s.mode == "raw")

    lines: list[str] = []
    lines.append("# Normalize-mode error rate (WS-A measurement)\n")
    lines.append(
        f"Corpus: Karnalim IR-Plag, {len({s.case for s in scores})} cases. "
        f"Negatives (independent same-domain submissions): **{n_neg}** pairs. "
        f"Positives (labelled copies L1–L6): **{n_pos}** pairs. "
        "A negative scoring above threshold is a **false positive**.\n")

    lines.append("## Headline — false-positive rate at the shipped default "
                 f"(`--threshold-deep {DEFAULT_THRESHOLD:.0f}`)\n")
    for mode in ("raw", "normalize"):
        fp = _rate(fp_rate(scores, mode, DEFAULT_THRESHOLD))
        rc = _rate(recall(scores, mode, DEFAULT_THRESHOLD))
        lines.append(
            f"- **{mode}**: false-positive rate **{fp:.1f}%**, "
            f"recall (all levels) {rc:.1f}% at threshold {DEFAULT_THRESHOLD:.0f}.")
    lines.append("")

    lines.append("### False positives stratified by submission size (normalize)\n")
    lines.append("| Size stratum | FP rate @5 | FP rate @20 | FP rate @50 | Note |")
    lines.append("|---|---|---|---|---|")
    for label, lo, hi in _SIZE_BINS:
        _, tot = fp_rate(scores, "normalize", 0, size_bin=label)
        if tot == 0:
            # Render an empty stratum honestly: "no samples", not a misleading 0%.
            lines.append(f"| {label} (n=0) | — | — | — | _no samples in corpus_ |")
            continue
        r5 = _rate(fp_rate(scores, "normalize", 5, size_bin=label))
        r20 = _rate(fp_rate(scores, "normalize", 20, size_bin=label))
        r50 = _rate(fp_rate(scores, "normalize", 50, size_bin=label))
        lines.append(f"| {label} (n={tot}) | {r5:.1f}% | {r20:.1f}% | {r50:.1f}% | |")
    lines.append("")

    lines.append("### Recall by obfuscation level\n")
    header = "| Threshold | " + " | ".join(f"L{lv} (raw/norm)" for lv in levels) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(levels) + 1))
    for t in (5, 20, 50):
        cells = []
        for lv in levels:
            rr = _rate(recall(scores, "raw", t, level=lv))
            rn = _rate(recall(scores, "normalize", t, level=lv))
            cells.append(f"{rr:.0f}/{rn:.0f}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("### Candidate normalize operating points\n")
    lines.append("Lowest threshold at which the normalize false-positive rate "
                 "falls to/below a target, and the recall there:\n")
    lines.append("| Target FP | Threshold | Recall (all) |")
    lines.append("|---|---|---|")
    for target in (5.0, 1.0, 0.0):
        chosen = None
        for t in range(0, 101):
            if _rate(fp_rate(scores, "normalize", t)) <= target:
                chosen = t
                break
        if chosen is None:
            lines.append(f"| ≤{target:.0f}% | (unreachable) | — |")
        else:
            rc = _rate(recall(scores, "normalize", chosen))
            lines.append(f"| ≤{target:.0f}% | {chosen} | {rc:.1f}% |")
    lines.append("")

    lines.append("### Joint (floor, threshold) calibration frontier — normalize\n")
    lines.append("The 'both' policy raises the threshold **and** withholds a "
                 "verdict below a token floor. Excluding sub-floor files (precision "
                 "unsalvageable there) lets the threshold for the rest come down "
                 "while still meeting the false-positive target.\n")
    for fp_target in (5.0, 1.0):
        frontier, rec = calibrate(scores, fp_target=fp_target)
        lines.append(f"**Target FP ≤ {fp_target:.0f}%**\n")
        lines.append("| Token floor | Threshold | FP rate | Recall (≥floor) | Coverage |")
        lines.append("|---|---|---|---|---|")
        for p in frontier:
            if p.floor == -1:
                continue
            star = "  ⟵ recommended" if rec and p.floor == rec.floor and \
                p.threshold == rec.threshold else ""
            lines.append(f"| {p.floor} | {p.threshold} | {p.fp_rate:.1f}% | "
                         f"{p.recall:.1f}% | {p.coverage*100:.0f}%{star} |")
        if rec:
            lines.append(f"\n> Recommended (highest recall with ≥50% coverage): "
                         f"**floor={rec.floor} tokens, threshold={rec.threshold}** "
                         f"→ FP {rec.fp_rate:.1f}%, recall {rec.recall:.1f}%.\n")
        else:
            lines.append("\n> No point meets the target with ≥50% coverage.\n")

    lines.append("> These are candidate operating points for WS-B, not a "
                 "decision. The threshold and the 'inconclusive' floor are "
                 "forensic-defensibility calls for the maintainer to ratify.\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    scores = score_corpus()
    if not scores:
        raise SystemExit(f"No scores produced — is {CORPUS_ROOT} present?")
    write_csv(sweep_rows(scores), OUTPUT_DIR / "pr_curve.csv")
    write_md_summary(scores, OUTPUT_DIR / "error_rate.md")

    # Machine-readable calibration for WS-B (calibration.py reads this).
    import json
    calib = {}
    for fp_target in (5.0, 1.0):
        _, rec = calibrate(scores, fp_target=fp_target)
        calib[f"fp_le_{int(fp_target)}"] = (
            None if rec is None else
            {"floor_tokens": rec.floor, "threshold": rec.threshold,
             "fp_rate": rec.fp_rate, "recall": rec.recall, "coverage": rec.coverage}
        )
    (OUTPUT_DIR / "calibration.json").write_text(
        json.dumps(calib, indent=2), encoding="utf-8")

    fp5 = _rate(fp_rate(scores, "normalize", DEFAULT_THRESHOLD))
    fp5_raw = _rate(fp_rate(scores, "raw", DEFAULT_THRESHOLD))
    print(f"Wrote {OUTPUT_DIR / 'pr_curve.csv'} and error_rate.md")
    print(f"FP@{DEFAULT_THRESHOLD:.0f}: raw={fp5_raw:.1f}%  normalize={fp5:.1f}%")


if __name__ == "__main__":
    main()
