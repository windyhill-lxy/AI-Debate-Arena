@echo off

chcp 65001 >nul 2>&1

setlocal enabledelayedexpansion

set "MODE=%~1"

if not defined MODE set "MODE=local"

cd /d "%~dp0.."



call "%~dp0env.bat"

if errorlevel 1 (

  pause

  exit /b 1

)



if not exist ".env" (

  if exist ".env.example" copy ".env.example" ".env" > nul

)



for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b "BACKEND_PORT=" ".env" 2^>nul`) do set "%%a=%%b"

if not defined BACKEND_PORT set BACKEND_PORT=9000



set "HOST=127.0.0.1"

if /i "!MODE!"=="lan" set "HOST=0.0.0.0"

set "RUN_PATH=%PATH%"



call "%~dp0deps-check.bat"

if "!DEPS_OK!"=="0" (

  if /i "!MODE!"=="school" (

    echo 依赖未就绪，请先运行 bootstrap.bat

    pause

    exit /b 1

  )

  echo [WARN] Python 依赖未完整，尝试快速安装到 tools\python ...

  "%PYTHON_EXE%" -m pip install -q -r "backend\requirements.txt"

  if errorlevel 1 (

    echo [ERROR] 依赖安装失败，请运行 bootstrap.bat

    pause

    exit /b 1

  )

  if exist "backend\requirements-confidence.txt" (

    "%PYTHON_EXE%" -m pip install -q -r "backend\requirements-confidence.txt"

    if errorlevel 1 (

      echo [WARN] 摄像头训练依赖安装失败，辩论核心功能仍可启动。

    )

  )

  echo. > "%TOOLS%\.deps-ready"

)



set "NEED_NPM=0"

if not exist "frontend\node_modules" set "NEED_NPM=1"

if not exist "frontend\node_modules\vite" set "NEED_NPM=1"

if not exist "frontend\node_modules\react" set "NEED_NPM=1"

if not exist "frontend\node_modules\react-dom" set "NEED_NPM=1"

if not exist "frontend\node_modules\lucide-react" set "NEED_NPM=1"

if "!NEED_NPM!"=="1" (

  if /i "!MODE!"=="school" (

    echo 前端依赖不完整，请先运行 bootstrap.bat

    pause

    exit /b 1

  )

  echo 安装前端依赖（仅首次）...

  pushd "frontend"

  call "%NPM_CMD%" install

  popd

  if errorlevel 1 (

    pause

    exit /b 1

  )

)



:launch

echo Checking port availability...

rem --- 后端端口探测（最多尝试 5 个） ---
set /a PORT_TRY=0
:CHECK_BACKEND
netstat -ano | find ":%BACKEND_PORT% " >nul 2>&1
if %errorlevel%==0 (
  set /a PORT_TRY+=1
  if !PORT_TRY! geq 5 (
    echo [ERROR] 找不到可用后端端口（从 %BACKEND_PORT% 起已尝试 5 个）
    pause & exit /b 1
  )
  set /a BACKEND_PORT+=1
  goto CHECK_BACKEND
)

rem --- 前端端口探测（最多尝试 5 个） ---
set "FRONTEND_PORT=5173"
set /a FPORT_TRY=0
:CHECK_FRONTEND
netstat -ano | find ":%FRONTEND_PORT% " >nul 2>&1
if %errorlevel%==0 (
  set /a FPORT_TRY+=1
  if !FPORT_TRY! geq 5 (
    echo [ERROR] 找不到可用前端端口（从 5173 起已尝试 5 个）
    pause & exit /b 1
  )
  set /a FRONTEND_PORT+=1
  goto CHECK_FRONTEND
)

echo Starting backend and frontend...



start "AI Debate Backend" cmd /k "chcp 65001>nul&set PATH=%RUN_PATH%&& cd /d %PROJECT_ROOT%\backend && "%PYTHON_EXE%" -m uvicorn app.main:app --reload --host %HOST% --port %BACKEND_PORT%"



if /i "!MODE!"=="lan" (

  start "AI Debate Frontend (LAN)" cmd /k "chcp 65001>nul&set PATH=%RUN_PATH%&set BACKEND_PORT=%BACKEND_PORT%&set FRONTEND_PORT=%FRONTEND_PORT%&& cd /d %PROJECT_ROOT%\frontend && "%NPM_CMD%" run dev -- --host 0.0.0.0 --port %FRONTEND_PORT%"

) else (

  start "AI Debate Frontend" cmd /k "chcp 65001>nul&set PATH=%RUN_PATH%&set BACKEND_PORT=%BACKEND_PORT%&set FRONTEND_PORT=%FRONTEND_PORT%&& cd /d %PROJECT_ROOT%\frontend && "%NPM_CMD%" run dev -- --port %FRONTEND_PORT%"

)



if /i not "!MODE!"=="lan" (

  start "AI Debate Browser" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\open-when-ready.ps1" -FrontendUrl "http://127.0.0.1:%FRONTEND_PORT%" -BackendUrl "http://127.0.0.1:%BACKEND_PORT%/health"

)



echo.

if /i "!MODE!"=="lan" (

  for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.PrefixOrigin -ne 'WellKnown' } ^| Select-Object -First 1 -ExpandProperty IPAddress); if($ip){$ip}else{'YOUR_LAN_IP'}"`) do set "LAN_IP=%%i"

  echo LAN Backend:  http://!LAN_IP!:%BACKEND_PORT%

  echo LAN Frontend: http://!LAN_IP!:%FRONTEND_PORT%

) else (

  echo Backend:   http://127.0.0.1:%BACKEND_PORT%

  echo Frontend:  http://127.0.0.1:%FRONTEND_PORT%

  echo Browser opens when services are ready.

)

echo Use stop.bat to close services.

endlocal
