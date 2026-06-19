@echo off
call "%~dp0scripts\e2e\test.bat" %*
exit /b %ERRORLEVEL%
