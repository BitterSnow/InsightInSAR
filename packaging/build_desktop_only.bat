@echo off
setlocal

REM IMPORTANT: Keep this file ASCII-only for cmd compatibility.
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] .venv not found. Create it: python -m venv .venv
  echo Then: .venv\Scripts\pip install -r desktop\requirements.txt pyinstaller
  pause
  exit /b 1
)

echo ========================================
echo InSAR Desktop - build (desktop only)
echo ========================================
echo.

echo [1/2] Ensure PyInstaller...
"%PY%" -m pip install pyinstaller -q
if errorlevel 1 (
  echo [ERROR] pip install pyinstaller failed
  pause
  exit /b 1
)

echo [2/2] Build Desktop to dist\InSAR Desktop\
cd "%ROOT%\.venv"
.\Scripts\python.exe -m PyInstaller --noconfirm --distpath="%ROOT%\dist" --workpath="%ROOT%\build" "%ROOT%\packaging\insar_desktop.spec"
cd "%ROOT%"
if errorlevel 1 (
  echo [ERROR] Desktop build failed
  pause
  exit /b 1
)

echo.
echo Output:
echo   %ROOT%\dist\InSAR Desktop\InSAR Desktop.exe
echo.
echo Done.
pause

