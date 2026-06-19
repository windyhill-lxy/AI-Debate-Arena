@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PS1=%~dp0scripts\setup-firewall.ps1"
if not exist "%PS1%" (
  echo [ERROR] Not found: %PS1%
  echo Please run this file from the project root folder.
  pause
  exit /b 1
)

echo.
echo AI Debate Arena - Firewall setup
echo Allows TCP 5173 / 9000 and cloudflared outbound.
echo If UAC appears, click Yes to run as Administrator.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo Finished with errors. Try: right-click this file - Run as administrator
)
pause
endlocal
