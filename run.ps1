#!/usr/bin/env pwsh
# FB Ads Controller - one-click launcher (Windows / PowerShell)
# Spawns backend + frontend in two new PowerShell windows and opens the browser.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

if (-not (Test-Path (Join-Path $root "backend\.venv"))) {
  Write-Host "First run detected. Running setup..." -ForegroundColor Yellow
  & (Join-Path $root "setup.ps1")
  if ($LASTEXITCODE -ne 0) { exit 1 }
}
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
  Write-Host "Frontend deps missing. Running setup..." -ForegroundColor Yellow
  & (Join-Path $root "setup.ps1")
  if ($LASTEXITCODE -ne 0) { exit 1 }
}

Write-Host ""
Write-Host "Starting FB Ads Controller..." -ForegroundColor Cyan
Write-Host "  Backend  : http://127.0.0.1:8080"
Write-Host "  Frontend : http://localhost:5173"
Write-Host ""
Write-Host "Two new windows will open. Close them to stop the app."
Write-Host ""

$backendCmd = "Set-Location '$root\backend'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8080"
$frontendCmd = "Set-Location '$root\frontend'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCmd
Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCmd

Start-Sleep -Seconds 5
Start-Process "http://localhost:5173"

Write-Host "Done. Two PowerShell windows are running the servers." -ForegroundColor Green
