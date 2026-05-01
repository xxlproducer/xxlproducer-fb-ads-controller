@echo off
setlocal
chcp 65001 >nul

if not exist "%~dp0backend\.venv" (
  echo First run detected. Running setup...
  call "%~dp0setup.bat"
  if not %errorlevel%==0 exit /b 1
)
if not exist "%~dp0frontend\node_modules" (
  echo Frontend deps missing. Running setup...
  call "%~dp0setup.bat"
  if not %errorlevel%==0 exit /b 1
)

echo.
echo Starting FB Ads Controller...
echo   Backend  : http://127.0.0.1:8080
echo   Frontend : http://localhost:5173
echo.
echo Two new windows will open. Close them to stop the app.
echo.

start "FB Ads Controller Backend" cmd /k "%~dp0_run_backend.bat"
start "FB Ads Controller Frontend" cmd /k "%~dp0_run_frontend.bat"

timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"

echo Done. You can close this window.
timeout /t 3 /nobreak >nul
