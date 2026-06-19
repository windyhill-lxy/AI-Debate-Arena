@echo off
call "%~dp0scripts\e2e\setup.bat" %*
exit /b %ERRORLEVEL%
