#!/usr/bin/env pwsh
# FB Ads Controller - update + restart (Windows / PowerShell)
# - Pulls latest code from git (if the folder is a git checkout)
# - Refreshes Python and Node dependencies (incremental, fast on rerun)
# - Restarts the app via run.ps1
#
# Designed for double-click via update.bat. No terminal dance required.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  FB Ads Controller - update" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Strip MOTW so freshly pulled / extracted files don't get blocked.
Get-ChildItem -Path $root -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

$gitDir = Join-Path $root ".git"
$hasGit = (Test-Path $gitDir) -and (Get-Command git -ErrorAction SilentlyContinue)

if ($hasGit) {
  Write-Host "[1/3] Pulling latest changes from git..." -ForegroundColor Cyan
  Push-Location $root
  try {
    & git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[WARN] git pull failed (maybe local changes or not on a branch)." -ForegroundColor Yellow
      Write-Host "       Continuing with current code." -ForegroundColor Yellow
    }
  } finally {
    Pop-Location
  }
} else {
  Write-Host "[1/3] No .git folder detected (ZIP install)." -ForegroundColor Yellow
  Write-Host "      To enable one-click updates, install Git for Windows once:" -ForegroundColor Yellow
  Write-Host "        https://git-scm.com/download/win" -ForegroundColor Yellow
  Write-Host "      Then clone the repo with:" -ForegroundColor Yellow
  Write-Host "        git clone https://github.com/xxlproducer/xxlproducer-fb-ads-controller.git" -ForegroundColor Yellow
  Write-Host "      For now, please re-download the ZIP from GitHub manually." -ForegroundColor Yellow
  Write-Host ""
}

Write-Host "[2/3] Refreshing dependencies (this may be quick if cached)..." -ForegroundColor Cyan
& (Join-Path $root "setup.ps1")
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] Dependency refresh failed." -ForegroundColor Red
  Read-Host "Press Enter to exit"
  exit 1
}

Write-Host "[3/3] Starting the app..." -ForegroundColor Cyan
& (Join-Path $root "run.ps1")
