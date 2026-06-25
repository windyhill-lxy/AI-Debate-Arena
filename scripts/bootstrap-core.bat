@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo =========================================
echo  AI Debate Arena - 首次配置（U盘/新机一次）
echo =========================================
echo.

call "%~dp0env.bat"
if errorlevel 1 exit /b 1

if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" > nul
    echo 已从 .env.example 创建 .env
  ) else (
    echo [ERROR] 缺少 .env，请复制 .env.example 或从家里拷贝 .env
    pause
    exit /b 1
  )
)

echo [1/3] 安装 Python 依赖到 tools\python ...
"%PYTHON_EXE%" -m pip install -q --upgrade pip
"%PYTHON_EXE%" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
  echo pip 安装失败
  pause
  exit /b 1
)

echo [2/3] 安装自信度摄像头依赖（可选）...
"%PYTHON_EXE%" -m pip install -q -r "backend\requirements-confidence.txt"
if errorlevel 1 (
  echo [WARN] 摄像头依赖安装失败，辩论功能仍可用。
) else (
  echo 摄像头依赖已就绪。
)

echo [3/3] 安装前端依赖 ...
pushd "frontend"
if not exist "node_modules" (
  call "%NPM_CMD%" install
  if errorlevel 1 (
    popd
    echo npm install 失败
    pause
    exit /b 1
  )
) else (
  echo node_modules 已存在，跳过。
)
popd

echo. > "%TOOLS%\.deps-ready"
echo.
echo 配置完成。以后直接双击 start.bat 即可，无需再等待 pip。
echo.
pause
endlocal
