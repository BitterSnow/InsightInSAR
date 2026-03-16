@echo off
cd /d "%~dp0\.."
echo Deleting .git\index.lock if present...
if exist ".git\index.lock" del /f ".git\index.lock"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_to_github.ps1"
pause
