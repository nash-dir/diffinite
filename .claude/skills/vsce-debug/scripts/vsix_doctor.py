#!/usr/bin/env python3
"""Diffinite VS Code extension doctor: catch packaging/runtime/publish problems
before a human has to find them.

Standard library only. Never publishes, never reads or needs a token.

Subcommands (run from the repository root):
  preflight            versions, tool engines, compiled output, `vsce ls` file list
  inspect VSIX         what is inside a packaged VSIX (target, version, bundle, leaks)
  runtime              run the bundled Windows Python and feed its JSON to the
                       extension's own strict parser
  host-smoke VSIX      install the VSIX into a throw-away VS Code profile
  registry [VERSION]   anonymous Marketplace + Open VSX state (network)

Each check prints PASS / WARN / FAIL. Exit code 1 if any FAIL.
Every check below exists because the matching failure already happened in
this repository (see SKILL.md "Failure catalogue").
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EXT = ROOT / "vscode-extension"
PUBLISHER_EXT = "nash-dir.diffinite"
BUNDLED_TARGET = "win32-x64"  # release.yml: only this target ships bin/python
SITE = Path("bin/python/Lib/site-packages")

# Paths that must never be inside the VSIX (relative to the extension root).
FORBIDDEN = [
    (re.compile(r"(^|/)__pycache__/|\.pyc$|\.pyo$"), "Python bytecode cache (F1)"),
    (re.compile(r"\.map$|(?<!\.d)\.ts$"), "TypeScript source or source map (F9)"),
    (re.compile(r"^(src|test|scripts|\.vscode|\.vscode-test|node_modules)/"), "development folder (F9)"),
    (re.compile(r"\.vsix$"), "old VSIX inside the package"),
    (re.compile(r"^bin/python/Scripts/"), "pip launcher scripts (F2)"),
    (re.compile(r"^bin/python/Lib/site-packages/bin/"), "pip --target console-script launchers (F2b)"),
    (re.compile(r"(^|/)(pip|pip_licenses|piplicenses|prettytable|wcwidth|wheel|setuptools|_distutils_hack)(/|\.py$|-)"),
     "build-only Python package (F2)"),
]
# vsce renames README/CHANGELOG/LICENSE inside the VSIX (readme.md, changelog.md,
# LICENSE.txt), so each requirement accepts any of its spellings, case-insensitively.
REQUIRED = [("package.json",), ("out/extension.js",), ("readme.md",), ("license", "license.txt", "license.md"),
            ("changelog.md",)]
LEAK = re.compile(r"[A-Za-z]:\\\\?Users\\\\?[^\\\"'<>\s]+|/home/[a-z][\w-]*/|/Users/[A-Za-z][\w-]*/|%APPDATA%")

failures = 0


def report(level: str, msg: str) -> None:
    global failures
    if level == "FAIL":
        failures += 1
    print(f"{level:4}  {msg}")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def package_version() -> str:
    return read_json(EXT / "package.json")["version"]


def pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else "?"


def bundled_version(ext_root: Path) -> str | None:
    site = ext_root / SITE
    if not site.is_dir():
        return None
    infos = sorted(site.glob("diffinite-*.dist-info"))
    return infos[-1].name[len("diffinite-"):-len(".dist-info")] if infos else "?"


def check_forbidden(paths: list[str], where: str) -> None:
    bad: dict[str, list[str]] = {}
    for p in paths:
        for rx, why in FORBIDDEN:
            if rx.search(p):
                bad.setdefault(why, []).append(p)
                break
    if not bad:
        report("PASS", f"{where}: no forbidden files among {len(paths)}")
    for why, items in bad.items():
        sample = ", ".join(items[:4]) + (" ..." if len(items) > 4 else "")
        report("FAIL", f"{where}: {len(items)} x {why}: {sample}")
    lower = {p.lower() for p in paths}
    for alternatives in REQUIRED:
        if not any(alt in lower for alt in alternatives):
            report("FAIL", f"{where}: required file missing: {alternatives[0]}")


def npx(*args: str, cwd: Path = EXT) -> subprocess.CompletedProcess:
    exe = shutil.which("npx") or shutil.which("npx.cmd")
    if not exe:
        raise FileNotFoundError("npx not found on PATH")
    return subprocess.run([exe, "--no-install", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- preflight
def cmd_preflight(_: argparse.Namespace) -> None:
    pkg, py = package_version(), pyproject_version()
    report("PASS" if pkg == py else "FAIL", f"package.json {pkg} vs pyproject.toml {py}")

    changelog = (EXT / "CHANGELOG.md").read_text(encoding="utf-8")
    report("PASS" if f"[{pkg}]" in changelog else "WARN",
           f"CHANGELOG.md has a [{pkg}] entry (Marketplace Changelog tab, F10)")

    bundled = bundled_version(EXT)
    if bundled is None:
        report("WARN", "no local bin/python bundle: F5 on Windows falls back to diffinite.pythonPath")
    else:
        report("PASS" if bundled == py else "FAIL",
               f"local bundled analyzer {bundled} vs pyproject {py} "
               "(stale bundle = F5 and local packages run an old analyzer; rebuild with scripts/build_bundle.ps1)")

    # Same version is not enough: a bundle rebuilt before the last src/ edit carries the
    # same version string. Compare the installed package's files byte for byte.
    site_pkg = EXT / SITE / "diffinite"
    if site_pkg.is_dir():
        src_pkg = ROOT / "src" / "diffinite"
        differ = []
        for f in sorted(src_pkg.rglob("*.py")):
            rel = f.relative_to(src_pkg)
            other = site_pkg / rel
            if not other.exists() or other.read_bytes() != f.read_bytes():
                differ.append(rel.as_posix())
        report("PASS" if not differ else "FAIL",
               "bundled diffinite sources match src/diffinite" if not differ
               else f"bundled diffinite differs from src/ in {len(differ)} file(s) (rebuild the bundle): {differ[:6]}")

    node = tuple(int(x) for x in re.findall(r"\d+", subprocess.run(
        ["node", "--version"], capture_output=True, text=True).stdout)[:3])
    for tool in ("@vscode/vsce", "ovsx"):
        manifest = EXT / "node_modules" / tool / "package.json"
        if not manifest.exists():
            report("WARN", f"{tool} not installed (run npm ci in vscode-extension)")
            continue
        info = read_json(manifest)
        need = info.get("engines", {}).get("node", "")
        floor = tuple(int(x) for x in re.findall(r"\d+", need)[:1]) or (0,)
        report("PASS" if node[:1] >= floor else "FAIL",
               f"{tool} {info['version']} needs node {need}; have {'.'.join(map(str, node))} (F14)")

    stale = []
    for ts in (EXT / "src").glob("*.ts"):
        js = EXT / "out" / (ts.stem + ".js")
        if not js.exists() or js.stat().st_mtime < ts.stat().st_mtime:
            stale.append(ts.name)
    report("PASS" if not stale else "FAIL",
           "out/ is up to date with src/" if not stale else f"out/ older than src/ (run npm run compile): {stale}")

    try:
        res = npx("vsce", "ls", "--no-dependencies")
    except FileNotFoundError as e:
        report("FAIL", str(e))
        return
    if res.returncode != 0:
        report("FAIL", f"vsce ls failed: {res.stderr.strip()[:300]}")
        return
    paths = [line.strip().replace("\\", "/") for line in res.stdout.splitlines() if line.strip()]
    check_forbidden(paths, "vsce ls (what `vsce package` would include)")


# ---------------------------------------------------------------- inspect
def cmd_inspect(a: argparse.Namespace) -> None:
    vsix = Path(a.vsix)
    z = zipfile.ZipFile(vsix)
    names = z.namelist()
    ext_paths = [n[len("extension/"):] for n in names if n.startswith("extension/") and not n.endswith("/")]
    size_mb = vsix.stat().st_size / 1024 / 1024
    report("PASS", f"{vsix.name}: {len(ext_paths)} files, {size_mb:.1f} MB (size is reported, not judged)")

    root = ET.fromstring(z.read("extension.vsixmanifest"))
    ns = {"v": "http://schemas.microsoft.com/developer/vsx-schema/2011"}
    ident = root.find(".//v:Metadata/v:Identity", ns)
    version = ident.get("Version") if ident is not None else "?"
    target = ident.get("TargetPlatform") if ident is not None else None
    report("PASS" if version == package_version() else "FAIL",
           f"manifest Version {version} vs package.json {package_version()}")
    if a.target:
        report("PASS" if target == a.target else "FAIL", f"manifest TargetPlatform {target} vs expected {a.target}")
    else:
        report("WARN" if target is None else "PASS", f"manifest TargetPlatform = {target or '(none: universal)'}")

    has_bundle = any(p.startswith("bin/python/") for p in ext_paths)
    expect_bundle = (a.target or target) == BUNDLED_TARGET
    report("PASS" if has_bundle == expect_bundle else "FAIL",
           f"bundled Python present={has_bundle}, expected={expect_bundle} for target {target}")
    if has_bundle:
        infos = [p for p in ext_paths if re.match(r"bin/python/Lib/site-packages/diffinite-[^/]+\.dist-info/", p)]
        bundled = infos[0].split("diffinite-")[1].split(".dist-info")[0] if infos else "?"
        report("PASS" if bundled == pyproject_version() else "FAIL",
               f"bundled analyzer {bundled} vs pyproject {pyproject_version()}")

    check_forbidden(ext_paths, "VSIX")

    leaks = []
    for n in names:
        if n.endswith((".md", ".txt", ".json", ".js", ".html", ".xml", ".cfg")) and z.getinfo(n).file_size < 4_000_000:
            text = z.read(n).decode("utf-8", "ignore")
            m = LEAK.search(text)
            if m:
                leaks.append(f"{n}: {m.group(0)[:60]}")
    report("PASS" if not leaks else "FAIL",
           "no local user paths in text files (F8)" if not leaks else f"local paths leaked: {leaks[:5]}")


# ---------------------------------------------------------------- runtime
# -I ignores every PYTHON* variable, so PYTHONIOENCODING=cp1252 has no effect on
# an isolated interpreter. Instead the streams are re-wrapped as strict cp1252
# inside the process before the module runs; a non-cp1252 character in the
# output then raises UnicodeEncodeError and the process exits non-zero.
CP1252_PRELUDE = (
    "import io, sys; "
    "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252', errors='strict'); "
    "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='cp1252', errors='strict'); "
)


def run_help_under_cp1252(py: Path, module: str = "diffinite") -> subprocess.CompletedProcess:
    """Run ``<py> -I -m <module> --help`` with strict cp1252 stdout/stderr."""
    code = (CP1252_PRELUDE + "import runpy; "
            f"sys.argv = [{module!r}, '--help']; "
            f"runpy.run_module({module!r}, run_name='__main__', alter_sys=True)")
    return subprocess.run([str(py), "-I", "-c", code], capture_output=True)


def cmd_runtime(_: argparse.Namespace) -> None:
    py = EXT / "bin" / "python" / "python.exe"
    if not py.exists():
        report("WARN", "no bundled bin/python/python.exe (Windows bundle not built); runtime check skipped")
        return
    ver = subprocess.run([str(py), "-I", "-c", "import diffinite; print(diffinite.__version__)"],
                         capture_output=True, text=True)
    got = ver.stdout.strip()
    report("PASS" if got == pyproject_version() else "FAIL",
           f"bundled `import diffinite` -> {got or ver.stderr.strip()[-200:]} vs pyproject {pyproject_version()}")

    h = run_help_under_cp1252(py)  # F7: legacy console code page
    report("PASS" if h.returncode == 0 else "FAIL",
           f"--help under cp1252 console exit {h.returncode} (F7)"
           + (f": {h.stderr.decode('utf-8', 'replace').strip()[-200:]}" if h.returncode else ""))

    with tempfile.TemporaryDirectory(prefix="vsix-doctor-") as tmp:
        t = Path(tmp)
        (t / "A").mkdir()
        (t / "B").mkdir()
        (t / "A" / "x.py").write_text("def f(a):\n    return a + 1\n", encoding="utf-8")
        (t / "B" / "x.py").write_text("def f(b):\n    return b + 2\n", encoding="utf-8")
        out = t / "r.json"
        run = subprocess.run([str(py), "-I", "-m", "diffinite", "--mode", "deep", "--metrics-only",
                              "--report-json", str(out), "--", str(t / "A"), str(t / "B")],
                             capture_output=True, text=True)
        if run.returncode != 0 or not out.exists():
            report("FAIL", f"sample analysis failed: {run.stderr.strip()[-300:]}")
            return
        # Feed the JSON to the extension's own strict parser (catches schema drift between
        # the bundled analyzer and the TypeScript side).
        model = (EXT / "out" / "analysisModel.js").as_posix()
        js = (f"const m=require({json.dumps(model)});"
              f"m.parseLiveReport(JSON.parse(require('fs').readFileSync({json.dumps(out.as_posix())},'utf8')));"
              "console.log('ok')")
        chk = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        report("PASS" if chk.returncode == 0 else "FAIL",
               "extension parseLiveReport accepts the bundled analyzer's JSON" if chk.returncode == 0
               else f"extension rejects analyzer JSON: {chk.stderr.strip()[-300:]}")


# ---------------------------------------------------------------- host-smoke
def find_code_cli() -> str | None:
    for name in ("code", "code.cmd", "code-insiders", "code-insiders.cmd"):
        p = shutil.which(name)
        if p:
            return p
    return None


def cmd_host_smoke(a: argparse.Namespace) -> None:
    code = find_code_cli()
    if not code:
        report("WARN", "VS Code `code` CLI not on PATH; host smoke skipped")
        return
    with tempfile.TemporaryDirectory(prefix="vsix-host-") as tmp:
        ud, ed = Path(tmp) / "ud", Path(tmp) / "ext"
        base = [code, "--user-data-dir", str(ud), "--extensions-dir", str(ed)]
        inst = subprocess.run([*base, "--install-extension", str(Path(a.vsix).resolve()), "--force"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        report("PASS" if inst.returncode == 0 else "FAIL",
               f"install into isolated profile exit {inst.returncode}: {(inst.stdout + inst.stderr).strip()[-200:]}")
        lst = subprocess.run([*base, "--list-extensions", "--show-versions"], capture_output=True, text=True)
        want = f"{PUBLISHER_EXT}@{package_version()}"
        report("PASS" if want in lst.stdout else "FAIL", f"installed extensions contain {want}: {lst.stdout.strip()}")
        installed = [p for p in ed.glob(f"{PUBLISHER_EXT}-*") if p.is_dir()]
        if installed and (installed[0] / "bin" / "python" / "python.exe").exists():
            report("PASS", "installed copy contains the bundled runtime")
    print("NOTE  Activation and webviews are not exercised by this check; see SKILL.md level 4.")


# ---------------------------------------------------------------- registry
def http_json(url: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "vsix-doctor", **(headers or {})},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_registry(a: argparse.Namespace) -> None:
    expected_targets = {"win32-x64", "linux-x64", "darwin-arm64"}  # release.yml build-vsix matrix
    want = a.version or package_version()
    try:
        # Anonymous gallery query used by `vsce show`; filterType 7 = extension name,
        # flags 17 = include versions + version properties (vsce src/publicgalleryapi.ts).
        res = http_json(
            "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery",
            {"filters": [{"criteria": [{"filterType": 7, "value": PUBLISHER_EXT}], "pageNumber": 1, "pageSize": 1}],
             "flags": 17},
            {"Accept": "application/json;api-version=3.0-preview.1", "Content-Type": "application/json"},
        )
        exts = res["results"][0]["extensions"]
        versions = exts[0]["versions"] if exts else []
        latest = versions[0]["version"] if versions else "none"
        targets = {v.get("targetPlatform") for v in versions if v["version"] == want}
        report("PASS", f"Marketplace latest = {latest}")
        missing = expected_targets - targets
        report("PASS" if not missing else ("WARN" if not targets else "FAIL"),
               f"Marketplace {want}: targets {sorted(t for t in targets if t) or 'none'}"
               + (f", missing {sorted(missing)}" if missing else ""))
    except (urllib.error.URLError, OSError, KeyError, IndexError) as e:
        report("WARN", f"Marketplace query failed (network?): {e}")

    try:
        http_json("https://open-vsx.org/api/nash-dir")
        try:
            ovsx = http_json("https://open-vsx.org/api/nash-dir/diffinite")
            report("PASS", f"Open VSX latest = {ovsx.get('version')} (verified={ovsx.get('verified')})")
        except urllib.error.HTTPError as e:
            report("WARN", f"Open VSX namespace exists but extension not found ({e.code})")
    except urllib.error.HTTPError as e:
        report("WARN", f"Open VSX namespace nash-dir does not exist ({e.code}); publishing there needs the "
                       "owner steps in SKILL.md")
    except (urllib.error.URLError, OSError) as e:
        report("WARN", f"Open VSX query failed (network?): {e}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight").set_defaults(fn=cmd_preflight)
    i = sub.add_parser("inspect")
    i.add_argument("vsix")
    i.add_argument("--target", help="expected TargetPlatform, e.g. win32-x64")
    i.set_defaults(fn=cmd_inspect)
    sub.add_parser("runtime").set_defaults(fn=cmd_runtime)
    h = sub.add_parser("host-smoke")
    h.add_argument("vsix")
    h.set_defaults(fn=cmd_host_smoke)
    r = sub.add_parser("registry")
    r.add_argument("version", nargs="?")
    r.set_defaults(fn=cmd_registry)
    a = p.parse_args()
    a.fn(a)
    print(f"\n{'FAILED' if failures else 'OK'}: {failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
