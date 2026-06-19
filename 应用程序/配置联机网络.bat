@echo off
setlocal EnableExtensions

set "PS1=%~dp0..\scripts\setup-firewall.ps1"
if not exist "%PS1%" (
  set "PS1=%~dp0scripts\setup-firewall.ps1"
)
if not exist "%PS1%" (
  cd /d "%~dp0.."
  set "PS1=%CD%\scripts\setup-firewall.ps1"
)
if not exist "%PS1%" (
  echo [ERROR] setup-firewall.ps1 not found.
  echo Tried parent folder scripts\setup-firewall.ps1
  pause
  exit /b 1
)

echo.
echo AI Debate Arena - Firewall setup
echo Allows TCP 5173 / 9000 and cloudflared outbound.
echo If UAC appears, click Yes to run as Administrator.
echo.

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo Finished with errors. Try: right-click this file - Run as administrator
)
pause
endlocal
