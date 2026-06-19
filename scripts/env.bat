@echo off
chcp 65001 >nul 2>&1
rem 统一运行时：仅使用 tools\python 与 tools\node，不回退系统 PATH。
set "PROJECT_ROOT=%~dp0.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"
set "TOOLS=%PROJECT_ROOT%\tools"
set "PYTHON_EXE=%TOOLS%\python\python.exe"
set "NODE_EXE=%TOOLS%\node\node.exe"
set "NPM_CMD=%TOOLS%\node\npm.cmd"
set "NPX_CMD=%TOOLS%\node\npx.cmd"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] 未找到 %TOOLS%\python\python.exe
  echo 请先运行 download-portable.ps1 或 bootstrap.bat
  exit /b 1
)

set "PATH=%TOOLS%\python;%TOOLS%\python\Scripts;%PATH%"

if /i not "%~1"=="python-only" (
  if not exist "%NODE_EXE%" (
    echo [ERROR] 未找到 %TOOLS%\node\node.exe
    echo 请先运行 download-portable.ps1 或 bootstrap.bat
    exit /b 1
  )
  set "PATH=%TOOLS%\node;%PATH%"
)

exit /b 0
