@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0..\.."

echo =========================================
echo  AI Debate Arena - E2E 测试
echo =========================================
echo.

call "%~dp0..\env.bat" python-only
if errorlevel 1 (
  pause
  exit /b 1
)

set "PY=%PYTHON_EXE%"
"%PY%" -c "import playwright" 2>nul
if errorlevel 1 call "%~dp0setup.bat"

for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b "BACKEND_PORT=" ".env" 2^>nul`) do set "%%a=%%b"
if not defined BACKEND_PORT set BACKEND_PORT=9000
set "FRONTEND_PORT=5173"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%"
set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%"

set "NEED_BACKEND=1"
"%PY%" "%~dp0..\e2e_wait_url.py" "%BACKEND_URL%/health" --seconds 2 >nul 2>&1
if not errorlevel 1 set "NEED_BACKEND=0"

if "!NEED_BACKEND!"=="1" (
  echo 启动 E2E 后端...
  start "E2E Backend" /min cmd /c "chcp 65001>nul&cd /d %CD%\backend&&set DEBATE_E2E_MOCK=1&& "%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"
  "%PY%" "%~dp0..\e2e_wait_url.py" "%BACKEND_URL%/health" --seconds 45
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

set "NEED_FRONTEND=1"
"%PY%" "%~dp0..\e2e_wait_url.py" "%FRONTEND_URL%/" --seconds 2 >nul 2>&1
if not errorlevel 1 set "NEED_FRONTEND=0"

if "!NEED_FRONTEND!"=="1" (
  if exist "frontend\dist\index.html" (
    start "E2E Frontend Static" /min cmd /c "chcp 65001>nul&cd /d %CD%&& "%PY%" scripts\serve_frontend_static.py --port %FRONTEND_PORT%"
  ) else (
    call "%~dp0..\env.bat"
    if not errorlevel 1 (
      start "E2E Frontend Dev" /min cmd /c "chcp 65001>nul&cd /d %CD%\frontend&& "%NPM_CMD%" run dev"
    ) else (
      echo [ERROR] 前端未运行且无 frontend\dist
      pause
      exit /b 1
    )
  )
  "%PY%" "%~dp0..\e2e_wait_url.py" "%FRONTEND_URL%/" --seconds 60
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

echo 运行 Playwright E2E ...
set "E2E_FRONTEND_URL=%FRONTEND_URL%"
set "E2E_API_URL=%BACKEND_URL%"
pushd backend
"%PY%" -m pytest tests\e2e -v --tb=short
set "RC=!ERRORLEVEL!"
popd

if "!RC!"=="0" (echo E2E 通过。) else (echo E2E 失败，退出码 !RC!)
pause
exit /b !RC!
