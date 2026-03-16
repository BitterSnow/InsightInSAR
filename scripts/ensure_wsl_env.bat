@echo off
setlocal
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

echo Checking WSL ISCE2 + MintPy...
echo ""

REM Find distro with bash (same as check_wsl_env.bat)
set "WSL_EXTRA="
wsl -e bash -c "true" 2>nul && goto :wsl_ok
wsl -d Ubuntu -e bash -c "true" 2>nul && set "WSL_EXTRA=-d Ubuntu" && goto :wsl_ok
wsl -d Ubuntu-24.04 -e bash -c "true" 2>nul && set "WSL_EXTRA=-d Ubuntu-24.04" && goto :wsl_ok
wsl -d Ubuntu-22.04 -e bash -c "true" 2>nul && set "WSL_EXTRA=-d Ubuntu-22.04" && goto :wsl_ok
echo [ERROR] No WSL distro with bash. Install Ubuntu from Microsoft Store, then: wsl --set-default Ubuntu
pause
exit /b 1

:wsl_ok
wsl %WSL_EXTRA% -e true 2>nul
if errorlevel 1 (
    echo [ERROR] WSL not available.
    pause
    exit /b 1
)

REM Get WSL path of project root
set "WSL_PROJECT="
for /f "usebackq delims=" %%i in (`wsl %WSL_EXTRA% -e wslpath -a "%PROJECT_ROOT%" 2^>nul`) do set "WSL_PROJECT=%%i"
if not defined WSL_PROJECT (
    echo [ERROR] Could not get WSL path for %PROJECT_ROOT%
    pause
    exit /b 1
)

REM Check first; if not ready, run ensure_env.sh in WSL
wsl %WSL_EXTRA% -e bash -c "source ~/insar-wsl/env_isce2.sh 2>/dev/null || true; [ -f ~/miniconda3/etc/profile.d/conda.sh ] && source ~/miniconda3/etc/profile.d/conda.sh && conda activate isce2 2>/dev/null; python3 -c 'import isce' 2>/dev/null && python3 -c 'import mintpy' 2>/dev/null" 2>nul
if not errorlevel 1 (
    echo Result: READY. Start Desktop with scripts\start_desktop_wsl.bat
    pause
    exit /b 0
)

echo Not configured. Running auto-setup in WSL...
echo ""
wsl %WSL_EXTRA% -e bash "%WSL_PROJECT%/scripts/wsl/ensure_env.sh"
set "SETUP_ERR=%errorlevel%"
echo ""
if %SETUP_ERR% neq 0 (
    echo Auto-setup failed or check still not OK. See docs\wsl_ubuntu24_isce2_setup.md
) else (
    echo Done. Start Desktop with scripts\start_desktop_wsl.bat
)
pause
exit /b %SETUP_ERR%
