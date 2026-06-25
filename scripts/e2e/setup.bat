@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0..\.."

echo =========================================
echo  AI Debate Arena - E2E 一键安装
echo =========================================
echo.

call "%~dp0..\env.bat" python-only
if errorlevel 1 (
  pause
  exit /b 1
)

echo [1/3] 安装 Python E2E 依赖到 tools\python ...
"%PYTHON_EXE%" -m pip install -q -r "backend\requirements-e2e.txt"
if errorlevel 1 (
  pause
  exit /b 1
)

echo [2/3] 安装 Chromium（首次约 150MB）...
"%PYTHON_EXE%" -m playwright install chromium
if errorlevel 1 (
  pause
  exit /b 1
)

echo [3/3] 检查前端静态资源...
if exist "frontend\dist\index.html" (
  echo frontend\dist 已存在。
) else (
  call "%~dp0..\env.bat"
  if not errorlevel 1 (
    pushd "frontend"
    if not exist "node_modules" call "%NPM_CMD%" install
    if not errorlevel 1 call "%NPM_CMD%" run build
    popd
  )
)

echo.
echo 完成。双击 test-e2e.bat 运行测试。
pause
endlocal
