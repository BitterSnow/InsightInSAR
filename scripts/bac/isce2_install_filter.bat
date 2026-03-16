@echo off
REM Build + install ISCE2 (including libfilter) to lib/isce2-main/install.
REM Run from project root: scripts\isce2_install_filter.bat

set ROOT=%~dp0..
set BUILD=%ROOT%\lib\isce2-main\build
set PREFIX=%ROOT%\lib\isce2-main\install
set PKG=%PREFIX%\packages

echo Building libfilter...
cmake --build "%BUILD%" --target libfilter
if errorlevel 1 exit /b 1

echo Installing to %PREFIX% ...
cmake --install "%BUILD%" --prefix "%PREFIX%"
if errorlevel 1 exit /b 1

REM Stack uses packages/isce; ensure isce/components/mroipac/filter has libfilter.dll (copy from isce2 if needed).
if not exist "%PKG%\isce\components\mroipac\filter\libfilter.dll" (
  if exist "%PKG%\isce2\components\mroipac\filter\libfilter.dll" (
    echo Copying libfilter into packages/isce for legacy path...
    mkdir "%PKG%\isce\components\mroipac\filter" 2>nul
    copy /Y "%PKG%\isce2\components\mroipac\filter\libfilter.dll" "%PKG%\isce\components\mroipac\filter\"
  )
)

echo Done. libfilter.dll should be in:
echo   %PKG%\isce2\components\mroipac\filter\
echo   %PKG%\isce\components\mroipac\filter\
exit /b 0
