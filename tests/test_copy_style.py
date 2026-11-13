"""House style for report text: no decorative typography, English only.

Renders the Markdown, HTML (merged and per-pair) and JSON reports from ASCII
fixtures and checks every byte of user-facing output. The fixtures are ASCII,
so any forbidden character found here comes from Diffinite's own text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from diffinite.cli import main
from diffinite.notices import SCOPE_NOTICE, SHORT_CODE_NOTICE

# Middle dot, em dash, en dash, warning sign, information source, check mark,
# ballot X, and the arrows and glyphs the reports used to carry.
FORBIDDEN = {
    "·": "middle dot",
    "—": "em dash",
    "–": "en dash",
    "⚠": "warning sign",
    "ℹ": "information source",
    "✓": "check mark",
    "✗": "ballot X",
    "→": "right arrow",
    "↔": "left-right arrow",
    "⋯": "midline ellipsis",
    "ⓘ": "circled i",
}
HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")

LEFT = {
    "Ledger.java": (
        "public class Ledger {\n"
        + "".join(f"    int f{i} = {i};\n" for i in range(40))
        + "    int total() { return f1 + f2; }\n}\n"
    ),
    "Tiny.java": "class Tiny { int a; }\n",
    "OnlyA.java": "class OnlyA { void run() { System.out.println(1); } }\n",
}
RIGHT = {
    "Ledger.java": (
        "public class Ledger {\n"
        + "".join(f"    int f{i} = {i};\n" for i in range(40))
        + "    int total() { return f1 + f3; }\n}\n"
    ),
    "Tiny.java": "class Tiny { int b; }\n",
    "OnlyB.java": "class OnlyB { void go() { System.out.println(2); } }\n",
}


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def _outputs(tmp_path: Path, *extra: str) -> dict[str, str]:
    left = _tree(tmp_path / "left", LEFT)
    right = _tree(tmp_path / "right", RIGHT)
    out = tmp_path / "out"
    main(
        [
            str(left),
            str(right),
            "--mode",
            "deep",
            "--hash",
            "--collapse-identical",
            "--report-md",
            str(out / "r.md"),
            "--report-html",
            str(out / "r.html"),
            "--report-json",
            str(out / "r.json"),
            "--workers",
            "1",
            *extra,
        ]
    )
    texts = {
        "markdown": (out / "r.md").read_text(encoding="utf-8"),
        "html": (out / "r.html").read_text(encoding="utf-8"),
        "json": (out / "r.json").read_text(encoding="utf-8"),
    }
    manifests = sorted(out.glob("*manifest.sha256.json"))
    if manifests:
        texts["manifest"] = manifests[0].read_text(encoding="utf-8")
    return texts


def _split_outputs(tmp_path: Path) -> dict[str, str]:
    left = _tree(tmp_path / "left", LEFT)
    right = _tree(tmp_path / "right", RIGHT)
    out = tmp_path / "out"
    main(
        [
            str(left),
            str(right),
            "--mode",
            "deep",
            "--no-merge",
            "--report-html",
            str(out / "r.html"),
            "--workers",
            "1",
        ]
    )
    return {
        str(p.relative_to(out)): p.read_text(encoding="utf-8")
        for p in sorted((out / "r_files").rglob("*.html"))
    }


def _assert_house_style(name: str, text: str) -> None:
    for ch, label in FORBIDDEN.items():
        assert ch not in text, f"{name} contains a {label} (U+{ord(ch):04X})"
    match = HANGUL.search(text)
    assert match is None, (
        f"{name} contains Hangul: {text[max(0, match.start() - 40) : match.end() + 40]!r}"
    )


@pytest.mark.parametrize("extra", [(), ("--normalize", "--strip-comments")])
def test_reports_use_house_style(tmp_path, extra):
    texts = _outputs(tmp_path, *extra)
    for name, text in texts.items():
        _assert_house_style(name, text)


def test_per_pair_and_index_pages_use_house_style(tmp_path):
    pages = _split_outputs(tmp_path)
    assert any(name.endswith("index.html") for name in pages)
    for name, text in pages.items():
        _assert_house_style(name, text)


@pytest.mark.parametrize("extra", [(), ("--normalize", "--strip-comments")])
def test_scope_and_short_code_notices_are_stated_once(tmp_path, extra):
    texts = _outputs(tmp_path, *extra)
    for name in ("markdown", "html"):
        assert texts[name].count(SCOPE_NOTICE) == 1, name
        assert texts[name].count(SHORT_CODE_NOTICE) == 1, name


def test_index_page_carries_the_notices(tmp_path):
    pages = _split_outputs(tmp_path)
    index = next(text for name, text in pages.items() if name.endswith("index.html"))
    assert SCOPE_NOTICE in index
    assert SHORT_CODE_NOTICE in index


def test_normalized_threshold_notice_only_with_normalize(tmp_path):
    raw = _outputs(tmp_path / "raw")
    norm = _outputs(tmp_path / "norm", "--normalize", "--strip-comments")
    for texts in (raw, norm):
        disclosure = json.loads(texts["json"])["metadata"]["calibration_disclosure"]
        assert disclosure in texts["markdown"]
    assert "1 of 105" not in raw["markdown"]
    assert "1 of 105" in norm["markdown"]


def test_integrity_notice_accompanies_the_hash_table(tmp_path):
    texts = _outputs(tmp_path)
    assert "independently retained copy" in texts["html"]
    assert "not a digital signature" in texts["html"]
    manifest = json.loads(texts["manifest"])
    assert "not a digital signature" in manifest["integrity_note"]
