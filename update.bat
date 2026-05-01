@echo off
REM Thin shim that delegates to update.ps1 with -ExecutionPolicy Bypass
REM so Windows ExecutionPolicy / Mark-of-the-Web blocks don't apply.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
if errorlevel 1 (
  echo.
  echo Update failed. Press any key to close.
  pause >nul
  exit /b 1
)
