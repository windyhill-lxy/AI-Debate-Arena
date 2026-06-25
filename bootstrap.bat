@echo off
cd /d "%~dp0"
call "%~dp0scripts\bootstrap-core.bat"
exit /b %ERRORLEVEL%
