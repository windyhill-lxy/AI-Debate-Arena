@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"

call "%~dp0scripts\env-pack.bat"
if not "%ERRORLEVEL%"=="0" (
  echo.
  pause
  exit /b 1
)

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\preflight.ps1" -Repair
if not "%ERRORLEVEL%"=="0" (
  echo [WARN] Preflight reported issues; will still try to start.
)

if not exist "%PACK_ROOT%\assets\frontend-dist\index.html" (
  echo [INFO] First run: preparing frontend assets and Electron...
  call "%~dp0准备程序.bat"
  if not "%ERRORLEVEL%"=="0" exit /b 1
)

if not exist "%ELECTRON_DIR%\node_modules\electron\package.json" (
  echo [INFO] Installing Electron shell...
  pushd "%ELECTRON_DIR%"
  call "%NPM_CMD%" install
  popd
  if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Electron install failed
    pause
    exit /b 1
  )
)

rem Release ports / Electron if still running
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" -IncludeElectron >nul 2>&1

echo Starting AI Debate Arena (desktop + LAN)...
pushd "%ELECTRON_DIR%"
call "%NPM_CMD%" run start
set "EXIT_CODE=!ERRORLEVEL!"
popd

if not "!EXIT_CODE!"=="0" (
  echo.
  echo [ERROR] App exited with code !EXIT_CODE!
  pause
)

for /f %%I in ("!EXIT_CODE!") do (
  endlocal
  exit /b %%~I
)
