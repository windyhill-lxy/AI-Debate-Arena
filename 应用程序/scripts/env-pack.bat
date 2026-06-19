@echo off
chcp 65001 >nul 2>&1
set "PACK_ROOT=%~dp0.."
for %%I in ("%PACK_ROOT%") do set "PACK_ROOT=%%~fI"
set "PROJECT_ROOT=%PACK_ROOT%\.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"
set "TOOLS=%PROJECT_ROOT%\tools"
set "PYTHON_EXE=%TOOLS%\python\python.exe"
set "NODE_EXE=%TOOLS%\node\node.exe"
set "NPM_CMD=%TOOLS%\node\npm.cmd"
set "NPX_CMD=%TOOLS%\node\npx.cmd"
set "ELECTRON_DIR=%PACK_ROOT%\electron"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Portable Python not found: %PYTHON_EXE%
  echo Run bootstrap.bat in project root first.
  exit /b 1
)

if not exist "%NODE_EXE%" (
  echo [ERROR] Portable Node not found: %NODE_EXE%
  echo Run bootstrap.bat in project root first.
  exit /b 1
)

set "PATH=%TOOLS%\python;%TOOLS%\python\Scripts;%TOOLS%\node;%PATH%"
exit /b 0
