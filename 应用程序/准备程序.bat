@echo off
chcp 65001 >nul 2>&1
setlocal

cd /d "%~dp0"

echo ========================================
echo   AI Debate Arena - Prepare desktop assets
echo ========================================
echo.

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare.ps1"
if not "%ERRORLEVEL%"=="0" (
  echo.
  echo [ERROR] Prepare failed. See messages above.
  pause
  exit /b 1
)

echo.
echo [OK] Prepare finished.
pause
endlocal
