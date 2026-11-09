---
name: vsce-debug
description: Debug and pre-flight the Diffinite VS Code extension (VSIX packaging, bundled Windows Python runtime, Extension Development Host, VS Code Marketplace and Open VSX state) with automated checks. Use when the extension misbehaves after a change, before tagging a release, after a release run, when a publish job is red, or when asked about vsce / ovsx / Open VSX / Marketplace / VSIX contents. Never publishes and never handles tokens.
---

# vsce-debug — Diffinite extension debugging and publish pre-flight

Every check here exists because the matching failure already happened in this
repository (catalogue below). Run the cheapest level that can answer the
question, then go up.

## Hard rules

- **Never publish, unpublish, or create a namespace.** `vsce publish`, `ovsx publish`,
  `ovsx create-namespace`, `vsce unpublish` are owner-only. So are `vsce verify-pat` and
  `ovsx verify-pat`: they need a token, and an agent must not read, ask for, or pass one.
- Network checks (level 5) are anonymous public reads only.
- Do not "fix" a failing check by loosening it. Report it.
- The script prints facts; it does not judge VSIX size (no budget number exists with a
  stated reason; AGENTS.md forbids unexplained constants).

## The doctor script

`python .claude/skills/vsce-debug/scripts/vsix_doctor.py <command>` from the repo root.
Standard library only. Prints PASS / WARN / FAIL; exit 1 if any FAIL.

> Python choice: on this workstation the `.venv-ci` interpreter is blocked from the
> network by the firewall (WinError 10013). Use the system `python` for `registry`;
> any interpreter works for the other commands.

| Level | Command | Needs | Catches |
|---|---|---|---|
| 1 | `preflight` | `npm ci` done | version drift (package.json / pyproject / CHANGELOG / **local bundle**), Node vs vsce/ovsx engines, `out/` older than `src/`, forbidden or missing files in `vsce ls` |
| 2 | `inspect <vsix> --target <t>` | a packaged VSIX | manifest Version/TargetPlatform, bundle only in win32-x64, bundled analyzer version, forbidden files, local user paths leaked into text files |
| 3 | `runtime` | Windows bundle in `bin/` | bundled `import diffinite` version, `--help` under a cp1252 console, sample analysis JSON accepted by the extension's own strict `parseLiveReport` |
| 3b | `host-smoke <vsix>` | `code` CLI | VSIX installs into a throw-away profile and lists as `nash-dir.diffinite@<version>` with its runtime |
| 4 | `npm run test:host` (in vscode-extension) | installed VS Code | see Level 4 below |
| 5 | `registry [version]` | network | Marketplace latest + which of win32-x64 / linux-x64 / darwin-arm64 exist for that version (`vsce show` hides per-target gaps); Open VSX namespace/extension state |

Package a VSIX for level 2 the same way CI does:

```bash
cd vscode-extension && npx --no-install vsce package --target win32-x64 --no-dependencies --allow-star-activation --out ../tmp/check.vsix
```

`vsce ls` (3.2.2) has no `--target`; `preflight` lists the win32 view because the local
`bin/` is included. Linux/darwin VSIXs are built in release.yml only; inspect the
release artifacts for those.

## Level 4 — inside a real VS Code Extension Host (automated)

```bash
cd vscode-extension && npm run test:host                       # extension from source (out/)
cd vscode-extension && node test/host/run.js --vsix ../tmp/check.vsix   # the packaged VSIX
```

`test/host/run.js` starts the locally installed VS Code binary (`Code.exe`, not the
`code` launcher, which returns immediately) with a throw-away `--user-data-dir` /
`--extensions-dir`, `--disable-extensions` and `--disable-workspace-trust`, and
runs `test/host/index.js` through VS Code's own `--extensionTestsPath`. No npm
dependency and no VS Code download. It checks, inside the host:

- activation and the three commands; Help and Analysis webview tabs open
- Phase 1 and Phase 2 analysis through `runner.ts` and the bundled analyzer
- Tree Viewer and Result Viewer panels build from a live report
- PDF export with the Technical and Evidence presets (PDF + manifest written;
  the Evidence run uses Bates suffix `-CONFIDENTIAL`)
- the binary-exclude regression and cancellation classification

Each step is written to the result file as it starts, so a hang shows where it
stopped. The run prints the extension-host log folder
(`<tmp>/ud/logs/<ts>/window1/exthost/exthost.log`; the "Diffinite" output
channel is under `window1/output_<ts>/`).

Not covered: clicking inside webviews (selection, filter, export buttons), the
save dialog, and Linux/macOS hosts. For those, use F5 with `vscode-extension/`
opened as the workspace ("Run Extension" launch config) and the same log paths.

## Owner-only actions (give the user this checklist, do not run)

- **Marketplace token retirement:** the official publishing page states global Azure
  DevOps PATs are retired on **2026-12-01**. `release.yml` publishes with `VSCE_PAT`.
  Moving to GitHub Actions Trusted Publishing (`vsce publish --oidc`, `id-token: write`,
  a trusted publishing policy in the Marketplace, and a vsce newer than the pinned
  3.2.2) is the owner's decision.
- Before a release: `npx vsce verify-pat nash-dir` (owner's token) so a bad token fails
  before any target is uploaded.
- **Open VSX** (intentionally not published since 0.12.2; namespace `nash-dir` returns 404):
  Eclipse account → sign the Open VSX Publisher Agreement → create a token →
  `ovsx create-namespace nash-dir` → claim ownership via an issue at
  github.com/EclipseFdn/open-vsx.org → add the `OVSX_PAT` secret. Until then the
  release step skips silently (green run, nothing published).
- Publish retries in `release.yml` have no `--skip-duplicate`; a retry after a
  server-side success fails with "already exists". Verify with `registry` instead of
  re-running the job.

## Failure catalogue → check

| # | Past failure (commit / note) | Detected by |
|---|---|---|
| F1 | Prune no-op shipped ~12 MB `__pycache__`/`.pyc` | preflight, inspect |
| F2 | Build-only packages (pip-licenses, wheel, …) shipped | preflight, inspect |
| F2b | `pip --target` console launchers in `site-packages/bin/*.exe` shipped | preflight, inspect |
| F3 | Rolling `get-pip.py` hash broke the CD job | CI bundle job (not this script) |
| F7 | cp1252 console `UnicodeEncodeError` (3 times) | runtime |
| F8 | Local user paths in `DEPENDENCY_LICENSES.md` / lock headers | inspect |
| F9 | `.ts`, `.map`, `scripts/`, `.vscode/` in the VSIX | preflight, inspect |
| F10 | Stale CHANGELOG on the Marketplace tab | preflight |
| F13 | Open VSX `Unknown publisher: nash-dir` after other registries published | registry |
| F14 | vsce/ovsx need newer Node | preflight |
| F15/F16 | vsce flag churn, upload timeout | run the exact release `vsce package` line (above) |
| F17 | macOS symlinks broke packaging | release darwin job (not reproducible on Windows) |
| — | Stale local bundle: F5 and local VSIX run an older analyzer than the extension | preflight (version **and** byte-for-byte source comparison), inspect and runtime (version only) |
| — | Analyzer JSON schema rejected by the extension (e.g. Python < 0.14) | runtime |
| — | A target missing on the Marketplace after a partial publish | registry |

## Reporting

Report each FAIL with the check line, the likely cause from the catalogue, and the
fix owner (code change here vs owner action). Then apply the AGENTS.md direction check.
