# AI Debate Arena - startup preflight (ASCII-only for PS 5.1 encoding safety)
param(
    [string]$PackRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [switch]$Repair
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}

$python = Join-Path $ProjectRoot "tools\python\python.exe"
$npm = Join-Path $ProjectRoot "tools\node\npm.cmd"
$frontendDistPack = Join-Path $PackRoot "assets\frontend-dist\index.html"
$requirements = Join-Path $ProjectRoot "backend\requirements.txt"

$issues = @()

if (-not (Test-Path $python)) {
    $issues += "Missing Python: $python"
}

if (-not (Test-Path $frontendDistPack)) {
    $issues += "Missing frontend-dist: $frontendDistPack (run prepare.bat)"
}

if ($issues.Count -gt 0 -and $Repair) {
    Write-Step "Auto-repair dependencies"
    if (-not (Test-Path $python)) {
        $downloadScript = Join-Path $ProjectRoot "download-portable.ps1"
        if (Test-Path $downloadScript) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $downloadScript
        }
        $bootstrap = Join-Path $ProjectRoot "scripts\bootstrap-core.bat"
        if (Test-Path $bootstrap) {
            cmd /c "`"$bootstrap`""
        }
    }
    if (-not (Test-Path $frontendDistPack) -and (Test-Path $npm)) {
        $prepare = Join-Path $PackRoot "scripts\prepare.ps1"
        if (Test-Path $prepare) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $prepare
        }
    }
    $issues = @()
    if (-not (Test-Path $python)) { $issues += "Python still missing" }
    if (-not (Test-Path $frontendDistPack)) { $issues += "frontend-dist still missing" }
}

if ((Test-Path $python) -and (Test-Path $requirements) -and $Repair) {
    Write-Step "Check Python packages"
    & $python -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing backend requirements..." -ForegroundColor Yellow
        & $python -m pip install -q -r $requirements
    }
}

if ($issues.Count -gt 0) {
    Write-Host ""
    Write-Host "[preflight] FAILED:" -ForegroundColor Red
    foreach ($item in $issues) { Write-Host "  - $item" }
    exit 1
}

Write-Host "[preflight] OK" -ForegroundColor Green
exit 0
