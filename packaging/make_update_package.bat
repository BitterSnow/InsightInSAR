@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_update_package.ps1"
pause

