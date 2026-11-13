"""Out-of-sample checks of the normalize operating point (threshold 93).

``error_rate.py`` chose threshold 93 *and* measured its false-positive rate on
the same 105 IR-Plag negatives, so that rate is in-sample (optimistic). This
harness answers two questions an opposing expert would ask, without changing
the shipped threshold:

1. **Leave-one-case-out (LOCO) on IR-Plag.** For each of the 7 assignments,
   pick the threshold on the *other six* with the same written rule as the
   shipped point (lowest whole-number threshold whose FP rate is <= 1%), then
   count false positives and recall on the held-out assignment only. Splitting
   by assignment, not by pair, keeps same-task pairs out of both sides. With 90
   training negatives the 1% rule permits zero false positives, while on all
   105 it permits one; the report states how often no threshold qualifies.

2. **SOCO 2014 Java/C training set** (Flores et al., FIRE 2014) — a corpus that
   played no part in choosing 93. Every file pair is scored at the frozen
   profile; the expert-annotated re-use pairs (qrels) are positives. All other
   pairs are *unlabelled*, not proven independent, so their flag count bounds
   the false-positive rate from above; it is not a measured FP rate.

It also records directional containment (shared / unique hashes of each side)
on IR-Plag, descriptively — no containment threshold is proposed here.

Usage (both corpora are fetched and SHA-256-verified by
``python example/download_examples.py --dataset plagiarism`` and
``--dataset soco14``)::

    python -m tests.validation.holdout

Outputs ``example/validation/holdout.md`` and ``holdout.json``.
"""

from __future__ import annotations

