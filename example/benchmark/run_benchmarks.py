"""Reproduce every benchmark quoted in README.md and check it has not drifted.

    python example/download_examples.py          # fetch the pinned datasets first
    python example/benchmark/run_benchmarks.py           # regenerate reports + RESULTS.md + results.json
    python example/benchmark/run_benchmarks.py --check   # re-run and fail if any number differs

Every case runs the real CLI (``python -m diffinite``) with ``--workers 1``.
For each case the runner records:
  * the exact command line,
  * a SHA-256 digest of the input trees (so a reader can tell whether they ran
    on the same bytes; see "Input digest" below),
  * the line-diff and Deep Compare numbers taken from the JSON report.

The calibration figures (false-positive rate, recall, holdout) are produced by
``python -m tests.validation.error_rate`` / ``holdout`` into example/validation/
and are only linked from RESULTS.md, not recomputed here.

Input digest: SHA-256 over the lines "<side>/<relative path>\\t<sha256 of file>", side A then B,
each side ordered by its POSIX relative path string (identical on every platform).
Cases whose inputs are missing are reported as "skipped (dataset not downloaded)".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "example" / "benchmark"
CORPUS = ROOT / "tests" / "validation" / "behaviour_corpus" / "cross-language-and-encoding"

# (id, title, dir A, dir B, extra CLI args, committed Markdown report or None)
CASES = [
    (
        "case_oracle",
        "Google v. Oracle — API declarations (AOSP libcore vs OpenJDK)",
        "example/Case-Oracle/AOSP_Google",
        "example/Case-Oracle/OpenJDK_Oracle",
        ["--strip-comments"],
        "case_oracle.md",
    ),
    (
        "case_negative",
        "Eclipse Collections v. OpenJDK — negative control",
        "example/Case-NegativeControl/Eclipse_Collections",
        "example/Case-NegativeControl/OpenJDK",
        ["--strip-comments"],
        "case_negative.md",
    ),
    (
        "plagiarism_case01",
        "IR-Plag case-01 — labelled plagiarism, calibrated normalize profile",
        "example/plagiarism/case-01/original",
        "example/plagiarism/case-01/plagiarized",
        ["--normalize", "--strip-comments"],
        "plagiarism_case01.md",
    ),
    (
        "aosp",
        "AOSP Handler/Looper/Message — same codebase, minor edits (comments stripped)",
        "example/aosp/left",
        "example/aosp/right",
        ["--strip-comments"],
        "aosp.md",
    ),
    (
        "aosp_comments",
        "AOSP Handler/Looper/Message — comments included (default)",
        "example/aosp/left",
        "example/aosp/right",
        [],
        None,
    ),
    (
        "unicode",
        "Unicode / i18n — non-ASCII names, identifiers and comments",
        "example/unicode/left",
        "example/unicode/right",
        ["--normalize"],
        "unicode.md",
    ),
]
# Cross-language ports and a same-name unrelated control, hand-written behaviour
# corpus (tests/validation/behaviour_corpus/README.md: not calibration data).
# --threshold-deep 0 lists every pair that shares at least one fingerprint (pairs
# with none are never reported); it is a reporting choice, not a decision threshold.
CROSS_LANG_CASES = ["c1_py_to_js", "c2_java_to_kotlin_csharp", "c7_trap_unrelated_cross_lang"]
CROSS_LANG_PROFILES = {
    "raw": ["--threshold-deep", "0"],
    "normalize": ["--normalize", "--strip-comments", "--threshold-deep", "0"],
    "normalize+lang-aware": [
        "--normalize",
        "--lang-aware",
        "--strip-comments",
        "--threshold-deep",
        "0",
    ],
}


def tree_digest(dir_a: Path, dir_b: Path) -> str:
    lines = []
    for side, root in (("A", dir_a), ("B", dir_b)):
        # Sort by the POSIX path string: Path ordering is case-insensitive on Windows
        # and case-sensitive elsewhere, which would make the digest platform-dependent.
        for rel, p in sorted(
            (x.relative_to(root).as_posix(), x) for x in root.rglob("*") if x.is_file()
        ):
            lines.append(f"{side}/{rel}\t{hashlib.sha256(p.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def run_case(dir_a: Path, dir_b: Path, args: list[str], md_out: Path | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="diffinite-bench-") as tmp:
        json_out = Path(tmp) / "r.json"
        cmd = [
            sys.executable,
            "-m",
            "diffinite",
            "--mode",
            "deep",
            *args,
            "--workers",
            "1",
            "--report-json",
            str(json_out),
        ]
        if md_out is None:
            cmd.append("--metrics-only")
        else:
            cmd += ["--report-md", str(md_out)]
        cmd += ["--", str(dir_a), str(dir_b)]
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if proc.returncode != 0:
            raise RuntimeError(f"diffinite failed ({proc.returncode}): {proc.stderr[-800:]}")
        report = json.loads(json_out.read_text(encoding="utf-8"))
    pairs = [
        {
            "file_a": r["file_a"],
            "file_b": r["file_b"],
            "line_match_pct": round(r["ratio"] * 100, 2),
            "added": r["additions"],
            "deleted": r["deletions"],
            "binary": r["binary"],
            "error": r["error"],
        }
        for r in report["results"]
    ]
    deep = [
        {
            "file_a": d["file_a"],
            "file_b": m["file_b"],
            "jaccard_pct": round(m["jaccard"] * 100, 2),
            "a_in_b_pct": None
            if m.get("containment_a_in_b") is None
            else round(m["containment_a_in_b"] * 100, 2),
            "b_in_a_pct": None
            if m.get("containment_b_in_a") is None
            else round(m["containment_b_in_a"] * 100, 2),
            "inconclusive": m.get("inconclusive"),
        }
        for d in (report.get("deep_results") or [])
        for m in d["matches"]
    ]
    deep.sort(key=lambda x: (-x["jaccard_pct"], x["file_a"], x["file_b"]))
    meta = report["metadata"]
    return {
        "unmatched_a": report["summary"]["unmatched_a_count"],
        "unmatched_b": report["summary"]["unmatched_b_count"],
        "analysis_state": report["analysis_status"]["state"],
        "threshold_pct": meta.get("threshold"),
        "threshold_provenance": meta.get("threshold_provenance"),
        "comment_mode": report.get("comment_mode"),
        "pairs": pairs,
        "deep": deep,
    }


def rel_cmd(dir_a: str, dir_b: str, args: list[str], md: str | None) -> str:
    out = f" --report-md example/benchmark/{md}" if md else ""
    return f"python -m diffinite --mode deep {' '.join(args)} --workers 1{out} -- {dir_a} {dir_b}".replace(
        "  ", " "
    )


def collect(write_reports: bool) -> dict:
    cases = {}
    for cid, title, a, b, args, md in CASES:
        da, db = ROOT / a, ROOT / b
        entry = {"title": title, "command": rel_cmd(a, b, args, md)}
        if not (da.is_dir() and db.is_dir()):
            entry["skipped"] = "dataset not downloaded (python example/download_examples.py)"
        else:
            entry["input_digest"] = tree_digest(da, db)
            if md and not write_reports:
                # --check renders the same Markdown into a temp dir so both modes run the
                # identical pipeline (rendering can truncate diff payloads → "incomplete").
                with tempfile.TemporaryDirectory(prefix="diffinite-bench-md-") as tmp_md:
                    entry.update(run_case(da, db, args, Path(tmp_md) / md))
            else:
                entry.update(run_case(da, db, args, BENCH / md if md else None))
        cases[cid] = entry
        print(f"  {cid}: {'skipped' if 'skipped' in entry else 'ok'}")
    cross = {}
    for case in CROSS_LANG_CASES:
        da, db = CORPUS / case / "left", CORPUS / case / "right"
        for prof, args in CROSS_LANG_PROFILES.items():
            key = f"{case}/{prof}"
            res = run_case(da, db, args, None)
            cross[key] = {
                "input_digest": tree_digest(da, db),
                "command": rel_cmd(
                    da.relative_to(ROOT).as_posix(), db.relative_to(ROOT).as_posix(), args, None
                ),
                **res,
            }
        print(f"  cross-language {case}: ok")
    return {"cases": cases, "cross_language": cross}


def environment() -> dict:
    def git(*a: str) -> str:
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
        return r.stdout.strip()

    import diffinite  # noqa: PLC0415 — the version actually run

    return {
        "diffinite_version": diffinite.__version__,
        "git_commit": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--", "src")),
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def fmt(v) -> str:
    return "—" if v is None else f"{v:.1f}%" if isinstance(v, float) else str(v)


def render_md(env: dict, data: dict) -> str:
    out = [
        "# Benchmark results",
        "",
        "Generated by `python example/benchmark/run_benchmarks.py`; verify with `--check`.",
        f"Diffinite {env['diffinite_version']} at commit `{env['git_commit']}`"
        + (" (with uncommitted src/ changes)" if env["git_dirty"] else "")
        + f", Python {env['python']}, {env['platform']}, {env['generated_utc']}.",
        "",
        "These tables report what the tool measured. They do not state whether any code was copied:",
        "line match and Jaccard are textual/token similarity, and interpreting them is the expert's job.",
        "Calibration figures (false-positive rate, recall, holdout) are in",
        "[`example/validation/error_rate.md`](../validation/error_rate.md) and",
        "[`example/validation/holdout.md`](../validation/holdout.md).",
        "",
    ]
    for cid, c in data["cases"].items():
        out += [f"## {c['title']}", "", f"`{c['command']}`", ""]
        if "skipped" in c:
            out += [f"*Skipped: {c['skipped']}.*", ""]
            continue
        out += [
            f"Input digest `{c['input_digest'][:16]}…` · analysis {c['analysis_state']} · "
            f"comments {c['comment_mode']} · deep threshold {fmt(c['threshold_pct'])} ({c['threshold_provenance']}) · "
            f"unmatched {c['unmatched_a']} (A) / {c['unmatched_b']} (B)",
            "",
        ]
        out += ["| File A | File B | Line match | +Added | −Deleted |", "|---|---|---:|---:|---:|"]
        out += [
            f"| `{p['file_a']}` | `{p['file_b']}` | {fmt(p['line_match_pct'])} | {p['added']} | {p['deleted']} |"
            for p in c["pairs"]
        ] or ["| — | — | — | — | — |"]
        out += [
            "",
            "| Deep: File A | File B | Jaccard | A in B | B in A | Inconclusive |",
            "|---|---|---:|---:|---:|:-:|",
        ]
        out += [
            f"| `{d['file_a']}` | `{d['file_b']}` | {fmt(d['jaccard_pct'])} | {fmt(d['a_in_b_pct'])} | "
            f"{fmt(d['b_in_a_pct'])} | {'yes' if d['inconclusive'] else ''} |"
            for d in c["deep"]
        ] or ["| *(no pair at or above the threshold)* | | | | | |"]
        out.append("")
    out += [
        "## Cross-language ports (behaviour corpus, not calibration data)",
        "",
        "Hand-written cases in `tests/validation/behaviour_corpus/cross-language-and-encoding/`",
        "(see its `CASES.md`; written by an AI agent, three cases only). `--threshold-deep 0` lists every",
        "pair that shares at least one fingerprint; pairs with none (Jaccard 0) are omitted.",
        "No threshold is calibrated for cross-language input.",
        "",
        "| Case | Profile | Same-stem line match | Deep Compare Jaccard, every pair with a shared fingerprint (highest first) |",
        "|---|---|---:|---|",
    ]
    for key, c in data["cross_language"].items():
        case, prof = key.split("/")
        lm = (
            ", ".join(f"{p['file_a']}↔{p['file_b']} {fmt(p['line_match_pct'])}" for p in c["pairs"])
            or "—"
        )
        tj = (
            ", ".join(f"{d['file_a']}↔{d['file_b']} {fmt(d['jaccard_pct'])}" for d in c["deep"])
            or "—"
        )
        out.append(f"| {case} | {prof} | {lm} | {tj} |")
    out.append("")
    return "\n".join(out)


def strip_env(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "environment"}


# Every per-case value that results.json records and RESULTS.md publishes.
CHECKED_FIELDS = (
    "title",
    "command",
    "input_digest",
    "pairs",
    "deep",
    "unmatched_a",
    "unmatched_b",
    "analysis_state",
    "threshold_pct",
    "threshold_provenance",
    "comment_mode",
)


def compare_results(committed: dict, data: dict) -> tuple[list[str], list[str], list[str]]:
    """Compare a fresh run with results.json.

    Returns ``(drift, checked, unverified)``: differences, the keys whose numbers
    were re-derived and match, and keys this run could not re-derive because
    the dataset is not downloaded (including keys results.json also records as
    skipped). Nothing is silently passed over: a key present on only one side
    is drift, and every other key is either checked, unverified or drift.
    """
    drift: list[str] = []
    checked: list[str] = []
    unverified: list[str] = []
    for section in ("cases", "cross_language"):
        old_section = committed.get(section, {})
        new_section = data.get(section, {})
        for key in sorted(old_section.keys() | new_section.keys()):
            name = f"{section}/{key}"
            old, now = old_section.get(key), new_section.get(key)
            if now is None:
                drift.append(f"{name}: in results.json but not produced by this run")
                continue
            if old is None:
                drift.append(f"{name}: not in results.json (regenerate it)")
                continue
            if "skipped" in now:
                # Not re-derived by this run. A case that results.json also
                # records as skipped has no committed number either, but it is
                # still not verified: it must not vanish from the summary.
                unverified.append(name)
                continue
            if "skipped" in old:
                drift.append(f"{name}: results.json records it as skipped (regenerate it)")
                continue
            before = len(drift)
            for field in CHECKED_FIELDS:
                if old.get(field) != now.get(field):
                    reason = (
                        "different input bytes" if field == "input_digest" else "result changed"
                    )
                    drift.append(f"{name}: {field} differs ({reason})")
            if len(drift) == before:
                checked.append(name)
    return drift, checked, unverified


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--check", action="store_true", help="re-run and compare with results.json; write nothing"
    )
    ap.add_argument(
        "--allow-skips",
        action="store_true",
        help="with --check, exit 0 even if some committed cases could not be re-run "
        "because their dataset is not downloaded (they are still listed)",
    )
    a = ap.parse_args()
    print("Running benchmarks…")
    data = collect(write_reports=not a.check)
    results_path = BENCH / "results.json"
    if a.check:
        committed = json.loads(results_path.read_text(encoding="utf-8"))
        drift, checked, unverified = compare_results(committed, data)
        if drift:
            print("DRIFT:\n  " + "\n  ".join(drift))
        if unverified:
            print(
                "NOT VERIFIED (dataset not downloaded; run python example/download_examples.py):\n  "
                + "\n  ".join(unverified)
            )
        print(f"{len(checked)} checked, {len(unverified)} not verified, {len(drift)} drifted")
        if drift or (unverified and not a.allow_skips):
            return 1
        print("OK: every checked benchmark reproduces results.json")
        return 0
    env = environment()
    results_path.write_text(
        json.dumps({"environment": env, **data}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (BENCH / "RESULTS.md").write_text(render_md(env, data), encoding="utf-8", newline="\n")
    print(f"Wrote {results_path.relative_to(ROOT)} and RESULTS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
