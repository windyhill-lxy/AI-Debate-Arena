@echo off
cd /d "%~dp0"
call "%~dp0scripts\start-core.bat" lan
exit /b %ERRORLEVEL%
