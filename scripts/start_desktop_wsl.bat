@echo off
setlocal
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

set INSAR_USE_WSL=1
if defined INSAR_WSL_DISTRO goto wsl_check_done
set INSAR_WSL_DISTRO=
wsl -e bash -c "true" 2>nul
if not errorlevel 1 goto wsl_check_done
wsl -d Ubuntu -e bash -c "true" 2>nul
if not errorlevel 1 set INSAR_WSL_DISTRO=Ubuntu
if not errorlevel 1 goto wsl_check_done
echo [ERROR] No WSL with bash. Install Ubuntu and run: wsl --set-default Ubuntu
pause
exit /b 1

:wsl_check_done
if defined INSAR_WSL_ENV_SCRIPT goto env_done
set INSAR_WSL_ENV_SCRIPT=~/insar-wsl/env_isce2.sh
:env_done
if defined INSAR_WSL_WORKSPACE_ROOT goto ws_done
set INSAR_WSL_WORKSPACE_ROOT=~/insar-projects
:ws_done

set WSL_EXTRA=
if "%INSAR_WSL_DISTRO%"=="" goto py_check
set WSL_EXTRA=-d %INSAR_WSL_DISTRO%
:py_check

set PYTHON=
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if "%PYTHON%"=="" goto no_venv
goto venv_ok
:no_venv
echo [ERROR] .venv not found. Run: python -m venv .venv
echo Then: .venv\Scripts\pip install -r desktop\requirements.txt
pause
exit /b 1

:venv_ok
set PYTHONPATH=%PROJECT_ROOT%
set INSAR_PROJECT_ROOT=%PROJECT_ROOT%
set PYTHONIOENCODING=utf-8
if exist "%PROJECT_ROOT%\lib\MintPy-main\src" set "PYTHONPATH=%PROJECT_ROOT%\lib\MintPy-main\src;%PYTHONPATH%"

"%PYTHON%" -c "import PySide6; import qt_material; import qtawesome" 2>nul
if not errorlevel 1 goto run_desktop
echo Installing desktop requirements...
"%PYTHON%" -m pip install -r "%PROJECT_ROOT%\desktop\requirements.txt"
if errorlevel 1 goto pip_err

:run_desktop
echo.
echo InSAR Desktop - WSL mode
echo   Python: %PYTHON%
echo   Project: %PROJECT_ROOT%
echo.

cd /d "%PROJECT_ROOT%"
if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs"
set "LOG_FILE=%PROJECT_ROOT%\logs\desktop.log"
REM Log file is written by Desktop only (UTF-8), no redirect to avoid encoding mix
"%PYTHON%" -m desktop.main
if not errorlevel 1 goto exit_ok
echo.
echo [ERROR] Desktop exited with error. Log: %LOG_FILE%
pause
:exit_ok
endlocal
exit /b 0

:pip_err
echo [ERROR] pip install failed
pause
exit /b 1
