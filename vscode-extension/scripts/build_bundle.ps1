<#
.SYNOPSIS
    Downloads and bundles Windows Embeddable Python + diffinite dependencies
    into the VS Code extension's bin folder for standalone offline execution.

.DESCRIPTION
    This script encapsulates the exact steps used in the CD (Continuous Deployment)
    release pipeline. Running this locally serves as a robust tester to ensure
    the VS CE deployment bundle will work perfectly in production.

    Steps:
    1. Downloads & Extracts Python Embeddable zip (SHA256 verified)
    2. Enables 'import site' in ._pth
    3. Bootstraps pip (SHA256 verified)
    4. Installs dependencies with --require-hashes (supply-chain hardened)
       4a. Hash-verified PyPI deps from requirements-bundle.lock
       4b. Local diffinite package (--no-deps)
    5. Extracts Dependency Licenses (build-only pip-licenses in a temp dir)
    6. Pre-prune Smoke Test (runs the bundled python.exe -m diffinite --help)
    7. Aggressive Pruning (removes __pycache__, tests, .c/.cpp files, etc.)
    8. Post-prune Version & Report Smoke Tests
#>
param(
    [string]$pythonVersion = "3.12.9"
)

$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$extRoot = "$workspaceRoot\vscode-extension"
$binPythonDir = "$extRoot\bin\python"

# Reset directory
if (Test-Path $binPythonDir) {
    Write-Host "Cleaning existing bundle directory..."
    Remove-Item $binPythonDir -Recurse -Force
}
New-Item -ItemType Directory -Path $binPythonDir | Out-Null

# -------------------------------------------------------------------------
# 1. Download & Extract Embedded Python
# -------------------------------------------------------------------------
$downloadUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
$zipPath = "$binPythonDir\python-embed.zip"
# 공식 Python 3.12.9 릴리스 SHA256 해시값 (python.org 제공)
$expectedPythonHash = "615861FB801E8B04C847598DB4E1E46E4B046295017CAA37CB5486DDE72B5865"

Write-Host "Downloading Embedded Python v$pythonVersion..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath

Write-Host "Verifying Python zip hash..."
$actualPythonHash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash
if ($actualPythonHash -ne $expectedPythonHash) {
    throw "Security Exception: Python download hash mismatch! Expected $expectedPythonHash, got $actualPythonHash"
}

Write-Host "Extracting Python..."
Expand-Archive -Path $zipPath -DestinationPath $binPythonDir -Force
Remove-Item $zipPath

# -------------------------------------------------------------------------
# 2. Enable 'import site'
# -------------------------------------------------------------------------
# Important: Embedded python disables site-packages by default. We must enable it.
$pthFiles = Get-ChildItem -Path $binPythonDir -Filter "python*._pth"
foreach ($pth in $pthFiles) {
    $content = [System.IO.File]::ReadAllText($pth.FullName)
    $content = $content -replace '#import site', 'import site'
    [System.IO.File]::WriteAllText($pth.FullName, $content, [System.Text.Encoding]::ASCII)
    Write-Host "Enabled 'import site' in $($pth.Name)"
}

# -------------------------------------------------------------------------
# 3. Bootstrap Pip
# -------------------------------------------------------------------------
Write-Host "Bootstrapping pip..."
# pip is bootstrapped from its own wheel at an immutable PyPI file URL, pinned by
# SHA-256. (bootstrap.pypa.io/get-pip.py is a rolling URL whose content changes
# with every pip release, so a pinned hash for it breaks the build each time.)
# pip-audit on 2026-11-03: 26.1.2 has PYSEC-2026-3721 (fixed in 26.2); 26.2.2
# (released 2026-10-20) has no known advisories.
$expectedPipVersion = "26.2.2"
$pipWheelName = "pip-$expectedPipVersion-py3-none-any.whl"
$pipWheelUrl = "https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/$pipWheelName"
$expectedPipWheelHash = "FD7F4DFA8190E014013B9F08F3E973F4E4C26FFD179A204895533A7254813A70"
$pipWheelPath = "$binPythonDir\$pipWheelName"

Invoke-WebRequest -Uri $pipWheelUrl -OutFile $pipWheelPath

Write-Host "Verifying pip wheel hash..."
$actualPipWheelHash = (Get-FileHash -Path $pipWheelPath -Algorithm SHA256).Hash
if ($actualPipWheelHash -ne $expectedPipWheelHash) {
    throw "Security Exception: pip wheel hash mismatch! Expected $expectedPipWheelHash, got $actualPipWheelHash"
}

