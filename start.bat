@echo off
cd /d "%~dp0"
echo [Tip] LAN mode: start-lan.bat
call "%~dp0scripts\start-core.bat" local
if errorlevel 1 (
  echo.
  echo [ERROR] 启动失败，请查看上方错误信息。
  echo 若是首次使用，请先运行 bootstrap.bat
  pause
  exit /b 1
)
echo.
echo 服务已在独立窗口中启动（Backend / Frontend）。
echo 请保留 Backend / Frontend 两个窗口运行；关闭它们会停止服务。
echo.
pause
exit /b 0
