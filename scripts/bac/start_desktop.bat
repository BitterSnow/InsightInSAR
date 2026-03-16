@echo off
chcp 65001 >nul 2>&1
title InSAR Desktop
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

:: ---- Locate Python --------------------------------------------------------
:: Prefer .venv (PySide6 works cleanly); fall back to isce2-build conda env.
set "PYTHON="
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    set "PYTHON_LABEL=.venv"
)
if not defined PYTHON (
    for %%P in (
        "D:\env\miniconda3\envs\isce2-build\python.exe"
        "C:\ProgramData\Anaconda3\envs\isce2-build\python.exe"
    ) do if not defined PYTHON if exist %%P (
        set "PYTHON=%%~P"
        set "PYTHON_LABEL=isce2-build"
    )
)
if not defined PYTHON (
    echo [ERROR] Python not found. Create .venv or isce2-build conda env first.
    pause & exit /b 1
)

:: ---- Environment -----------------------------------------------------------
set "MINTPY_SRC=%PROJECT_ROOT%\lib\MintPy-main\src"
set "PYTHONPATH=%PROJECT_ROOT%"
if exist "%MINTPY_SRC%" set "PYTHONPATH=%MINTPY_SRC%;%PYTHONPATH%"
set "INSAR_PROJECT_ROOT=%PROJECT_ROOT%"
set "PYTHONIOENCODING=utf-8"

:: isce2-build fallback needs UCRT64 + ISCE packages on PATH
if "%PYTHON_LABEL%"=="isce2-build" (
    set "UCRT64=%PROJECT_ROOT%\tools\msys64\ucrt64\bin"
    set "PACKAGES=%PROJECT_ROOT%\lib\isce2-main\install\packages"
    if not exist "%PACKAGES%" (
        echo [ERROR] ISCE2 packages not found: %PACKAGES%
        pause & exit /b 1
    )
    for %%P in ("%PYTHON%") do set "CONDA_BIN=%%~dpP"
    call set "PATH=%UCRT64%;%CONDA_BIN%Library\bin;%CONDA_BIN%;%PATH%"
)

:: ---- Auto-install PySide6 if missing (.venv only) --------------------------
if "%PYTHON_LABEL%"==".venv" (
    "%PYTHON%" -c "import PySide6" 2>nul
    if errorlevel 1 (
        echo PySide6 not found, installing desktop\requirements.txt ...
        "%PYTHON%" -m pip install -r "%PROJECT_ROOT%\desktop\requirements.txt"
        if errorlevel 1 (
            echo [ERROR] pip install failed
            pause & exit /b 1
        )
    )
)

:: ---- MintPy deps check (time-series) ---------------------------------------
if exist "%MINTPY_SRC%" (
    "%PYTHON%" -c "import skimage" 2>nul
    if errorlevel 1 (
        echo [MintPy] Missing dependencies. Installing desktop\requirements-mintpy.txt ...
        "%PYTHON%" -m pip install -r "%PROJECT_ROOT%\desktop\requirements-mintpy.txt"
        if errorlevel 1 echo [MintPy] pip install failed. Time-series may fail. Run: pip install -r desktop\requirements-mintpy.txt
    )
)

:: ---- Launch ----------------------------------------------------------------
echo Python : %PYTHON% (%PYTHON_LABEL%)
echo Project: %PROJECT_ROOT%
echo.
"%PYTHON%" -m desktop.main
if errorlevel 1 (
    echo.
    echo [Desktop exited with error code %ERRORLEVEL%]
    pause
)