# Run pip from inside its verified wheel to install that same wheel (no index).
# Isolated mode blocks PYTHON* environment variables, user-site packages, and
# the current directory from influencing any code run by the bundled runtime;
# the wheel is therefore put on sys.path explicitly rather than relied on as
# an implicit script directory.
$pipBootstrap = "import sys; sys.path.insert(0, sys.argv[1]); " +
    "from pip._internal.cli.main import main; " +
    "sys.exit(main(['install', '--no-index', '--no-warn-script-location', sys.argv[1]]))"
& "$binPythonDir\python.exe" -I -c $pipBootstrap $pipWheelPath
if ($LASTEXITCODE -ne 0) { throw "Pip bootstrap failed." }
Remove-Item $pipWheelPath -Force
$actualPipVersion = & "$binPythonDir\python.exe" -I -c "from importlib.metadata import version; print(version('pip'))"
if ($LASTEXITCODE -ne 0 -or $actualPipVersion -ne $expectedPipVersion) {
    throw "Security Exception: expected bootstrap pip $expectedPipVersion, got $actualPipVersion"
}

# -------------------------------------------------------------------------
# 4. Install diffinite package and dependencies (Supply-Chain Hardened)
# -------------------------------------------------------------------------
$buildLockFile = "$PSScriptRoot\requirements-build.lock"
if (-not (Test-Path $buildLockFile)) {
    throw "Security Exception: requirements-build.lock not found at $buildLockFile. Run update_lockfile.ps1 first."
}

Write-Host "Installing hash-verified build and license tools..."
& "$binPythonDir\python.exe" -I -m pip install `
    --require-hashes `
    --no-deps `
    --no-warn-script-location `
    -r $buildLockFile
if ($LASTEXITCODE -ne 0) {
    throw "Security Exception: Build-tool hash verification failed."
}

$sitePackages = "$binPythonDir\Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

# 4a. Install hash-verified dependencies from lock file
$lockFile = "$PSScriptRoot\requirements-bundle.lock"
if (-not (Test-Path $lockFile)) {
    throw "Security Exception: requirements-bundle.lock not found at $lockFile. Run update_lockfile.ps1 first."
}

Write-Host "Installing hash-verified dependencies from lock file..."
Write-Host "  Lock file: $lockFile"
& "$binPythonDir\python.exe" -I -m pip install `
    --require-hashes `
    --no-deps `
    --target $sitePackages `
    --no-warn-script-location `
    -r $lockFile
if ($LASTEXITCODE -ne 0) {
    throw "Security Exception: Dependency hash verification failed! A package may have been tampered with."
}

# 4b. Install diffinite itself (local source, no deps — already hash-verified above)
Write-Host "Installing diffinite package (local source, --no-deps)..."
& "$binPythonDir\python.exe" -I -m pip install `
    --no-deps `
    --no-build-isolation `
    --target $sitePackages `
    --no-warn-script-location `
    $workspaceRoot
if ($LASTEXITCODE -ne 0) { throw "Diffinite installation failed." }

# -------------------------------------------------------------------------
# 5. Extract Dependency Licenses
# -------------------------------------------------------------------------
# pip-licenses is a BUILD-ONLY tool, but it (and prettytable/wcwidth) must be
# importable by the bundled interpreter to enumerate license metadata. The
# embedded Python is driven by a `._pth` file, which makes it ignore PYTHONPATH
# and any --target dir, so it can only import from site-packages. We therefore
# install it from the hash-verified build lock and strip it (plus its deps) in
# the final prune step (#7); .vscodeignore is a second backstop.
Write-Host "Extracting open-source licenses..."
$pythonExeTemplate = "$binPythonDir\python.exe"

# The lock is the runtime dependency source of truth. Enumerating the whole
# interpreter can leak unrelated build-host packages into the license inventory.
$installedPackages = @(
    Select-String -Path $lockFile -Pattern '^([a-zA-Z0-9_.-]+)==' |
        ForEach-Object { $_.Matches[0].Groups[1].Value }
) + @('diffinite')
$expectedLicensePackages = @{}
foreach ($installedPackage in $installedPackages) {
    $canonicalInstalledPackage = $installedPackage.ToLowerInvariant() -replace '[-_.]+', '-'
    $expectedLicensePackages[$canonicalInstalledPackage] = $true
}

# --no-license-path: keep the license TEXT but drop the absolute LicenseFile
# path column. Those paths can resolve to the builder's home dir (e.g. a package
# also present in %APPDATA%\Python), leaking the local username into the public
# VSIX; they are also meaningless on end-user machines.
& $pythonExeTemplate -I -m piplicenses --with-license-file --no-license-path --format=markdown --output-file="$extRoot\DEPENDENCY_LICENSES.md" --packages $installedPackages
if ($LASTEXITCODE -ne 0) { throw "License extraction failed." }

