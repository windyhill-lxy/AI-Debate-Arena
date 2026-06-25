# 下载便携 Node.js 与 Python 到 tools/node、tools/python
# 用法：在项目根目录 PowerShell 执行  .\download-portable.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Force -Path (Join-Path $tools "node"), (Join-Path $tools "python") | Out-Null

$nodeVer = "v22.16.0"
$nodeZip = Join-Path $tools "node.zip"
$nodeUrl = "https://nodejs.org/dist/$nodeVer/node-$nodeVer-win-x64.zip"
Write-Host "Downloading Node $nodeVer ..."
Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZip -UseBasicParsing
$nodeExtract = Join-Path $tools "_extract_node"
Remove-Item $nodeExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $nodeZip -DestinationPath $nodeExtract -Force
$nodeFolder = Get-ChildItem $nodeExtract -Directory | Select-Object -First 1
Get-ChildItem (Join-Path $tools "node") -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Path (Join-Path $nodeFolder.FullName "*") -Destination (Join-Path $tools "node") -Recurse -Force
Remove-Item $nodeExtract -Recurse -Force
Remove-Item $nodeZip -Force

$pyTag = "20250205"
$pyFile = "cpython-3.12.9+20250205-x86_64-pc-windows-msvc-install_only.tar.gz"
$pyUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/$pyTag/$pyFile"
$pyTar = Join-Path $tools "python.tar.gz"
Write-Host "Downloading Python 3.12 standalone ..."
Invoke-WebRequest -Uri $pyUrl -OutFile $pyTar -UseBasicParsing
$pyExtract = Join-Path $tools "_extract_python"
Remove-Item $pyExtract -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $pyExtract | Out-Null
tar -xzf $pyTar -C $pyExtract
$pyExe = Get-ChildItem $pyExtract -Recurse -Filter "python.exe" | Select-Object -First 1
if (-not $pyExe) { throw "python.exe not found" }
$pyDir = $pyExe.Directory.FullName
Get-ChildItem (Join-Path $tools "python") -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Path (Join-Path $pyDir "*") -Destination (Join-Path $tools "python") -Recurse -Force
Remove-Item $pyExtract -Recurse -Force
Remove-Item $pyTar -Force

Write-Host ""
Write-Host "Done."
& (Join-Path $tools "node\node.exe") -v
& (Join-Path $tools "python\python.exe") --version
Write-Host "Next: run bootstrap.bat (first time), then start.bat"