import itertools
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from diffinite.calibration import (
    CALIBRATION_MAX_FILE_TOKENS,
    NORMALIZE_CALIBRATION_K,
    NORMALIZE_CALIBRATION_W,
    NORMALIZE_DEFAULT_THRESHOLD,
)
from diffinite.differ import read_file
from diffinite.fingerprint import extract_fingerprints, tokenize
from diffinite.parser import strip_comments
from tests.validation.error_rate import (
    CORPUS_ROOT,
    OUTPUT_DIR,
    is_flagged,
    verify_corpus,
    wilson_ci,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
SOCO_TRAIN = _REPO_ROOT / "example" / "soco14" / "fire14-source-code-training-dataset"

# Same selection rule as the shipped operating point (calibration.json "fp_le_1"),
# plus the looser fp_le_5 rule from the same artifact to show rule sensitivity.
FP_TARGETS_PCT = (1.0, 5.0)


def _norm_set(path: Path) -> frozenset[int] | None:
    """Fingerprint one file exactly as the frozen calibration profile does."""
    text = read_file(str(path))
    if not text:
        return None
    cleaned = strip_comments(text, path.suffix.lower())
    fps = extract_fingerprints(
        cleaned, k=NORMALIZE_CALIBRATION_K, w=NORMALIZE_CALIBRATION_W, normalize=True
    )
    hashes = frozenset(fp.hash_value for fp in fps)
    return hashes or None


@dataclass(frozen=True)
class Pair:
    case: str
    label: str  # "pos" | "neg"
    level: int | None
    jaccard: float
    a_in_b: float  # shared / |original|
    b_in_a: float  # shared / |candidate|


def _pair(case: str, label: str, level: int | None, a: frozenset, b: frozenset) -> Pair:
    shared = len(a & b)
    union = len(a | b)
    return Pair(case, label, level, shared / union if union else 0.0,
                shared / len(a), shared / len(b))


def _files(d: Path) -> list[frozenset[int]]:
    out = []
    for f in sorted(p for p in d.rglob("*") if p.is_file()):
        s = _norm_set(f)
        if s is not None:
            out.append(s)
    return out


def score_irplag(root: Path = CORPUS_ROOT) -> list[Pair]:
    """Original-vs-candidate file pairs, the same unit error_rate.py measures."""
    pairs: list[Pair] = []
    for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        originals = _files(case_dir / "original")
        neg_root = case_dir / "non-plagiarized"
        for sub in sorted(p for p in neg_root.iterdir() if p.is_dir()):
            for cand in _files(sub):
                pairs.extend(_pair(case_dir.name, "neg", None, o, cand) for o in originals)
        plag_root = case_dir / "plagiarized"
        for level_dir in sorted(p for p in plag_root.iterdir() if p.is_dir()):
            level = int(level_dir.name.lstrip("Ll"))
            for sub in sorted(p for p in level_dir.iterdir() if p.is_dir()):
                for cand in _files(sub):
                    pairs.extend(_pair(case_dir.name, "pos", level, o, cand) for o in originals)
    return pairs


def _select_threshold(train: list[Pair], fp_target: float) -> int:
    """Lowest whole threshold meeting *fp_target*; 101 means none does (flag nothing)."""
    negs = [p for p in train if p.label == "neg"]
    for t in range(0, 101):
        if sum(is_flagged(p.jaccard, t) for p in negs) / len(negs) * 100 <= fp_target:
            return t
    return 101


def fixed_threshold_by_case(pairs: list[Pair], threshold: float) -> list[dict]:
    """The shipped threshold, unchanged, scored on each assignment separately."""
    out = []
    for case in sorted({p.case for p in pairs}):
        negs = [p for p in pairs if p.case == case and p.label == "neg"]
        pos = [p for p in pairs if p.case == case and p.label == "pos"]
        out.append({
            "case": case,
            "fp": sum(is_flagged(p.jaccard, threshold) for p in negs),
            "negatives": len(negs),
            "tp": sum(is_flagged(p.jaccard, threshold) for p in pos),
            "positives": len(pos),
        })
    return out


def loco(pairs: list[Pair], fp_target: float) -> dict:
    cases = sorted({p.case for p in pairs})
    folds = []
    for held in cases:
        train = [p for p in pairs if p.case != held]
        test = [p for p in pairs if p.case == held]
        t = _select_threshold(train, fp_target)
        negs = [p for p in test if p.label == "neg"]
        pos = [p for p in test if p.label == "pos"]
        folds.append({
            "held_out": held,
            "threshold": t,
            "fp": sum(is_flagged(p.jaccard, t) for p in negs),
            "negatives": len(negs),
            "tp": sum(is_flagged(p.jaccard, t) for p in pos),
            "positives": len(pos),
        })
    fp = sum(f["fp"] for f in folds)
    n = sum(f["negatives"] for f in folds)
    tp = sum(f["tp"] for f in folds)
    npos = sum(f["positives"] for f in folds)
    lo, hi = wilson_ci(fp, n)
    return {
        "fp_target_pct": fp_target,
        "folds": folds,
        # Folds where no threshold met the target on the 6 training assignments.
        "infeasible_folds": sum(1 for f in folds if f["threshold"] > 100),
        "pooled_fp": [fp, n],
        "pooled_fp_rate_pct": round(fp / n * 100, 2),
        # Pools folds that used different thresholds: describes the selection
        # procedure, not any single operating point.
        "pooled_fp_wilson95_pct": [round(lo, 2), round(hi, 2)],
        "pooled_recall_pct": round(tp / npos * 100, 2),
        "folds_with_any_fp": sum(1 for f in folds if f["fp"]),
    }


def containment_summary(pairs: list[Pair]) -> dict:
    """Quantiles of max(A in B, B in A) — descriptive, no threshold implied."""
    def q(vals: list[float]) -> dict:
        vals = sorted(vals)
        cut = statistics.quantiles(vals, n=20, method="inclusive") if len(vals) > 1 else vals * 19
        return {"n": len(vals), "median": round(statistics.median(vals), 3),
                "p95": round(cut[18], 3), "max": round(vals[-1], 3)}

    out = {"negatives": q([max(p.a_in_b, p.b_in_a) for p in pairs if p.label == "neg"])}
    for lv in sorted({p.level for p in pairs if p.level}):
        out[f"L{lv}"] = q([max(p.a_in_b, p.b_in_a) for p in pairs if p.level == lv])
    return out


def score_soco(lang: str) -> dict | None:
    src = SOCO_TRAIN / lang
    qrel = SOCO_TRAIN / f"SOCO14-{lang}.qrel"
    if not src.is_dir() or not qrel.is_file():
        return None
    positives = set()
    for line in qrel.read_text(encoding="utf-8").split("\n"):
        parts = line.split()
        if len(parts) == 2:
            positives.add(frozenset(parts))
    sets = {f.name: s for f in sorted(src.iterdir()) if (s := _norm_set(f)) is not None}
    token_counts = sorted(
        len(tokenize(strip_comments(read_file(str(f)) or "", f.suffix.lower())))
        for f in src.iterdir()
    )
    t = NORMALIZE_DEFAULT_THRESHOLD
    flagged_pos = flagged_unl = n_pos = n_unl = 0
    for (na, a), (nb, b) in itertools.combinations(sets.items(), 2):
        union = len(a | b)
        flagged = is_flagged(len(a & b) / union if union else 0.0, t)
        if frozenset((na, nb)) in positives:
            n_pos += 1
            flagged_pos += flagged
        else:
            n_unl += 1
            flagged_unl += flagged
    return {
        "language": lang,
        "threshold": t,
        "files": len(sets),
        "positives": n_pos,
        "recall_pct": round(flagged_pos / n_pos * 100, 2) if n_pos else None,
        "unlabelled_pairs": n_unl,
        "unlabelled_flagged": flagged_unl,
        "unlabelled_flag_rate_pct": round(flagged_unl / n_unl * 100, 4),
        # No confidence bound: every file appears in ~(files-1) pairs, so the
        # pairs are far from independent and a binomial bound would mislead.
        "median_tokens": int(statistics.median(token_counts)),
        "share_files_over_largest_calibration_file_pct": round(
            # Per-FILE counts against the per-FILE IR-Plag maximum (same unit; the
            # 212 bound is a per-pair smaller-file size and must not be used here).
            sum(t > CALIBRATION_MAX_FILE_TOKENS for t in token_counts)
            / len(token_counts) * 100,
            1,
        ),
    }


def write_md(result: dict, path: Path) -> None:
    lines = [
        "# Out-of-sample check of the normalize operating point",
        "",
        "> Generated by `python -m tests.validation.holdout`. Profile: normalize, "
        f"K={NORMALIZE_CALIBRATION_K}, W={NORMALIZE_CALIBRATION_W}, comments stripped, "
        "language-aware off — the frozen calibration profile.",
        "",
        "Corpus digests (sha256 over POSIX-path-sorted path + file hash): IR-Plag "
        f"`{result['corpus_sha256']['irplag']}`"
        + (f", SOCO training `{result['corpus_sha256']['soco']}`"
           if result["corpus_sha256"].get("soco") else "")
        + ".",
        "",
        "## 1. The shipped threshold 93, per assignment",
        "",
        "The threshold is fixed here (not re-selected); each row is one IR-Plag assignment.",
        "",
        "| Assignment | FP / negatives | Recall |",
        "|---|:-:|:-:|",
    ]
    for r in result["fixed_threshold_by_case"]:
        lines.append(f"| {r['case']} | {r['fp']}/{r['negatives']} "
                     f"| {r['tp'] / r['positives'] * 100:.1f}% |")
    lines += [
        "",
        "Because 93 was itself chosen on these assignments, this table is still "
        "in-sample; it shows where the single false positive sits, not an "
        "out-of-sample rate.",
        "",
        "## 2. Re-selecting the threshold, leave-one-assignment-out",
        "",
        "Threshold chosen on 6 assignments (lowest whole number meeting the FP "
        "target), then evaluated on the 7th. Threshold 101 = no threshold meets the "
        "target, so nothing is flagged. With 90 training negatives a 1% target "
        "allows **zero** false positives (1/90 = 1.1%), whereas on all 105 it allows "
        "one, so the rule's strictness depends on sample size.",
        "",
    ]
    for lo_ in result["loco"]:
        lines += [
            f"### FP target <= {lo_['fp_target_pct']:g}%",
            "",
            "| Held-out | Threshold | FP / negatives | Recall |",
            "|---|:-:|:-:|:-:|",
        ]
        for f in lo_["folds"]:
            rc = f["tp"] / f["positives"] * 100 if f["positives"] else 0.0
            lines.append(f"| {f['held_out']} | {f['threshold']} | {f['fp']}/{f['negatives']} "
                         f"| {rc:.1f}% |")
        lo, hi = lo_["pooled_fp_wilson95_pct"]
        lines += [
            "",
            f"No threshold met the target in **{lo_['infeasible_folds']} of "
            f"{len(lo_['folds'])}** folds. Pooled over folds (which used different "
            f"thresholds): FP {lo_['pooled_fp'][0]}/{lo_['pooled_fp'][1]} = "
            f"{lo_['pooled_fp_rate_pct']}% (Wilson 95% CI {lo}–{hi}%; pairs cluster in "
            f"{len(lo_['folds'])} assignments, so the true interval is wider), "
            f"recall {lo_['pooled_recall_pct']}%. This describes the selection "
            "procedure, not one operating point.",
            "",
        ]
    lines += [
        "## 3. SOCO 2014 training set at threshold 93 (never used for calibration)",
        "",
        "Unlabelled pairs are *not* proven independent, so their flag count bounds "
        "the false-positive rate from above but does not measure it. No confidence "
        "bound is given: every file appears in about (files - 1) pairs, so the pairs "
        "are not independent. Most SOCO files are larger than the largest IR-Plag "
        f"file ({CALIBRATION_MAX_FILE_TOKENS} tokens).",
        "",
        f"| Language | Files | Median tokens | Files > {CALIBRATION_MAX_FILE_TOKENS} tokens "
        "| Recall on expert re-use pairs | Unlabelled pairs flagged |",
        "|---|:-:|:-:|:-:|:-:|:-:|",
    ]
    for s in result["soco"]:
        lines.append(
            f"| {s['language']} | {s['files']} | {s['median_tokens']} "
            f"| {s['share_files_over_largest_calibration_file_pct']}% | {s['recall_pct']}% "
            f"({s['positives']} pairs) | {s['unlabelled_flagged']}/{s['unlabelled_pairs']} |")
    lines += [
        "",
        "## 4. Directional containment on IR-Plag (descriptive)",
        "",
        "max(A in B, B in A) per file pair. No containment threshold is calibrated.",
        "",
        "| Group | n | median | 95th pct | max |",
        "|---|:-:|:-:|:-:|:-:|",
    ]
    for k, v in result["containment"].items():
        lines.append(f"| {k} | {v['n']} | {v['median']} | {v['p95']} | {v['max']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    # Both corpora must be the pinned bytes; the digests recorded below are the
    # ones actually measured (platform-independent, see error_rate.tree_sha256).
    irplag_sha256 = verify_corpus(CORPUS_ROOT, "plagiarism")
    soco_sha256 = verify_corpus(SOCO_TRAIN, "soco14") if SOCO_TRAIN.is_dir() else None
    pairs = score_irplag()
    result = {
        "corpus_sha256": {
            "irplag": irplag_sha256,
            "soco": soco_sha256,
        },
        "fixed_threshold_by_case": fixed_threshold_by_case(pairs, NORMALIZE_DEFAULT_THRESHOLD),
        "loco": [loco(pairs, t) for t in FP_TARGETS_PCT],
        "containment": containment_summary(pairs),
        "soco": [s for s in (score_soco("java"), score_soco("c")) if s is not None],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "holdout.json").write_text(json.dumps(result, indent=2) + "\n",
                                             encoding="utf-8")
    write_md(result, OUTPUT_DIR / "holdout.md")
    print((OUTPUT_DIR / "holdout.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