# Python -I prevents a same-named user-site distribution or sitecustomize from
# contaminating the inventory. Packages whose wheels omit a license file must
# have a vetted, version-bound source license checked into third-party-licenses/.
$inventoryPath = "$extRoot\DEPENDENCY_LICENSES.md"
$inventoryLines = @(Get-Content -Path $inventoryPath)
$seenLicensePackages = @{}
$licenseEncoding = New-Object System.Text.UTF8Encoding($false)

for ($lineIndex = 0; $lineIndex -lt $inventoryLines.Count; $lineIndex++) {
    $cells = @($inventoryLines[$lineIndex] -split '\|')
    if ($cells.Count -lt 6) { continue }

    $packageName = $cells[1].Trim()
    $packageVersion = $cells[2].Trim()
    if (-not $packageName -or $packageName -eq "Name" -or $packageName -match '^-+$') {
        continue
    }

    $canonicalName = $packageName.ToLowerInvariant() -replace '[-_.]+', '-'
    if ($seenLicensePackages.ContainsKey($canonicalName)) {
        throw "Duplicate package in dependency license inventory: $packageName"
    }
    $seenLicensePackages[$canonicalName] = $true

    if ($cells[4].Trim() -eq "UNKNOWN") {
        $fallbackRelative = "third-party-licenses/$canonicalName-$packageVersion.txt"
        $fallbackPath = Join-Path $extRoot ($fallbackRelative -replace '/', '\')
        if (-not (Test-Path $fallbackPath -PathType Leaf) -or
            (Get-Item $fallbackPath).Length -eq 0) {
            throw "Missing vetted license fallback for $packageName $packageVersion at $fallbackPath"
        }
        $cells[4] = " See $fallbackRelative "
        $inventoryLines[$lineIndex] = $cells -join '|'
    }
}

$missingLicensePackages = @(
    $expectedLicensePackages.Keys |
        Where-Object { -not $seenLicensePackages.ContainsKey($_) } |
        Sort-Object
)
if ($missingLicensePackages.Count -gt 0) {
    throw "Missing package from dependency license inventory: $($missingLicensePackages -join ', ')"
}

$unexpectedLicensePackages = @(
    $seenLicensePackages.Keys |
        Where-Object { -not $expectedLicensePackages.ContainsKey($_) } |
        Sort-Object
)
if ($unexpectedLicensePackages.Count -gt 0) {
    throw "Unexpected package in dependency license inventory: $($unexpectedLicensePackages -join ', ')"
}

[System.IO.File]::WriteAllLines($inventoryPath, $inventoryLines, $licenseEncoding)
Write-Host "Licenses saved to DEPENDENCY_LICENSES.md"

# -------------------------------------------------------------------------
# 6. Smoke Test
# -------------------------------------------------------------------------
# Run BEFORE pruning: importing diffinite regenerates __pycache__/*.pyc in
# site-packages, so the prune must be the final step to actually shrink the
# shipped bundle.
Write-Host "Running smoke test on bundled python..."
& "$binPythonDir\python.exe" -I -m diffinite --help
if ($LASTEXITCODE -ne 0) { throw "Smoke test failed! The bundled Python architecture is broken." }

# -------------------------------------------------------------------------
# 7. Aggressive Pruning (Size Optimization) — must be the LAST step
# -------------------------------------------------------------------------
Write-Host "Pruning unnecessary files and caches..."

# Prune function.
# NOTE: Get-ChildItem -Include is a no-op unless -Path ends in '\*'; the prior
# version silently pruned nothing and leaked ~12 MB of __pycache__/.pyc into the
# VSIX. Filter with Where-Object on the piped items instead.
function Prune-Folder {
    param([string]$path)
    if (-not (Test-Path $path)) { return }
    # Delete __pycache__, tests, examples directories
    Get-ChildItem -Path $path -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @("__pycache__", "tests", "test", "examples") } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    # Delete compiled caches and unused C/C++ sources
    Get-ChildItem -Path $path -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".pyc", ".pyo", ".c", ".cpp", ".h") } |
        Remove-Item -Force -ErrorAction SilentlyContinue
    # Preserve diffinite's dist-info: importlib.metadata is the authoritative
    # runtime version source used in evidence manifests. Other metadata is not
    # needed after the dependency license inventory has been generated.
    Get-ChildItem -Path $path -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -like "*.dist-info" -and $_.Name -notlike "diffinite-*.dist-info") -or
            $_.Name -like "*.egg-info"
        } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Prune-Folder $binPythonDir

