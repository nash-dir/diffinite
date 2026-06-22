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
    6. Smoke Test (runs the bundled python.exe -m diffinite --help)
    7. Aggressive Pruning (removes __pycache__, tests, .c/.cpp files, etc.) — last
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
# get-pip.py SHA256 — bootstrap.pypa.io는 항상 최신본을 주는 롤링 URL이라,
# pip 릴리스로 내용이 바뀌면 이 핀을 갱신해야 한다(장기적으로는 버전 고정 스냅샷 권장).
$expectedPipHash = "A341E1A43E38001C551A1508A73FF23636A11970B61D901D9A1CAD2A18F57055"
$pipScriptPath = "$binPythonDir\get-pip.py"

Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $pipScriptPath

Write-Host "Verifying get-pip.py hash..."
$actualPipHash = (Get-FileHash -Path $pipScriptPath -Algorithm SHA256).Hash
if ($actualPipHash -ne $expectedPipHash) {
    throw "Security Exception: get-pip.py hash mismatch! Expected $expectedPipHash, got $actualPipHash"
}

& "$binPythonDir\python.exe" $pipScriptPath --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "Pip bootstrap failed." }

# -------------------------------------------------------------------------
# 4. Install diffinite package and dependencies (Supply-Chain Hardened)
# -------------------------------------------------------------------------
Write-Host "Installing build dependencies (setuptools, wheel)..."
& "$binPythonDir\python.exe" -m pip install setuptools wheel --no-warn-script-location

$sitePackages = "$binPythonDir\Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

# 4a. Install hash-verified dependencies from lock file
$lockFile = "$PSScriptRoot\requirements-bundle.lock"
if (-not (Test-Path $lockFile)) {
    throw "Security Exception: requirements-bundle.lock not found at $lockFile. Run update_lockfile.ps1 first."
}

Write-Host "Installing hash-verified dependencies from lock file..."
Write-Host "  Lock file: $lockFile"
& "$binPythonDir\python.exe" -m pip install `
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
& "$binPythonDir\python.exe" -m pip install `
    --no-deps `
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
# install it into site-packages and strip it (plus its deps) in the final prune
# step (#7); .vscodeignore is a second backstop so it never reaches the VSIX.
Write-Host "Extracting open-source licenses..."
$pythonExeTemplate = "$binPythonDir\python.exe"
& $pythonExeTemplate -m pip install pip-licenses --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "pip-licenses install failed." }

# Enumerate runtime packages, excluding pip/setuptools/wheel and the build-only
# license tooling itself (pip-licenses, prettytable, wcwidth).
$installedPackages = (& $pythonExeTemplate -m pip list --format=freeze) |
                     Where-Object { $_ -notmatch '^(pip|setuptools|wheel|pip-licenses|prettytable|wcwidth)=' } |
                     ForEach-Object { ($_ -split '=')[0] }

# --no-license-path: keep the license TEXT but drop the absolute LicenseFile
# path column. Those paths can resolve to the builder's home dir (e.g. a package
# also present in %APPDATA%\Python), leaking the local username into the public
# VSIX; they are also meaningless on end-user machines.
& $pythonExeTemplate -m piplicenses --with-license-file --no-license-path --format=markdown --output-file="$extRoot\DEPENDENCY_LICENSES.md" --packages $installedPackages
if ($LASTEXITCODE -ne 0) { throw "License extraction failed." }
Write-Host "Licenses saved to DEPENDENCY_LICENSES.md"

# -------------------------------------------------------------------------
# 6. Smoke Test
# -------------------------------------------------------------------------
# Run BEFORE pruning: importing diffinite regenerates __pycache__/*.pyc in
# site-packages, so the prune must be the final step to actually shrink the
# shipped bundle.
Write-Host "Running smoke test on bundled python..."
& "$binPythonDir\python.exe" -m diffinite --help
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
    # Delete dist-info/egg-info (licenses are already collected in step 5)
    Get-ChildItem -Path $path -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*.dist-info" -or $_.Name -like "*.egg-info" } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Prune-Folder $binPythonDir

# Remove pip, setuptools, wheel, and the build-only license tooling
# (pip-licenses + prettytable + wcwidth) — none are used at runtime.
$buildOnlyPatterns = @(
    "pip*", "setuptools*", "wheel*",
    "pip_licenses*", "piplicenses*", "prettytable*", "wcwidth*",
    "_distutils_hack", "distutils-precedence.pth"
)
Get-ChildItem -Path $sitePackages -ErrorAction SilentlyContinue |
    Where-Object { $name = $_.Name; $buildOnlyPatterns | Where-Object { $name -like $_ } } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path "$binPythonDir\Scripts") { Remove-Item "$binPythonDir\Scripts" -Recurse -Force }
if (Test-Path "$binPythonDir\get-pip.py") { Remove-Item "$binPythonDir\get-pip.py" -Force }

Write-Host "=========================================================="
Write-Host "✓ SUCCESS: Bundle built and verified successfully."
Write-Host "Workspace is now configured identically to the Release CD."
Write-Host "=========================================================="
