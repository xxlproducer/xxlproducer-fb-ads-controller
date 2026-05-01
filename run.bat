@echo off
REM Thin shim that delegates to run.ps1 with -ExecutionPolicy Bypass
REM so Windows ExecutionPolicy / Mark-of-the-Web blocks don't apply.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
