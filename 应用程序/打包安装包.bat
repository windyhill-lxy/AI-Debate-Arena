@echo off
chcp 65001 >nul 2>&1
setlocal

cd /d "%~dp0"

call "%~dp0scripts\env-pack.bat"
if not "%ERRORLEVEL%"=="0" (
  pause
  exit /b 1
)

echo ========================================
echo   AI Debate Arena - Build Windows installer
echo ========================================
echo.
echo Output:
echo   release\AI辩论场-1.0.0-Windows-安装包.exe
echo.
echo The installer can choose install path and includes Python/backend/frontend/Electron runtime.
echo Local .env secrets are not bundled by default.
echo.
echo First build may take 5-15 minutes.
echo.

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-release.ps1" -Installer
if not "%ERRORLEVEL%"=="0" (
  echo.
  echo [ERROR] Installer build failed. See messages above.
  pause
  exit /b 1
)

echo.
echo [OK] Installer build finished.
pause
endlocal
