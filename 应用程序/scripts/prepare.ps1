# AI Debate Arena - prepare desktop assets (ASCII-only for PS 5.1 encoding safety)
param(
    [string]$PackRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = "Stop"
$frontendDir = Join-Path $ProjectRoot "frontend"
$distDir = Join-Path $frontendDir "dist"
$assetsDir = Join-Path $PackRoot "assets\frontend-dist"
$stagingDir = Join-Path $PackRoot "assets\_staging-frontend-dist"
$electronDir = Join-Path $PackRoot "electron"
$npm = Join-Path $ProjectRoot "tools\node\npm.cmd"
$pythonExe = Join-Path $ProjectRoot "tools\python\python.exe"
$nodeDir = Join-Path $ProjectRoot "tools\node"
$pythonDir = Join-Path $ProjectRoot "tools\python"

function Ensure-PortablePath {
    $env:PATH = "$pythonDir;$pythonDir\Scripts;$nodeDir;$env:PATH"
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Stop-PackServices {
    & (Join-Path $PSScriptRoot "stop.ps1") -IncludeElectron
    Start-Sleep -Seconds 1
}

function Sync-FrontendDist {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $stagingDir) {
        Remove-Item -Recurse -Force $stagingDir -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $stagingDir -Recurse -Force

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $null = & robocopy $stagingDir $Destination /MIR /NFL /NDL /NJH /NJS /nc /ns /np
    $robocopyCode = $LASTEXITCODE
    if ($robocopyCode -ge 8) {
        throw "robocopy failed (code $robocopyCode). Close running app, then run prepare again."
    }

    Remove-Item -Recurse -Force $stagingDir -ErrorAction SilentlyContinue
    $global:LASTEXITCODE = 0
}

if (-not (Test-Path $npm) -or -not (Test-Path $pythonExe)) {
    Write-Step "Missing portable runtime, trying download-portable + bootstrap"
    $downloadScript = Join-Path $ProjectRoot "download-portable.ps1"
    if (Test-Path $downloadScript) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $downloadScript
    }
    $bootstrap = Join-Path $ProjectRoot "scripts\bootstrap-core.bat"
    if (Test-Path $bootstrap) {
        cmd /c "`"$bootstrap`""
    }
}

if (-not (Test-Path $npm)) {
    throw "npm.cmd not found: $npm. Run bootstrap.bat in project root first."
}

Write-Step "Stop desktop services (ports 9000/5173, Electron)"
Stop-PackServices

Ensure-PortablePath

Write-Step "npm install frontend (skip if already installed)"
Push-Location $frontendDir
& $npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }

Write-Step "Build frontend (same UI as web)"
& $npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm run build failed" }
Pop-Location

$distIndex = Join-Path $distDir "index.html"
if (-not (Test-Path $distIndex)) {
    throw "Build failed: missing $distIndex"
}

Write-Step "Copy dist to assets\frontend-dist"
try {
    Sync-FrontendDist -Source $distDir -Destination $assetsDir
}
catch {
    Write-Host ""
    Write-Host "Copy failed, retrying after stop..." -ForegroundColor Yellow
    Stop-PackServices
    Sync-FrontendDist -Source $distDir -Destination $assetsDir
}

Write-Step "Patch packaged JS strings (desktop wording)"
$jsFiles = Get-ChildItem -Path $assetsDir -Recurse -Filter "*.js" -File
$replacements = @{
    "start-lan.bat" = "desktop app (launch bat)"
    "start.bat"     = "this app"
}
foreach ($file in $jsFiles) {
    $text = [System.IO.File]::ReadAllText($file.FullName)
    $changed = $false
    foreach ($key in $replacements.Keys) {
        if ($text.Contains($key)) {
            $text = $text.Replace($key, $replacements[$key])
            $changed = $true
        }
    }
    if ($changed) {
        [System.IO.File]::WriteAllText($file.FullName, $text)
    }
}

Write-Step "Install Electron shell"
Push-Location $electronDir
& $npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "electron npm install failed" }
Pop-Location

Write-Host ""
Write-Host "Done. Run launch bat to start desktop app." -ForegroundColor Green
