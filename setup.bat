@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title FB Ads Controller - Setup

echo.
echo ============================================
echo   FB Ads Controller - first time setup
echo ============================================
echo.

REM ---- pick python: prefer 3.12 -> 3.13 -> 3.11 -> 3.10 -> default ----
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%V --version >nul 2>nul
    if not errorlevel 1 set "PY=py -%%V"
  )
)
if not defined PY (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3.10+ not found. Install from:
  echo   https://www.python.org/downloads/release/python-3128/
  echo Make sure to check "Add to PATH" during install.
  echo.
  pause
  exit /b 1
)
echo Using Python: %PY%

REM ---- check node ----
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install LTS from https://nodejs.org/
  echo.
  pause
  exit /b 1
)
echo Using Node:   
node --version

echo.
echo [1/3] Creating Python virtual environment...
pushd backend
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
call .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install backend deps.
  popd
  pause
  exit /b 1
)
popd

echo [3/3] Installing frontend dependencies...
pushd frontend
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
echo   Setup complete. Double-click START.bat
echo ============================================
echo.
pause
