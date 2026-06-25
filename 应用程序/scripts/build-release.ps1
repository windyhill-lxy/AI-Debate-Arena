param(
    [string]$PackRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [switch]$SkipPrepare,
    [switch]$Portable
)

$ErrorActionPreference = "Stop"
$stagingRoot = Join-Path $PackRoot "release\staging"
$appCore = Join-Path $stagingRoot "app-core"
$distOut = Join-Path $PackRoot "release\dist"
$finalDir = Join-Path $PackRoot "release\AI辩论场"
$npm = Join-Path $ProjectRoot "tools\node\npm.cmd"
$pythonExe = Join-Path $ProjectRoot "tools\python\python.exe"
$electronDir = Join-Path $PackRoot "electron"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Invoke-Robocopy {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirs = @()
    )
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $xd = @()
    foreach ($dir in $ExcludeDirs) {
        $xd += "/XD"
        $xd += $dir
    }
    $args = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np") + $xd
    $null = & robocopy @args
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy 失败（$Source -> $Destination，错误码 $LASTEXITCODE）"
    }
    $global:LASTEXITCODE = 0
}

function Test-PortablePython {
    if (-not (Test-Path $pythonExe)) {
        throw "未找到 $pythonExe ，请先在项目根目录运行 bootstrap.bat"
    }
    & $pythonExe -c "import uvicorn, fastapi" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "便携 Python 缺少后端依赖，请在项目根目录运行 bootstrap.bat 或 pip install -r backend\requirements.txt"
    }
}

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  AI 辩论场 · 打包独立发行版 (exe + 依赖)" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Write-Step "停止可能占用的进程"
& (Join-Path $PSScriptRoot "stop.ps1") -IncludeElectron
Start-Sleep -Seconds 1

if (-not $SkipPrepare) {
    Write-Step "构建前端资源"
    & (Join-Path $PSScriptRoot "prepare.ps1")
}

Write-Step "检查便携 Python"
Test-PortablePython

Write-Step "清理并创建 staging 目录"
if (Test-Path $stagingRoot) {
    Remove-Item -Recurse -Force $stagingRoot -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $appCore -Force | Out-Null

Write-Step "复制后端 (backend/) — 约 1–2 分钟"
$backendSrc = Join-Path $ProjectRoot "backend"
$backendDst = Join-Path $appCore "backend"
Invoke-Robocopy -Source $backendSrc -Destination $backendDst -ExcludeDirs @(
    "tests", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"
)

Write-Step "复制便携 Python (tools/python/) — 约 3–8 分钟，体积较大"
$pythonSrc = Join-Path $ProjectRoot "tools\python"
$pythonDst = Join-Path $appCore "python"
Invoke-Robocopy -Source $pythonSrc -Destination $pythonDst -ExcludeDirs @(
    "__pycache__", "test", "tests"
)

Write-Step "复制前端静态资源"
$frontendSrc = Join-Path $PackRoot "assets\frontend-dist"
$frontendDst = Join-Path $appCore "frontend-dist"
Invoke-Robocopy -Source $frontendSrc -Destination $frontendDst

Write-Step "复制 SPA 服务脚本（含 API 代理，支持公网穿透）"
$scriptsDst = Join-Path $appCore "scripts"
New-Item -ItemType Directory -Path $scriptsDst -Force | Out-Null
$serveUnifiedSrc = Join-Path $PackRoot "scripts\serve_unified.py"
if (-not (Test-Path $serveUnifiedSrc)) {
    throw "缺少桌面端统一启动脚本 $serveUnifiedSrc"
}
Copy-Item -Path $serveUnifiedSrc -Destination $scriptsDst -Force

Write-Step "准备 cloudflared（公网穿透）"
$toolsDst = Join-Path $appCore "tools"
New-Item -ItemType Directory -Path $toolsDst -Force | Out-Null
$cloudflaredDst = Join-Path $toolsDst "cloudflared.exe"
$cloudflaredLocal = Join-Path $ProjectRoot "tools\cloudflared.exe"
if (Test-Path $cloudflaredLocal) {
    Copy-Item -Path $cloudflaredLocal -Destination $cloudflaredDst -Force
} else {
    try {
        Write-Host "  下载 cloudflared …" -ForegroundColor Gray
        Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cloudflaredDst -UseBasicParsing
    } catch {
        Write-Host "  [WARN] cloudflared 下载失败，首次开启公网穿透时将自动重试" -ForegroundColor Yellow
    }
}

Write-Step "准备配置与数据目录"
New-Item -ItemType Directory -Path (Join-Path $appCore "data") -Force | Out-Null
$envExample = Join-Path $ProjectRoot ".env.example"
$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envExample)) {
    throw "缺少 $envExample"
}
Copy-Item -Path $envExample -Destination (Join-Path $appCore ".env.example") -Force
if (Test-Path $envFile) {
    Copy-Item -Path $envFile -Destination (Join-Path $appCore ".env") -Force
    Write-Host "  已复制项目 .env 到发行包（含 API 密钥）" -ForegroundColor Gray
} else {
    Write-Host "  [WARN] 未找到项目 .env，发行包仅含 .env.example" -ForegroundColor Yellow
}

