@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

set INSAR_USE_WSL=1
if not defined INSAR_WSL_DISTRO set INSAR_WSL_DISTRO=Ubuntu

wsl -d Ubuntu -e bash -c "true" 2>nul
if errorlevel 1 (
  wsl -e bash -c "true" 2>nul
  if errorlevel 1 (
    echo [ERROR] No WSL with bash. Install Ubuntu.
    pause
    exit /b 1
  )
)

REM INSAR_WSL_ENV_SCRIPT: leave unset to auto-pick project scripts/wsl/env_isce2.sh
if not defined INSAR_WSL_WORKSPACE_ROOT set INSAR_WSL_WORKSPACE_ROOT=~/insar-projects
if not defined INSAR_WSL_MINTPY_SRC set INSAR_WSL_MINTPY_SRC=~/MintPy/MintPy/src

set PYTHON=
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON if exist "D:\env\miniconda3\envs\isce2-build\python.exe" set "PYTHON=D:\env\miniconda3\envs\isce2-build\python.exe"
if not defined PYTHON if exist "C:\ProgramData\Anaconda3\envs\isce2-build\python.exe" set "PYTHON=C:\ProgramData\Anaconda3\envs\isce2-build\python.exe"
if not defined PYTHON (
  where python >nul 2>&1
  if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
  echo [ERROR] Python not found.
  echo Create venv:  cd /d "%PROJECT_ROOT%"
  echo               python -m venv .venv
  echo               .venv\Scripts\pip install -r desktop\requirements.txt
  pause
  exit /b 1
)

set PYTHONPATH=%PROJECT_ROOT%
set INSAR_PROJECT_ROOT=%PROJECT_ROOT%
set PYTHONIOENCODING=utf-8
if exist "%PROJECT_ROOT%\lib\MintPy-main\src" set "PYTHONPATH=%PROJECT_ROOT%\lib\MintPy-main\src;%PYTHONPATH%"

"%PYTHON%" -c "import PySide6; import qt_material; import qtawesome" 2>nul
if errorlevel 1 (
  echo Installing desktop requirements...
  "%PYTHON%" -m pip install -r "%PROJECT_ROOT%\desktop\requirements.txt"
  if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
  )
)

echo.
echo InSAR Desktop - WSL mode
echo   Python: %PYTHON%
echo   Project: %PROJECT_ROOT%
echo   WSL distro: %INSAR_WSL_DISTRO%
echo.

cd /d "%PROJECT_ROOT%"
if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs"
"%PYTHON%" -m desktop.main
if errorlevel 1 (
  echo.
  echo [ERROR] Desktop exited with error. Log: %PROJECT_ROOT%\logs\desktop.log
  pause
)
endlocal
exit /b 0
