@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo ============================================
echo   FB Ads Controller - first time setup
echo ============================================
echo.

REM --- pick Python: prefer 3.12 / 3.13 / 3.11 / 3.10, fall back to default ---
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%V -V >nul 2>nul
    if not errorlevel 1 (
      set "PY=py -%%V"
      echo Using Python %%V via launcher.
    )
  )
)

if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY=py -3"
    echo Using default Python via launcher (py -3).
  )
)

if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "PY=python"
    echo Using python from PATH.
  )
)

if not defined PY (
  echo [ERROR] Python is not installed or not on PATH.
  echo Recommended: install Python 3.12 from
  echo   https://www.python.org/downloads/release/python-3128/
  echo Make sure to check "Add Python to PATH" during install.
  pause
  exit /b 1
)

REM --- check Python version is in tested range (3.10 - 3.13) ---
%PY% -c "import sys;v=sys.version_info;sys.exit(0 if (3,10)<=(v.major,v.minor)<=(3,13) else 2)" >nul 2>nul
if errorlevel 2 (
  echo.
  echo [WARNING] Detected Python is outside the tested range 3.10-3.13.
  echo Some packages may need to compile from source on newer Python.
  echo.
  echo Recommended: install Python 3.12 alongside your current Python from
  echo   https://www.python.org/downloads/release/python-3128/
  echo Then re-run setup.bat - it will pick 3.12 automatically.
  echo.
  set /p CONTINUE="Continue anyway? (y/N): "
  if /i not "!CONTINUE!"=="y" exit /b 1
)

REM --- check node ---
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js is not installed or not on PATH.
  echo Install LTS from https://nodejs.org/
  pause
  exit /b 1
)

echo.
echo [1/3] Creating Python virtual environment...
pushd "%~dp0backend"
if not exist .venv (
  %PY% -m venv .venv
  if errorlevel 1 (
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
if errorlevel 1 (
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
if errorlevel 1 (
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
