@echo off

setlocal

cd /d "%~dp0"



for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b "BACKEND_PORT=" ".env" 2^>nul`) do set "%%a=%%b"

if not defined BACKEND_PORT set BACKEND_PORT=9000



echo =========================================

echo  AI Debate Arena - Stop

echo =========================================

echo.



for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr LISTENING') do (

  echo Stopping backend process %%a

  taskkill /F /PID %%a > nul 2>&1

)



for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr LISTENING') do (

  echo Stopping frontend process %%a

  taskkill /F /PID %%a > nul 2>&1

)



echo.

echo Development services stopped if they were running.

endlocal

