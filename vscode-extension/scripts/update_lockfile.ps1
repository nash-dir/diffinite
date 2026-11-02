<#
.SYNOPSIS
    Regenerates the requirements-bundle.lock file with pinned versions and SHA256 hashes.

.DESCRIPTION
    Uses pip-compile (from pip-tools) under Python 3.12 to resolve runtime
    dependencies from pyproject.toml and build-only dependencies from
    requirements-build.in. Both outputs pin exact versions and PyPI SHA256 hashes.

    Prerequisites:
      pip install pip-tools==7.6.0

.EXAMPLE
    .\update_lockfile.ps1
    .\update_lockfile.ps1 -Upgrade   # resolve latest compatible versions
#>
param(
    [switch]$Upgrade,
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$workspaceRoot = (Resolve-Path "$scriptDir\..\..").Path
$requirementsIn = "$workspaceRoot\pyproject.toml"
$lockFile = "$scriptDir\requirements-bundle.lock"
$buildRequirementsIn = "$scriptDir\requirements-build.in"
$buildLockFile = "$scriptDir\requirements-build.lock"
$pythonCommand = (Get-Command $PythonExecutable -ErrorAction Stop).Source

foreach ($requiredInput in @($requirementsIn, $buildRequirementsIn)) {
    if (-not (Test-Path $requiredInput)) {
        throw "Lock input not found at: $requiredInput"
    }
}

# Release uses Python 3.12.9; marker evaluation and compatible wheels must be
# resolved with the same Python 3.12 runtime family.
$resolverVersion = & $pythonCommand -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $resolverVersion -ne "3.12") {
    throw "Lock regeneration requires Python 3.12; detected $resolverVersion"
}

# pip-tools 7.6.0 is the reviewed resolver used to generate the committed lock
# format; a different resolver version can select or serialize a different set.
$expectedPipToolsVersion = "7.6.0"
$actualPipToolsVersion = & $pythonCommand -c "from importlib.metadata import version; print(version('pip-tools'))"
if ($LASTEXITCODE -ne 0 -or $actualPipToolsVersion -ne $expectedPipToolsVersion) {
    throw "Lock regeneration requires pip-tools $expectedPipToolsVersion; detected $actualPipToolsVersion. Run: pip install pip-tools==$expectedPipToolsVersion"
}

$compileArgs = @(
    "-m", "piptools", "compile",
    "--generate-hashes",
    "--output-file=vscode-extension\scripts\requirements-bundle.lock",
    "--strip-extras",
    "--resolver=backtracking"
)

if ($Upgrade) {
    $compileArgs += "--upgrade"
    Write-Host "Upgrading all dependencies to latest compatible versions..."
}

$compileArgs += "pyproject.toml"

Write-Host "Resolving dependencies and generating hashes..."
Write-Host "Input:  $requirementsIn"
Write-Host "Output: $lockFile"

Push-Location $workspaceRoot
try {
    & $pythonCommand @compileArgs
    if ($LASTEXITCODE -ne 0) { throw "pip-compile failed. Check dependency conflicts." }

    $buildCompileArgs = @(
        "-m", "piptools", "compile",
        "--generate-hashes",
        "--allow-unsafe",
        "--output-file=vscode-extension\scripts\requirements-build.lock",
        "--strip-extras",
        "--resolver=backtracking"
    )
    if ($Upgrade) { $buildCompileArgs += "--upgrade" }
    $buildCompileArgs += "vscode-extension\scripts\requirements-build.in"
    & $pythonCommand @buildCompileArgs
    if ($LASTEXITCODE -ne 0) { throw "Build-tool pip-compile failed." }
} finally {
    Pop-Location
}

$lineCount = (Get-Content $lockFile).Count
$pkgCount = (Select-String -Path $lockFile -Pattern "^[a-zA-Z]" | Measure-Object).Count

Write-Host ""
Write-Host "=========================================================="
Write-Host "Lock file generated successfully."
Write-Host "  Packages pinned: $pkgCount"
Write-Host "  Total lines:     $lineCount"
Write-Host "  Build lock:      $buildLockFile"
Write-Host "=========================================================="
Write-Host ""
Write-Host "IMPORTANT: Review changes and commit the updated lock file."
Write-Host "  git diff vscode-extension/scripts/requirements-*.lock"
