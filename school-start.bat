@echo off
echo [Tip] school-start.bat is localhost mode. Use start-lan.bat for LAN.
call "%~dp0scripts\start-core.bat" school
exit /b %ERRORLEVEL%
