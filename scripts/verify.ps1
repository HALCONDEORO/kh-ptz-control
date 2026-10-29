param(
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$runtimeDir = Join-Path $repoRoot ".pytest-runtime"
New-Item -ItemType Directory -Force $runtimeDir | Out-Null

$env:QT_QPA_PLATFORM = "offscreen"
if (-not $env:HALLPTZ_DATA_DIR) {
    $env:HALLPTZ_DATA_DIR = Join-Path $runtimeDir "data"
}

if ($InstallDeps) {
    python -m pip install --upgrade pip
    python -m pip install -r requirements-dev.txt
}

python -m pytest --basetemp (Join-Path $runtimeDir "basetemp")
