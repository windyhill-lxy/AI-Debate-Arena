@echo off
chcp 65001 >nul 2>&1
rem Fast dependency probe: import check only.
rem Always run this check even when .deps-ready exists.
if not defined PYTHON_EXE call "%~dp0env.bat" python-only
if errorlevel 1 exit /b 1

set "DEPS_OK=0"

"%PYTHON_EXE%" -c "import fastapi,uvicorn,pydantic_settings,motor,redis,langgraph,httpx,yaml,fpdf,qrcode,PIL,cv2,mediapipe; import multipart" >nul 2>&1
if not errorlevel 1 set "DEPS_OK=1"
exit /b 0
