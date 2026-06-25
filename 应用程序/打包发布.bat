@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"

call "%~dp0scripts\env-pack.bat"
if not "%ERRORLEVEL%"=="0" (
  pause
  exit /b 1
)

echo ========================================
echo   AI Debate Arena - Build release package
echo ========================================
echo.
echo Output: release\AI辩论场\
echo   - AI辩论场.exe
echo   - resources\app-core\  (Python + backend + frontend)
echo   - Electron runtime files
echo.
echo First build may take 5-15 minutes (includes ~470MB Python copy).
echo.

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-release.ps1"
if not "%ERRORLEVEL%"=="0" (
  echo.
  echo [ERROR] Build failed. See messages above.
  pause
  exit /b 1
)

echo.
echo [OK] Build finished.
pause
endlocal
