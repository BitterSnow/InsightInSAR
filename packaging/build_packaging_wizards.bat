@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] .venv not found. Create: python -m venv .venv
    echo Then: .venv\Scripts\pip install -r desktop\requirements.txt pyinstaller
    pause
    exit /b 1
)

echo ========================================
echo InSAR WSL 导出/部署向导 打包
echo ========================================
echo.
echo 说明: 从 build 目录调用 PyInstaller，避免与项目 packaging 目录名冲突。
echo.

if not exist "%ROOT%\build" mkdir "%ROOT%\build"

echo [1/3] 安装/检查 PyInstaller ...
"%PY%" -m pip install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] pip install pyinstaller failed
    pause
    exit /b 1
)

echo [2/3] 打包 WSL 部署向导 ...
cd /d "%ROOT%\build"
"%PY%" -m PyInstaller --noconfirm --distpath="%ROOT%\dist" --workpath="%ROOT%\build" "%ROOT%\packaging\wsl_deploy_wizard.spec"
if errorlevel 1 (
    cd /d "%ROOT%"
    echo [ERROR] Deploy Wizard build failed
    pause
    exit /b 1
)

echo [3/3] 打包 WSL 导出向导 ...
"%PY%" -m PyInstaller --noconfirm --distpath="%ROOT%\dist" --workpath="%ROOT%\build" "%ROOT%\packaging\wsl_export_wizard.spec"
cd /d "%ROOT%"
if errorlevel 1 (
    echo [ERROR] Export Wizard build failed
    pause
    exit /b 1
)

echo.
echo 可执行文件已生成（整目录拷贝到客户机即可，无需安装 Python）:
echo   dist\InSAR WSL Deploy Wizard\InSAR WSL Deploy Wizard.exe
echo   dist\InSAR WSL Export Wizard\InSAR WSL Export Wizard.exe
echo.
echo 完成。
pause