Write-Step "安装 electron-builder（若未安装）"
Push-Location $electronDir
& $npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install 失败" }
Pop-Location

Write-Step "运行 electron-builder 生成 exe 与依赖文件"
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
Push-Location $electronDir
if ($Portable) {
    & $npm run build:win:portable
} else {
    & $npm run build:win
}
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "electron-builder 失败" }
Pop-Location

Write-Step "整理输出目录"
$winUnpacked = Join-Path $distOut "win-unpacked"
if (-not (Test-Path $winUnpacked)) {
    throw "未找到构建输出：$winUnpacked"
}

if (Test-Path $finalDir) {
    Remove-Item -Recurse -Force $finalDir -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $finalDir -Force | Out-Null
Copy-Item -Path (Join-Path $winUnpacked "*") -Destination $finalDir -Recurse -Force

$readmeSrc = Join-Path $PackRoot "release\使用说明.txt"
Copy-Item -Path $readmeSrc -Destination (Join-Path $finalDir "使用说明.txt") -Force

$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Copy-Item -Path $envFile -Destination (Join-Path $finalDir ".env") -Force
}

Write-Step "校验发行包关键文件"
$requiredReleaseFiles = @(
    (Join-Path $finalDir "AI辩论场.exe"),
    (Join-Path $finalDir "resources\app-core\python\python.exe"),
    (Join-Path $finalDir "resources\app-core\backend\app\main.py"),
    (Join-Path $finalDir "resources\app-core\backend\requirements.txt"),
    (Join-Path $finalDir "resources\app-core\frontend-dist\index.html"),
    (Join-Path $finalDir "resources\app-core\scripts\serve_unified.py"),
    (Join-Path $finalDir "resources\app-core\.env.example"),
    (Join-Path $finalDir ".env.example"),
    (Join-Path $finalDir "使用说明.txt")
)
$missingReleaseFiles = @($requiredReleaseFiles | Where-Object { -not (Test-Path $_) })
if ($missingReleaseFiles.Count -gt 0) {
    throw "发行包缺少关键文件：`n$($missingReleaseFiles -join "`n")"
}

$frontendAssetsDir = Join-Path $finalDir "resources\app-core\frontend-dist\assets"
if (-not (Test-Path $frontendAssetsDir)) {
    throw "发行包缺少前端 assets 目录：$frontendAssetsDir"
}

$releaseCloudflared = Join-Path $finalDir "resources\app-core\tools\cloudflared.exe"
if (-not (Test-Path $releaseCloudflared)) {
    Write-Host "  警告：发行包缺少 cloudflared.exe，公网隧道方式可能不可用。" -ForegroundColor Yellow
}

$portableExe = Get-ChildItem -Path $distOut -Filter "AI辩论场-*-便携单文件.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portableExe) {
    Copy-Item -Path $portableExe.FullName -Destination (Join-Path $PackRoot "release\$($portableExe.Name)") -Force
}

$totalSize = (Get-ChildItem $finalDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
$sizeMb = [math]::Round($totalSize / 1MB, 1)

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  打包完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "发行目录：$finalDir" -ForegroundColor White
Write-Host "主程序：  $finalDir\AI辩论场.exe" -ForegroundColor White
Write-Host "总体积：  约 ${sizeMb} MB" -ForegroundColor White
Write-Host ""
Write-Host "可将整个「AI辩论场」文件夹复制到其他 Windows 电脑直接运行。" -ForegroundColor Gray
Write-Host "首次使用请编辑同目录 .env.example → 另存为 .env 并填入 API 密钥。" -ForegroundColor Gray
Write-Host ""
