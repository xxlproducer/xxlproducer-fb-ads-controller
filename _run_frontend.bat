@echo off
chcp 65001 >nul
title FB Ads Controller - Frontend
cd /d "%~dp0frontend"
call npm run dev
