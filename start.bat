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
echo 本窗口 5 秒后自动关闭，也可按任意键立即关闭。
choice /c YN /d Y /t 5 /m "是否现在关闭本窗口"
exit /b 0
