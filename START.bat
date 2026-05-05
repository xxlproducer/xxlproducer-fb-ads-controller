@echo off
setlocal
chcp 65001 >nul
title FB Ads Controller

cd /d "%~dp0"

REM ---- first run? do setup ----
if not exist "backend\.venv" goto :do_setup
if not exist "frontend\node_modules" goto :do_setup
goto :start

:do_setup
echo First run detected. Running setup (this may take 1-3 minutes)...
echo.
call "%~dp0setup.bat"
if errorlevel 1 (
  echo.
  echo Setup failed. See errors above.
  pause
  exit /b 1
)

:start
echo.
echo ============================================
echo   Starting FB Ads Controller
echo ============================================
echo   Backend  : http://127.0.0.1:8080
echo   Frontend : http://localhost:5173
echo ============================================
echo.
echo Two windows will open (Backend + Frontend).
echo Close them to stop the app.
echo.

start "FB Ads Controller - Backend" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8080"
start "FB Ads Controller - Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

REM ---- wait for frontend to come up, then open browser ----
timeout /t 5 /nobreak >nul
start "" "http://localhost:5173"

echo Done. App is running. You can close this window.
timeout /t 3 /nobreak >nul
