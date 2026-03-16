@echo off
setlocal
echo Checking WSL ISCE2 + MintPy...
echo ""

REM Find distro with bash: default, then Ubuntu, Ubuntu-24.04, Ubuntu-22.04
set "WSL_EXTRA="
wsl -e bash -c "true" 2>nul && goto :do_check
wsl -d Ubuntu -e bash -c "true" 2>nul && set "WSL_EXTRA=-d Ubuntu" && goto :do_check
wsl -d Ubuntu-24.04 -e bash -c "true" 2>nul && set "WSL_EXTRA=-d Ubuntu-24.04" && goto :do_check
wsl -d Ubuntu-22.04 -e bash -c "true" 2>nul && set "WSL_EXTRA=-d Ubuntu-22.04" && goto :do_check
echo [ERROR] No WSL distro with bash found.
echo Install Ubuntu from Microsoft Store, then run: wsl --set-default Ubuntu
pause
exit /b 1

:do_check
wsl %WSL_EXTRA% -e bash -c "source ~/insar-wsl/env_isce2.sh 2>/dev/null || true; [ -f ~/miniconda3/etc/profile.d/conda.sh ] && source ~/miniconda3/etc/profile.d/conda.sh && conda activate isce2 2>/dev/null; F=0; echo '--- ISCE2 ---'; python3 -c 'import isce' 2>/dev/null && echo '  OK' || { echo '  FAIL'; F=1; }; echo '--- MintPy ---'; python3 -c 'import mintpy' 2>/dev/null && echo '  OK' || { echo '  FAIL'; F=1; }; exit $F"
set WSL_ERR=%errorlevel%
echo.
if %WSL_ERR% neq 0 (
    echo Result: NOT READY. Run scripts\ensure_wsl_env.bat to auto-setup.
    echo See docs\wsl_ubuntu24_isce2_setup.md
) else (
    echo Result: READY. Run scripts\start_desktop_wsl.bat to start Desktop.
)
pause
exit /b %WSL_ERR%
