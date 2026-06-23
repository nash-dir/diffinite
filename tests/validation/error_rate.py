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


def _file_doc(path: Path) -> Doc | None:
    """Fingerprint a single source file in both modes. None if unreadable/empty."""
    text = read_file(str(path))
    if text is None:
        return None
    cleaned = strip_comments(text, path.suffix.lower())
    raw = {fp.hash_value for fp in extract_fingerprints(cleaned, normalize=False)}
    norm = {fp.hash_value for fp in extract_fingerprints(cleaned, normalize=True)}
    if not raw and not norm:
        return None
    return Doc(
        raw_fp=frozenset(raw),
        norm_fp=frozenset(norm),
        tokens=len(tokenize(cleaned, normalize=False)),
    )


def _submission_files(submission_dir: Path) -> list[Doc]:
    """All fingerprintable files in a submission, as individual documents.

    Per-FILE, deliberately: the production tool does per-file N:M cross-matching
    and applies the threshold/floor to per-file token counts, so the validation
    must measure the same unit (the audit flagged that per-submission
    concatenation measured a different statistic than the runtime enforces)."""
    docs: list[Doc] = []
    for f in sorted(submission_dir.rglob("*")):
        if f.is_file():
            doc = _file_doc(f)
            if doc is not None:
                docs.append(doc)
    return docs


def score_case(case_dir: Path) -> list[PairScore]:
    """Score one IR-Plag case at the FILE-PAIR level (matching runtime): every
    original file vs every candidate file, in both modes."""
    case = case_dir.name
    original_files = _submission_files(case_dir / "original")
    if not original_files:
        return []

    scores: list[PairScore] = []

    def _emit(sub_dir: Path, label: str, level: int | None) -> None:
        for cand in _submission_files(sub_dir):
            for orig in original_files:
                tmin = min(orig.tokens, cand.tokens)
                for mode, a, b in (
                    ("raw", orig.raw_fp, cand.raw_fp),
                    ("normalize", orig.norm_fp, cand.norm_fp),
                ):
                    scores.append(PairScore(
                        case=case, mode=mode, label=label, level=level,
                        jaccard=jaccard_similarity(set(a), set(b)), tokens_min=tmin,
                    ))

    # Negatives: independent solutions to the same assignment (file pairs).
    neg_root = case_dir / "non-plagiarized"
    if neg_root.is_dir():
        for sub_dir in sorted(p for p in neg_root.iterdir() if p.is_dir()):
            _emit(sub_dir, "neg", None)

    # Positives: obfuscated copies, grouped by level L1..L6 (file pairs).
    plag_root = case_dir / "plagiarized"
    if plag_root.is_dir():
        for level_dir in sorted(p for p in plag_root.iterdir() if p.is_dir()):
            try:
                level = int(level_dir.name.lstrip("Ll"))
            except ValueError:
                continue
            for sub_dir in sorted(p for p in level_dir.iterdir() if p.is_dir()):
                _emit(sub_dir, "pos", level)

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


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a proportion, returned as percentages (lo, hi).

    A point estimate like "1 false positive in 105" is not a *known* error rate:
    its 95% interval is wide. Forensic reports must state the interval, not the
    point — a single observation's CI can span an order of magnitude.
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - half) * 100, min(1.0, center + half) * 100)


