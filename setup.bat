@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo ============================================
echo   FB Ads Controller - first time setup
echo ============================================
echo.

REM --- check python ---
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo [ERROR] Python 3.10+ is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/ ^(check "Add Python to PATH"^).
    pause
    exit /b 1
  )
)

REM --- check node ---
where node >nul 2>nul
if not %errorlevel%==0 (
  echo [ERROR] Node.js is not installed or not on PATH.
  echo Install LTS from https://nodejs.org/
  pause
  exit /b 1
)

echo [1/3] Creating Python virtual environment...
pushd "%~dp0backend"
if not exist .venv (
  %PY% -m venv .venv
  if not !errorlevel!==0 (
    echo [ERROR] Failed to create venv.
    popd
    pause
    exit /b 1
  )
)

echo [2/3] Installing backend dependencies...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if not !errorlevel!==0 (
  echo [ERROR] Failed to install backend deps.
  popd
  pause
  exit /b 1
)
call ".venv\Scripts\deactivate.bat"
popd

echo [3/3] Installing frontend dependencies...
pushd "%~dp0frontend"
call npm install
if not !errorlevel!==0 (
  echo [ERROR] Failed to install frontend deps.
  popd
  pause
  exit /b 1
)
popd

echo.
echo ============================================
echo   Setup complete. Run run.bat to start.
echo ============================================
echo.
pause