# Keep only the package name/version record needed by importlib.metadata.
# direct_url.json otherwise records the absolute CI checkout path in the VSIX.
$diffiniteDistInfo = @(
    Get-ChildItem -Path $sitePackages -Directory -Filter "diffinite-*.dist-info" -ErrorAction SilentlyContinue
)
if ($diffiniteDistInfo.Count -ne 1) {
    throw "Expected exactly one diffinite dist-info directory after pruning, found $($diffiniteDistInfo.Count)."
}
Get-ChildItem -LiteralPath $diffiniteDistInfo[0].FullName -Force |
    Where-Object { $_.Name -ne "METADATA" } |
    Remove-Item -Recurse -Force
if (-not (Test-Path (Join-Path $diffiniteDistInfo[0].FullName "METADATA") -PathType Leaf)) {
    throw "diffinite METADATA is missing after pruning."
}

# Remove pip, setuptools, wheel, and the build-only license tooling
# (pip-licenses + prettytable + wcwidth) — none are used at runtime.
$buildOnlyPatterns = @(
    "pip*", "setuptools*", "wheel*", "build*", "packaging*",
    "pyproject_hooks*", "colorama*",
    "pip_licenses*", "piplicenses*", "prettytable*", "wcwidth*",
    "_distutils_hack", "distutils-precedence.pth"
)
Get-ChildItem -Path $sitePackages -ErrorAction SilentlyContinue |
    Where-Object { $name = $_.Name; $buildOnlyPatterns | Where-Object { $name -like $_ } } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path "$binPythonDir\Scripts") { Remove-Item "$binPythonDir\Scripts" -Recurse -Force }

# -------------------------------------------------------------------------
# 8. Post-prune Version & Tiny Report Verification
# -------------------------------------------------------------------------
# The release artifact is only valid if pruning preserved both version
# provenance and the complete report-generation path used by the extension.
Write-Host "Running post-prune bundle verification..."

$versionMatch = Select-String -Path "$workspaceRoot\pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if ($null -eq $versionMatch) { throw "Could not read the project version from pyproject.toml." }
$expectedVersion = $versionMatch.Matches[0].Groups[1].Value

& "$binPythonDir\python.exe" -I -c 'import sys; from diffinite import __version__; expected = sys.argv[1]; assert __version__ == expected, (__version__, expected)' $expectedVersion
if ($LASTEXITCODE -ne 0) {
    throw "Post-prune version check failed. diffinite package metadata was not preserved."
}

$smokeRoot = Join-Path $binPythonDir "_post_prune_smoke"
$sourceA = Join-Path $smokeRoot "source-a"
$sourceB = Join-Path $smokeRoot "source-b"
$reportPath = Join-Path $smokeRoot "report.json"
$pdfPath = Join-Path $smokeRoot "report.pdf"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

try {
    New-Item -ItemType Directory -Path $sourceA, $sourceB -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $sourceA "sample.py"), "def value():`n    return 1`n", $utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $sourceB "sample.py"), "def value():`n    return 2`n", $utf8NoBom)

    # One worker is the documented minimum and keeps this release smoke test
    # deterministic on constrained GitHub-hosted Windows runners.
    & "$binPythonDir\python.exe" -I -m diffinite $sourceA $sourceB `
        --report-json $reportPath `
        --report-pdf $pdfPath `
        --workers 1
    if ($LASTEXITCODE -ne 0) { throw "Post-prune JSON/PDF report generation failed." }
    if (-not (Test-Path $reportPath -PathType Leaf)) {
        throw "Post-prune report generation did not create report.json."
    }
    if (-not (Test-Path $pdfPath -PathType Leaf)) {
        throw "Post-prune report generation did not create report.pdf."
    }

    $smokeReport = Get-Content -Path $reportPath -Raw | ConvertFrom-Json
    if ($null -eq $smokeReport.schema_version -or
        $null -eq $smokeReport.summary -or
        $smokeReport.analysis_status.state -ne "complete") {
        throw "Post-prune report.json failed its schema/completeness smoke check."
    }

    # The PDF contract requires both serialized bytes and at least one readable page.
    & "$binPythonDir\python.exe" -I -c 'import sys; from pathlib import Path; from pypdf import PdfReader; path = Path(sys.argv[1]); reader = PdfReader(path); assert path.stat().st_size > 0 and len(reader.pages) > 0' $pdfPath
    if ($LASTEXITCODE -ne 0) {
        throw "Post-prune report.pdf is empty or unreadable."
    }
}
finally {
    if (Test-Path $smokeRoot) { Remove-Item $smokeRoot -Recurse -Force }
}

Write-Host "=========================================================="
Write-Host "✓ SUCCESS: Bundle built and verified successfully."
Write-Host "Workspace is now configured identically to the Release CD."
Write-Host "=========================================================="
