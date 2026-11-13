"""Regression tests for example/download_examples.py (benchmark dataset fetcher).

No network access: urlopen is replaced by a stub.
"""

from __future__ import annotations

import base64
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "example" / "download_examples.py"


@pytest.fixture(scope="module")
def dl():
    spec = importlib.util.spec_from_file_location("download_examples", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_benchmark_hint_uses_flags_the_cli_accepts(dl, monkeypatch, capsys):
    """The printed follow-up command once used --no-comments, which the CLI rejects."""
    monkeypatch.setattr(dl, "download_dataset", lambda *a, **k: True)
    monkeypatch.setattr("sys.argv", ["download_examples.py", "--dataset", "aosp"])
    assert dl.main() == 0
    hint = [ln for ln in capsys.readouterr().out.splitlines() if "diffinite example/" in ln]
    assert hint, "benchmark hint not printed"
    cli_src = (ROOT / "src" / "diffinite" / "cli.py").read_text(encoding="utf-8")
    for flag in re.findall(r"(?<!\S)(--[a-z][a-z-]*)", hint[0]):
        assert f'"{flag}"' in cli_src, f"hint uses unknown CLI flag {flag}"
    assert "--strip-comments" in hint[0]


def test_gitiles_text_response_is_base64_decoded(dl, monkeypatch, tmp_path):
    payload = b"/*\n * Licensed to the Apache Software Foundation (ASF)\n */\nclass A {}\n"
    monkeypatch.setattr(
        dl.urllib.request,
        "urlopen",
        lambda req, timeout: _FakeResponse(base64.b64encode(payload)),
    )
    dest = tmp_path / "A.java"
    url = "https://android.googlesource.com/platform/libcore/+/" + "0" * 40 + "/A.java?format=TEXT"
    assert dl._download_file(url, dest)
    assert dest.read_bytes() == payload


def test_plain_raw_response_is_written_unchanged(dl, monkeypatch, tmp_path):
    payload = b"class B {}\n"
    monkeypatch.setattr(dl.urllib.request, "urlopen", lambda req, timeout: _FakeResponse(payload))
    dest = tmp_path / "B.java"
    assert dl._download_file("https://raw.githubusercontent.com/x/y/" + "0" * 40 + "/B.java", dest)
    assert dest.read_bytes() == payload


def test_benchmark_sources_are_commit_pinned(dl):
    """Case-Oracle and Case-NegativeControl must not follow a moving branch."""
    for name in ("Case-Oracle", "Case-NegativeControl"):
        for rel, url in dl.DATASETS[name]["files"].items():
            assert re.search(r"/[0-9a-f]{40}/", url), f"{name}/{rel} is not commit-pinned: {url}"
            assert "/master/" not in url and "kitkat-release" not in url


def test_kitkat_string_is_fetched_from_libdvm(dl):
    url = dl.DATASETS["Case-Oracle"]["files"]["AOSP_Google/String.java"]
    assert "/libdvm/src/main/java/java/lang/String.java" in url
    assert dl._is_gitiles_text(url)
