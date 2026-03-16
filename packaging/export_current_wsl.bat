@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."
REM Export current dev WSL image only. No checks/install. Optional: set INSAR_WSL_DISTRO=Ubuntu-24.04
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0export_current_wsl.ps1" %*
pause
