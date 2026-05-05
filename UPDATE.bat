@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title FB Ads Controller - Update

cd /d "%~dp0"

echo.
echo ============================================
echo   FB Ads Controller - Update from GitHub
echo ============================================
echo.
echo Downloading latest version from main...

set "ZIP=%TEMP%\fbac_update.zip"
set "EXTRACT=%TEMP%\fbac_update"

if exist "%ZIP%" del /q "%ZIP%"
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://github.com/xxlproducer/xxlproducer-fb-ads-controller/archive/refs/heads/main.zip' -OutFile '%ZIP%' -UseBasicParsing; Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACT%' -Force; exit 0 } catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
  echo [ERROR] Download/extract failed. Check internet connection.
  pause
  exit /b 1
)

set "SRC=%EXTRACT%\xxlproducer-fb-ads-controller-main"
if not exist "%SRC%" (
  echo [ERROR] Extracted folder not found at %SRC%.
  pause
  exit /b 1
)

echo Copying new files (preserving venv, node_modules, database)...
robocopy "%SRC%" "%~dp0" /MIR /NFL /NDL /NJH /NJS /NC /NS /XD ".venv" "node_modules" "data" "__pycache__" ".git" /XF "*.db" "*.sqlite" "*.sqlite3" ".env"

REM robocopy returns 0-7 for success, 8+ for errors
if errorlevel 8 (
  echo [ERROR] File copy failed.
  pause
  exit /b 1
)

echo Cleaning up...
if exist "%ZIP%" del /q "%ZIP%"
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%"

echo.
echo ============================================
echo   Update complete. Installing new deps...
echo ============================================
echo.

REM Re-install in case requirements.txt or package.json changed
pushd backend
if exist .venv (
  call .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
)
popd

pushd frontend
if exist node_modules (
  call npm install --silent
)
popd

echo.
echo ============================================
echo   Done. Starting app...
echo ============================================
echo.
timeout /t 2 /nobreak >nul

call "%~dp0START.bat"
