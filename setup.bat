@echo off
REM Thin shim that delegates to setup.ps1 with -ExecutionPolicy Bypass
REM so Windows ExecutionPolicy / Mark-of-the-Web blocks don't apply.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Press any key to close.
  pause >nul
  exit /b 1
)
