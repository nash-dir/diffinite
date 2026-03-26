<#
.SYNOPSIS
    Downloads and bundles Windows Embeddable Python + diffinite dependencies
    into the VS Code extension's bin folder for standalone offline execution.

.DESCRIPTION
    This script encapsulates the exact steps used in the CD (Continuous Deployment)
    release pipeline. Running this locally serves as a robust tester to ensure
    the VS CE deployment bundle will work perfectly in production.

    Steps:
    1. Downloads & Extracts Python Embeddable zip
    2. Enables 'import site' in ._pth
    3. Bootstraps pip
    4. Installs the local 'diffinite' package to target folder
    5. Extracts Dependency Licenses
    6. Aggressive Pruning (removes __pycache__, tests, .c/.cpp files, etc.)
    7. Smoke Test (runs the bundled python.exe -m diffinite --help)
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

Write-Host "Downloading Embedded Python v$pythonVersion..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath

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
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$binPythonDir\get-pip.py"
& "$binPythonDir\python.exe" "$binPythonDir\get-pip.py" --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "Pip bootstrap failed." }

# -------------------------------------------------------------------------
# 4. Install diffinite package and dependencies
# -------------------------------------------------------------------------
Write-Host "Installing build dependencies (setuptools, wheel)..."
& "$binPythonDir\python.exe" -m pip install setuptools wheel --no-warn-script-location

Write-Host "Installing diffinite & dependencies into target folder..."
$sitePackages = "$binPythonDir\Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

& "$binPythonDir\python.exe" -m pip install --target $sitePackages --no-warn-script-location $workspaceRoot
if ($LASTEXITCODE -ne 0) { throw "Diffinite installation failed." }

# -------------------------------------------------------------------------
# 5. Extract Dependency Licenses
# -------------------------------------------------------------------------
Write-Host "Extracting open-source licenses..."
& "$binPythonDir\python.exe" -m pip install pip-licenses --no-warn-script-location
$pythonExeTemplate = "$binPythonDir\python.exe"

# Get all installed non-system packages
$installedPackages = (& $pythonExeTemplate -m pip list --format=freeze) | 
                     Where-Object { $_ -notmatch '^(pip|setuptools|wheel)=' } | 
                     ForEach-Object { ($_ -split '=')[0] }
$packagesArg = $installedPackages -join " "

& $pythonExeTemplate -m piplicenses --with-license-file --format=markdown --output-file="$extRoot\DEPENDENCY_LICENSES.md" --packages $installedPackages
if ($LASTEXITCODE -ne 0) { throw "License extraction failed." }
Write-Host "Licenses saved to DEPENDENCY_LICENSES.md"

# -------------------------------------------------------------------------
# 6. Aggressive Pruning (Size Optimization)
# -------------------------------------------------------------------------
Write-Host "Pruning unnecessary files and caches..."

# Prune function
function Prune-Folder {
    param([string]$path)
    if (Test-Path $path) {
        # Delete __pycache__, tests, examples
        Get-ChildItem -Path $path -Recurse -Directory -Include "__pycache__", "tests", "test", "examples" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
        # Delete compiled generic caches and unused sources
        Get-ChildItem -Path $path -Recurse -File -Include "*.pyc", "*.c", "*.cpp", "*.h" -ErrorAction SilentlyContinue | Remove-Item -Force
        # Delete dist-info/egg-info (licenses are already collected)
        Get-ChildItem -Path $path -Recurse -Directory -Include "*.dist-info", "*.egg-info" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    }
}

Prune-Folder $binPythonDir

# Remove pip, setuptools, and Scripts directory (not needed at runtime)
Get-ChildItem -Path $sitePackages -Directory -Include "pip*", "setuptools*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
if (Test-Path "$binPythonDir\Scripts") { Remove-Item "$binPythonDir\Scripts" -Recurse -Force }
if (Test-Path "$binPythonDir\get-pip.py") { Remove-Item "$binPythonDir\get-pip.py" -Force }

# -------------------------------------------------------------------------
# 7. Smoke Test
# -------------------------------------------------------------------------
Write-Host "Running smoke test on bundled python..."
& "$binPythonDir\python.exe" -m diffinite --help
if ($LASTEXITCODE -ne 0) { throw "Smoke test failed! The bundled Python architecture is broken." }

Write-Host "=========================================================="
Write-Host "✓ SUCCESS: Bundle built and verified successfully."
Write-Host "Workspace is now configured identically to the Release CD."
Write-Host "=========================================================="
