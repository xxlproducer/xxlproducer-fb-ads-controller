#!/usr/bin/env pwsh
# FB Ads Controller - first-time setup (Windows / PowerShell)
# Idempotent: safe to re-run.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

# Strip Mark-of-the-Web from extracted ZIP files so future direct .ps1 calls
# don't get blocked by execution policy. Safe; only affects local files.
Get-ChildItem -Path $root -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  FB Ads Controller - first time setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- pick Python: prefer 3.12 / 3.13 / 3.11 / 3.10 via py launcher ---
$py = $null
foreach ($v in "3.12", "3.13", "3.11", "3.10") {
  & py -$v --version 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $py = @("py", "-$v")
    Write-Host "Using Python $v via launcher." -ForegroundColor Green
    break
  }
}
if (-not $py) {
  & py -3 --version 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $py = @("py", "-3")
    Write-Host "Using default Python via launcher (py -3)." -ForegroundColor Yellow
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $py = @("python")
    Write-Host "Using python from PATH." -ForegroundColor Yellow
  } else {
    Write-Host "[ERROR] Python is not installed or not on PATH." -ForegroundColor Red
    Write-Host "Recommended: install Python 3.12 from"
    Write-Host "  https://www.python.org/downloads/release/python-3128/"
    Read-Host "Press Enter to exit"
    exit 1
  }
}

# --- check node ---
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "[ERROR] Node.js is not installed or not on PATH." -ForegroundColor Red
  Write-Host "Install LTS from https://nodejs.org/"
  Read-Host "Press Enter to exit"
  exit 1
}

# --- backend ---
Write-Host ""
Write-Host "[1/3] Creating Python virtual environment..." -ForegroundColor Cyan
$venv = Join-Path $root "backend\.venv"
if (-not (Test-Path $venv)) {
  & $py[0] $py[1..($py.Length - 1)] -m venv $venv
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to create venv." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
  }
}

Write-Host "[2/3] Installing backend dependencies..." -ForegroundColor Cyan
$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] Failed to install backend deps." -ForegroundColor Red
  Read-Host "Press Enter to exit"
  exit 1
}

# --- frontend ---
Write-Host "[3/3] Installing frontend dependencies..." -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
try {
  & npm install
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install frontend deps." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
  }
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Setup complete. Run run.ps1 to start." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
