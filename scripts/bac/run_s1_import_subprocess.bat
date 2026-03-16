@echo off
REM Invoked by desktop: run_s1_import_subprocess.bat <request_json_file>
REM Sets isce2-build env and runs run_s1_import_standalone.py with that file.
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
set "UCRT64=%PROJECT_ROOT%\tools\msys64\ucrt64\bin"
set "PACKAGES=%PROJECT_ROOT%\lib\isce2-main\install\packages"
REM Prefer the conda env that was used to BUILD ISCE2 (often Anaconda); else Miniconda3
set "CONDA_ENV=C:\ProgramData\Anaconda3\envs\isce2-build"
if not exist "%CONDA_ENV%\python.exe" set "CONDA_ENV=D:\env\miniconda3\envs\isce2-build"
if not exist "%CONDA_ENV%\python.exe" exit /b 1
if not exist "%PACKAGES%" exit /b 1
if not exist "%UCRT64%\libgcc_s_seh-1.dll" exit /b 2

REM UCRT64 first so ISCE2 .pyd (MinGW-built) finds libgcc_s_seh, libstdc++, libwinpthread
set "PATH=%UCRT64%;%CONDA_ENV%\Library\bin;%CONDA_ENV%\bin;%PATH%"
set "PYTHONPATH=%PROJECT_ROOT%;%PACKAGES%"
set "INSAR_PROJECT_ROOT=%PROJECT_ROOT%"
set "PYTHONIOENCODING=utf-8"

"%CONDA_ENV%\python.exe" "%~dp0run_s1_import_standalone.py" "%~1"
exit /b %ERRORLEVEL%
