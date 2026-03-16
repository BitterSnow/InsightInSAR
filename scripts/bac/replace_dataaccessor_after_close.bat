@echo off
REM Run this AFTER closing all Python, PowerShell, and Cursor/IDE that might use isce.
REM Replaces DataAccessor.pyd with the new build (DataAccessor_new.pyd or from isce2).

set "ROOT=%~dp0.."
set "DIR=%ROOT%\lib\isce2-main\install\packages\isce\components\iscesys\ImageApi"
set "SRC=%ROOT%\lib\isce2-main\install\packages\isce2\components\iscesys\ImageApi\DataAccessor.pyd"
set "DST=%DIR%\DataAccessor.pyd"
set "NEW=%DIR%\DataAccessor_new.pyd"

if not exist "%SRC%" (
    echo Source not found: %SRC%
    exit /b 1
)

if exist "%NEW%" (
    del /f /q "%DIR%\DataAccessor.pyd" 2>nul
    if exist "%DIR%\DataAccessor.pyd" (
        echo DataAccessor.pyd is still in use. Close all Python/PowerShell/Cursor and run this again.
        exit /b 1
    )
    ren "%NEW%" "DataAccessor.pyd"
    echo Replaced with DataAccessor_new.pyd.
) else (
    copy /Y "%SRC%" "%DST%" >nul
    if errorlevel 1 (
        echo Copy failed. Close all Python/PowerShell/Cursor and run this again.
        exit /b 1
    )
    echo Overwrote DataAccessor.pyd from isce2.
)
echo Done. You can now run: scripts\run_step1_then_diagnose.ps1