def per_case_fp(scores: list[PairScore], mode: str, threshold: float) -> list[float]:
    """False-positive rate within each case, to expose clustering (the pairs are
    not i.i.d.: they cluster by assignment, so the pooled CI is optimistic)."""
    cases = sorted({s.case for s in scores})
    out: list[float] = []
    for c in cases:
        negs = [s for s in scores if s.case == c and s.mode == mode and s.label == "neg"]
        if negs:
            out.append(sum(1 for s in negs if s.jaccard * 100 >= threshold) / len(negs) * 100)
    return out


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
        fk, fn = fp_rate(scores, mode, DEFAULT_THRESHOLD)
        lo, hi = wilson_ci(fk, fn)
        rc = _rate(recall(scores, mode, DEFAULT_THRESHOLD))
        lines.append(
            f"- **{mode}**: false-positive rate **{_rate((fk, fn)):.1f}%** "
            f"(95% CI [{lo:.1f}%, {hi:.1f}%], {fk}/{fn}), "
            f"recall (all levels) {rc:.1f}% at threshold {DEFAULT_THRESHOLD:.0f}.")
    lines.append("")
    lines.append("> Measurement unit: **per file pair** (every original file vs every "
                 "candidate file), matching the runtime's per-file N:M decision and "
                 "the per-file token floor.\n")

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

    # ── Defensible characterization of the ratified FP ≤ 1% operating point ──
    _, rec = calibrate(scores, fp_target=1.0)
    lines.append("## Operating-point characterization (ratified: FP ≤ 1%)\n")
    if rec is None:
        lines.append("> No FP ≤ 1% point with ≥50% coverage exists on this corpus.\n")
    else:
        t = rec.threshold
        fk, fn = fp_rate(scores, "normalize", t)
        lo, hi = wilson_ci(fk, fn)
        lines.append(
            f"Threshold **{t}**, token floor **{rec.floor}**. False-positive rate "
            f"**{_rate((fk, fn)):.2g}%** — but this is **{fk} of {fn}** negatives; "
            f"the Wilson 95% CI is **[{lo:.2g}%, {hi:.2g}%]**. The point estimate is "
            "not a *known* 1% rate: a single negative crossing the threshold drives "
            "the headline, and the interval's upper bound is what an opposing expert "
            "will cite.\n")

        lines.append("**Recall at this operating point is NOT uniform** — it collapses "
                     "on the obfuscation `--normalize` exists to catch:\n")
        lines.append("| Level | Recall @ threshold {} |".format(t))
        lines.append("|---|---|")
        for lv in levels:
            rk, rn = recall(scores, "normalize", t, level=lv)
            lines.append(f"| L{lv} | {_rate((rk, rn)):.0f}% ({rk}/{rn}) |")
        lines.append("\n> At this threshold the tool reliably flags only near-verbatim "
                     "copies; heavily restructured copies fall below threshold and "
                     "require manual review. Do not cite the pooled recall as uniform "
                     "sensitivity.\n")

        # Clustering: the pairs are not i.i.d.
        pcf = per_case_fp(scores, "normalize", t)
        n_cases = len({s.case for s in scores})
        lines.append(
            f"**Clustering:** the {fn} negative pairs derive from only {n_cases} "
            f"assignments (one reference solution each), so they are not "
            f"independent; the effective sample size is closer to {n_cases}. Per-case "
            f"false-positive rate ranges {min(pcf):.0f}%–{max(pcf):.0f}%. The pooled "
            "CI above therefore *understates* true uncertainty.\n")

        # Size scope.
        max_tok = max((s.tokens_min for s in scores if s.label == "neg"), default=0)
        lines.append(
            f"**Size scope:** every tested file pair has ≤ {max_tok} tokens (no large "
            "files in this corpus). The operating point is unvalidated on large files; "
            "the calibration characterizes small-file behavior only.\n")

        # Floor binding.
        below = sum(1 for s in scores
                    if s.label == "neg" and s.mode == "normalize" and s.tokens_min < rec.floor)
        lines.append(
            f"**Floor binding:** {below} of {fn} negatives fall below the {rec.floor}-token "
            f"floor. {'The floor actively withholds verdicts on those.' if below else 'The floor excludes no negative here, so the realized FP rate is a pure-threshold result; the floor still suppresses sub-floor *runtime* matches, which this corpus does not exercise.'}\n")

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
    calib = {"unit": "file-pair"}
    for fp_target in (5.0, 1.0):
        _, rec = calibrate(scores, fp_target=fp_target)
        if rec is None:
            calib[f"fp_le_{int(fp_target)}"] = None
            continue
        fk, fn = fp_rate(scores, "normalize", rec.threshold)
        lo, hi = wilson_ci(fk, fn)
        per_level = {
            f"L{lv}": round(_rate(recall(scores, "normalize", rec.threshold, level=lv)), 1)
            for lv in sorted({s.level for s in scores if s.label == "pos" and s.level})
        }
        calib[f"fp_le_{int(fp_target)}"] = {
            "floor_tokens": rec.floor, "threshold": rec.threshold,
            "fp_rate": rec.fp_rate, "fp_ci95": [round(lo, 2), round(hi, 2)],
            "fp_observed": [fk, fn], "recall": rec.recall, "recall_by_level": per_level,
            "coverage": rec.coverage,
        }
    (OUTPUT_DIR / "calibration.json").write_text(
        json.dumps(calib, indent=2), encoding="utf-8")

    fp5 = _rate(fp_rate(scores, "normalize", DEFAULT_THRESHOLD))
    fp5_raw = _rate(fp_rate(scores, "raw", DEFAULT_THRESHOLD))
    print(f"Wrote {OUTPUT_DIR / 'pr_curve.csv'} and error_rate.md")
    print(f"FP@{DEFAULT_THRESHOLD:.0f}: raw={fp5_raw:.1f}%  normalize={fp5:.1f}%")


if __name__ == "__main__":
    main()
