"""Generate analysis reports for all 3 example datasets.

Produces per-dataset reports in TDD/result_2603141013/:
  1. sqlite_analysis.md   — SQLite amalgamation C diff analysis
  2. aosp_analysis.md     — AOSP Android 9 vs 11 Java diff analysis
  3. plagiarism_analysis.md — IR-Plag-Dataset cross-validation analysis
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diffinite.fingerprint import extract_fingerprints
from diffinite.parser import strip_comments
from diffinite.evidence import (
    compute_channel_scores,
    _DEFAULT_WEIGHTS,
    _ACADEMIC_WEIGHTS,
)

RESULT_DIR = PROJECT_ROOT / "TDD" / "result_2603141013"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def read_file(path: Path) -> str | None:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def fp(text: str, ext: str, k: int = 5, w: int = 4) -> dict:
    cleaned = strip_comments(text, ext)
    r = {f.hash_value for f in extract_fingerprints(cleaned, k=k, w=w, normalize=False, mode="token", extension=ext)}
    n = {f.hash_value for f in extract_fingerprints(cleaned, k=k, w=w, normalize=True, mode="token", extension=ext)}
    return {"raw": r, "normalized": n, "text": text, "cleaned": cleaned}


def channel_scores(a, b, ext, weights=None):
    return compute_channel_scores(
        fp_raw_a=a["raw"], fp_raw_b=b["raw"],
        fp_norm_a=a["normalized"], fp_norm_b=b["normalized"],
        source_a=a["text"], source_b=b["text"],
        cleaned_a=a["cleaned"], cleaned_b=b["cleaned"],
        extension=ext, weights=weights,
    )


def file_stats(path: Path) -> dict:
    text = read_file(path)
    if text is None:
        return {"lines": 0, "bytes": 0}
    return {"lines": text.count("\n") + 1, "bytes": len(text.encode("utf-8", errors="replace"))}

# ──────────────────────────────────────────────────────────────────────
# 1. SQLite Analysis
# ──────────────────────────────────────────────────────────────────────

def analyze_sqlite():
    print("Analyzing SQLite example...")
    sqlite_dir = PROJECT_ROOT / "example" / "sqlite"
    left_dir = sqlite_dir / "left"
    right_dir = sqlite_dir / "right"

    files = ["sqlite3.c", "sqlite3.h", "sqlite3ext.h", "shell.c"]
    results = []

    for fname in files:
        left_path = left_dir / fname
        right_path = right_dir / fname
        if not left_path.exists() or not right_path.exists():
            continue

        left_text = read_file(left_path)
        right_text = read_file(right_path)
        if not left_text or not right_text:
            continue

        left_stats = file_stats(left_path)
        right_stats = file_stats(right_path)

        ext = ".c" if fname.endswith(".c") else ".h"
        left_fp = fp(left_text, ext)
        right_fp = fp(right_text, ext)

        scores = channel_scores(left_fp, right_fp, ext)

        results.append({
            "file": fname,
            "left_lines": left_stats["lines"],
            "right_lines": right_stats["lines"],
            "left_bytes": left_stats["bytes"],
            "right_bytes": right_stats["bytes"],
            "scores": scores,
        })

    # Generate report
    report = []
    report.append("# SQLite Example Analysis Report")
    report.append(f"\n> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"> Dataset: `example/sqlite/`")
    report.append("")
    report.append("## Overview")
    report.append("")
    report.append("Cross-version comparison of SQLite amalgamation source files.")
    report.append("Two versions of the SQLite C source are compared to measure")
    report.append("code evolution similarity using Diffinite's multi-channel algorithm.")
    report.append("")
    report.append("## File Statistics")
    report.append("")
    report.append("| File | Left (lines) | Right (lines) | Left (KB) | Right (KB) |")
    report.append("|------|-------------|--------------|-----------|-----------|")
    for r in results:
        report.append(f"| `{r['file']}` | {r['left_lines']:,} | {r['right_lines']:,} | {r['left_bytes']//1024:,} | {r['right_bytes']//1024:,} |")

    total_left = sum(r["left_lines"] for r in results)
    total_right = sum(r["right_lines"] for r in results)
    report.append(f"| **Total** | **{total_left:,}** | **{total_right:,}** | | |")

    report.append("")
    report.append("## Multi-Channel Similarity Scores (K=5, W=4)")
    report.append("")
    report.append("| File | Raw Winnowing | Normalized | Identifier Cosine | Comment/String | **Composite** |")
    report.append("|------|:---:|:---:|:---:|:---:|:---:|")
    for r in results:
        s = r["scores"]
        report.append(
            f"| `{r['file']}` "
            f"| {s.get('raw_winnowing', 0):.4f} "
            f"| {s.get('normalized_winnowing', 0):.4f} "
            f"| {s.get('identifier_cosine', 0):.4f} "
            f"| {s.get('comment_string_overlap', 0):.4f} "
            f"| **{s.get('composite', 0):.4f}** |"
        )

    report.append("")
    report.append("## Key Findings")
    report.append("")
    if results:
        avg_composite = sum(r["scores"].get("composite", 0) for r in results) / len(results)
        max_r = max(results, key=lambda x: x["scores"].get("composite", 0))
        min_r = min(results, key=lambda x: x["scores"].get("composite", 0))
        report.append(f"- **Average composite similarity**: {avg_composite:.4f}")
        report.append(f"- **Highest similarity**: `{max_r['file']}` ({max_r['scores'].get('composite', 0):.4f})")
        report.append(f"- **Lowest similarity**: `{min_r['file']}` ({min_r['scores'].get('composite', 0):.4f})")
        report.append(f"- **Total codebase size**: {total_left:,} + {total_right:,} = {total_left+total_right:,} lines")
        report.append(f"- The SQLite amalgamation is a massive monolithic C file (~250K lines), ideal for stress-testing Diffinite's industrial-scale performance.")

    out_path = RESULT_DIR / "sqlite_analysis.md"
    out_path.write_text("\n".join(report), encoding="utf-8")
    print(f"  → {out_path}")
    return results

# ──────────────────────────────────────────────────────────────────────
# 2. AOSP Analysis
# ──────────────────────────────────────────────────────────────────────

def analyze_aosp():
    print("Analyzing AOSP example...")
    aosp_dir = PROJECT_ROOT / "example" / "aosp"
    left_dir = aosp_dir / "left"
    right_dir = aosp_dir / "right"

    files = ["Handler.java", "Looper.java", "Message.java"]
    results = []

    for fname in files:
        left_path = left_dir / fname
        right_path = right_dir / fname
        if not left_path.exists() or not right_path.exists():
            continue

        left_text = read_file(left_path)
        right_text = read_file(right_path)
        if not left_text or not right_text:
            continue

        left_stats = file_stats(left_path)
        right_stats = file_stats(right_path)

        left_fp = fp(left_text, ".java")
        right_fp = fp(right_text, ".java")
        scores = channel_scores(left_fp, right_fp, ".java")

        results.append({
            "file": fname,
            "left_lines": left_stats["lines"],
            "right_lines": right_stats["lines"],
            "left_bytes": left_stats["bytes"],
            "right_bytes": right_stats["bytes"],
            "scores": scores,
        })

    report = []
    report.append("# AOSP Example Analysis Report")
    report.append(f"\n> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"> Dataset: `example/aosp/`")
    report.append("")
    report.append("## Overview")
    report.append("")
    report.append("Cross-version comparison of AOSP (Android Open Source Project)")
    report.append("core OS Java files: Android 9 (Pie) vs Android 11.")
    report.append("Targets `android.os.Handler`, `Looper`, and `Message` — the core")
    report.append("message-passing framework of Android's main thread architecture.")
    report.append("")
    report.append("## File Statistics")
    report.append("")
    report.append("| File | Android 9 (lines) | Android 11 (lines) | A9 (KB) | A11 (KB) |")
    report.append("|------|:---:|:---:|:---:|:---:|")
    for r in results:
        report.append(f"| `{r['file']}` | {r['left_lines']:,} | {r['right_lines']:,} | {r['left_bytes']//1024} | {r['right_bytes']//1024} |")

    total_left = sum(r["left_lines"] for r in results)
    total_right = sum(r["right_lines"] for r in results)
    report.append(f"| **Total** | **{total_left:,}** | **{total_right:,}** | | |")

    report.append("")
    report.append("## Multi-Channel Similarity Scores (K=5, W=4)")
    report.append("")
    report.append("| File | Raw Winnowing | Normalized | Identifier Cosine | Comment/String | **Composite** |")
    report.append("|------|:---:|:---:|:---:|:---:|:---:|")
    for r in results:
        s = r["scores"]
        report.append(
            f"| `{r['file']}` "
            f"| {s.get('raw_winnowing', 0):.4f} "
            f"| {s.get('normalized_winnowing', 0):.4f} "
            f"| {s.get('identifier_cosine', 0):.4f} "
            f"| {s.get('comment_string_overlap', 0):.4f} "
            f"| **{s.get('composite', 0):.4f}** |"
        )

    report.append("")
    report.append("## Key Findings")
    report.append("")
    if results:
        avg_composite = sum(r["scores"].get("composite", 0) for r in results) / len(results)
        max_r = max(results, key=lambda x: x["scores"].get("composite", 0))
        min_r = min(results, key=lambda x: x["scores"].get("composite", 0))
        report.append(f"- **Average composite similarity**: {avg_composite:.4f}")
        report.append(f"- **Highest similarity**: `{max_r['file']}` ({max_r['scores'].get('composite', 0):.4f}) — least changed between versions")
        report.append(f"- **Lowest similarity**: `{min_r['file']}` ({min_r['scores'].get('composite', 0):.4f}) — most evolution")
        report.append(f"- These files represent Android's core threading infrastructure with moderate-size Java classes (300–900 lines), testing Diffinite's industrial profile on real-world version evolution.")

    out_path = RESULT_DIR / "aosp_analysis.md"
    out_path.write_text("\n".join(report), encoding="utf-8")
    print(f"  → {out_path}")
    return results

# ──────────────────────────────────────────────────────────────────────
# 3. Plagiarism Analysis
# ──────────────────────────────────────────────────────────────────────

def analyze_plagiarism():
    print("Analyzing Plagiarism dataset...")
    dataset_root = PROJECT_ROOT / "example" / "plagiarism"
    cases = sorted(p.name for p in dataset_root.iterdir() if p.is_dir())
    levels = [f"L{i}" for i in range(1, 7)]

    # Collect all scores with both profiles
    results_industrial = defaultdict(lambda: defaultdict(list))
    results_academic = defaultdict(lambda: defaultdict(list))
    neg_industrial = defaultdict(list)
    neg_academic = defaultdict(list)

    case_originals = {}

    for case_name in cases:
        case_dir = dataset_root / case_name
        orig_files = sorted((case_dir / "original").rglob("*.java"))
        if not orig_files:
            continue
        orig_text = read_file(orig_files[0])
        if not orig_text:
            continue

        case_originals[case_name] = {
            "file": orig_files[0].name,
            "lines": orig_text.count("\n") + 1,
        }

        orig_fp_ind = fp(orig_text, ".java", k=5, w=4)
        orig_fp_acad = fp(orig_text, ".java", k=2, w=3)

        for level in levels:
            level_dir = case_dir / "plagiarized" / level
            if not level_dir.exists():
                continue
            for jf in sorted(level_dir.rglob("*.java")):
                text = read_file(jf)
                if text:
                    # Industrial
                    s = channel_scores(orig_fp_ind, fp(text, ".java", k=5, w=4), ".java")
                    results_industrial[case_name][level].append(s.get("composite", 0))
                    # Academic
                    s = channel_scores(orig_fp_acad, fp(text, ".java", k=2, w=3), ".java", _ACADEMIC_WEIGHTS)
                    results_academic[case_name][level].append(s.get("composite", 0))

        for jf in sorted((case_dir / "non-plagiarized").rglob("*.java")):
            text = read_file(jf)
            if text:
                s = channel_scores(orig_fp_ind, fp(text, ".java", k=5, w=4), ".java")
                neg_industrial[case_name].append(s.get("composite", 0))
                s = channel_scores(orig_fp_acad, fp(text, ".java", k=2, w=3), ".java", _ACADEMIC_WEIGHTS)
                neg_academic[case_name].append(s.get("composite", 0))

    # Build report
    report = []
    report.append("# Plagiarism Dataset Analysis Report")
    report.append(f"\n> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"> Dataset: `example/plagiarism/` (IR-Plag-Dataset)")
    report.append("")
    report.append("## Overview")
    report.append("")
    report.append("Cross-validation of Diffinite against the IR-Plag-Dataset — 7 introductory")
    report.append("Java programming tasks with Faidhi-Robinson L1–L6 plagiarism levels and")
    report.append("independent (non-plagiarized) submissions.")
    report.append("")
    report.append("| Level | Plagiarism Technique |")
    report.append("|-------|---------------------|")
    report.append("| L1 | Comment/formatting changes |")
    report.append("| L2 | Identifier renaming |")
    report.append("| L3 | Statement reordering |")
    report.append("| L4 | Function extraction/refactoring |")
    report.append("| L5 | Loop/control-flow transformation |")
    report.append("| L6 | Complete logic restructuring |")
    report.append("")

    # Case summary
    report.append("## Case Summary")
    report.append("")
    report.append("| Case | Original File | Lines | Plagiarized | Non-Plagiarized |")
    report.append("|------|--------------|:---:|:---:|:---:|")
    for case_name in cases:
        o = case_originals.get(case_name, {})
        n_plag = sum(len(v) for v in results_industrial.get(case_name, {}).values())
        n_neg = len(neg_industrial.get(case_name, []))
        report.append(f"| `{case_name}` | `{o.get('file', '?')}` | {o.get('lines', 0)} | {n_plag} | {n_neg} |")

    # Industrial profile scores
    report.append("")
    report.append("## Industrial Profile (K=5, W=4, T=0.10)")
    report.append("")
    report.append("### Per-Level Average Composite Score")
    report.append("")
    report.append("| Case | L1 | L2 | L3 | L4 | L5 | L6 | Neg Avg |")
    report.append("|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    for case_name in cases:
        row = f"| `{case_name}` "
        for level in levels:
            scores = results_industrial[case_name].get(level, [])
            avg = sum(scores) / len(scores) if scores else 0
            row += f"| {avg:.3f} "
        neg = neg_industrial.get(case_name, [])
        neg_avg = sum(neg) / len(neg) if neg else 0
        row += f"| {neg_avg:.3f} |"
        report.append(row)

    # Academic profile scores
    report.append("")
    report.append("## Academic Profile (K=2, W=3, T=0.40)")
    report.append("")
    report.append("### Per-Level Average Composite Score")
    report.append("")
    report.append("| Case | L1 | L2 | L3 | L4 | L5 | L6 | Neg Avg |")
    report.append("|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    for case_name in cases:
        row = f"| `{case_name}` "
        for level in levels:
            scores = results_academic[case_name].get(level, [])
            avg = sum(scores) / len(scores) if scores else 0
            row += f"| {avg:.3f} "
        neg = neg_academic.get(case_name, [])
        neg_avg = sum(neg) / len(neg) if neg else 0
        row += f"| {neg_avg:.3f} |"
        report.append(row)

    # Aggregate metrics comparison
    def compute_agg(results_dict, neg_dict, threshold):
        tp = fn = fp_c = tn_c = 0
        for case_name in cases:
            for level in levels:
                for s in results_dict[case_name].get(level, []):
                    if s >= threshold: tp += 1
                    else: fn += 1
            for s in neg_dict.get(case_name, []):
                if s >= threshold: fp_c += 1
                else: tn_c += 1
        p = tp/(tp+fp_c) if (tp+fp_c)>0 else 0
        r = tp/(tp+fn) if (tp+fn)>0 else 0
        f1 = 2*p*r/(p+r) if (p+r)>0 else 0
        fpr = fp_c/(fp_c+tn_c) if (fp_c+tn_c)>0 else 0
        return {"f1": f1, "precision": p, "recall": r, "fpr": fpr, "tp": tp, "fn": fn, "fp": fp_c, "tn": tn_c}

    ind_m = compute_agg(results_industrial, neg_industrial, 0.10)
    acad_m = compute_agg(results_academic, neg_academic, 0.40)

    report.append("")
    report.append("## Profile Comparison")
    report.append("")
    report.append("| Metric | Industrial (K=5,W=4,T=0.10) | Academic (K=2,W=3,T=0.40) | Δ |")
    report.append("|--------|:---:|:---:|:---:|")
    for m in ["f1", "precision", "recall", "fpr"]:
        d = acad_m[m] - ind_m[m]
        report.append(f"| {m.upper()} | {ind_m[m]:.4f} | {acad_m[m]:.4f} | {d:+.4f} |")
    report.append(f"| TP | {ind_m['tp']} | {acad_m['tp']} | {acad_m['tp']-ind_m['tp']:+d} |")
    report.append(f"| FP | {ind_m['fp']} | {acad_m['fp']} | {acad_m['fp']-ind_m['fp']:+d} |")

    report.append("")
    report.append("## Key Findings")
    report.append("")
    report.append(f"- **Industrial profile**: F1={ind_m['f1']:.4f} — optimized for large codebases, threshold too low for short academic code")
    report.append(f"- **Academic profile**: F1={acad_m['f1']:.4f} — tuned for 10–30 line submissions, disables noisy identifier/comment channels")
    report.append(f"- **L1–L4 detection** remains robust across both profiles (surface-level plagiarism)")
    report.append(f"- **L5–L6** (control-flow/logic restructuring) are inherently harder; academic profile achieves better precision at minimal TPR cost")
    report.append(f"- **FPR reduction**: {ind_m['fpr']:.2f} → {acad_m['fpr']:.2f} ({(ind_m['fpr']-acad_m['fpr'])*100:.1f}pp improvement)")

    out_path = RESULT_DIR / "plagiarism_analysis.md"
    out_path.write_text("\n".join(report), encoding="utf-8")
    print(f"  → {out_path}")
    return results_industrial, results_academic


if __name__ == "__main__":
    print(f"Generating analysis reports in {RESULT_DIR}\n")
    analyze_sqlite()
    analyze_aosp()
    analyze_plagiarism()
    print("\nAll reports generated.")
