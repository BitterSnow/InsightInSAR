@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stage_desktop_delivery.ps1" %*
if errorlevel 1 (
  echo [ERROR] stage_desktop_delivery failed
  pause
  exit /b 1
)
exit /b 0
