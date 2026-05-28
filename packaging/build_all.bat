@echo off
chcp 65001 >nul 2>&1
setlocal
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
echo InSAR Desktop + 部署向导 一键打包
echo ========================================
echo.

echo [1/4] 安装/检查 PyInstaller ...
"%PY%" -m pip install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] pip install pyinstaller failed
    pause
    exit /b 1
)

echo [2/4] 打包桌面端 -> dist\InSAR Desktop\
cd "%ROOT%\.venv"
.\Scripts\python.exe -m PyInstaller --noconfirm --distpath="%ROOT%\dist" --workpath="%ROOT%\build" "%ROOT%\packaging\insar_desktop.spec"
cd "%ROOT%"
if errorlevel 1 (
    echo [ERROR] Desktop build failed
    pause
    exit /b 1
)

echo [3/4] 打包 WSL 部署向导 -> dist\InSAR WSL 部署向导\
cd "%ROOT%\.venv"
.\Scripts\python.exe -m PyInstaller --noconfirm --distpath="%ROOT%\dist" --workpath="%ROOT%\build" "%ROOT%\packaging\wsl_deploy_wizard.spec"
cd "%ROOT%"
if errorlevel 1 (
    echo [ERROR] Wizard build failed
    pause
    exit /b 1
)

echo [4/4] 打包 WSL 导出向导 -> dist\InSAR WSL 导出向导\
cd "%ROOT%\.venv"
.\Scripts\python.exe -m PyInstaller --noconfirm --distpath="%ROOT%\dist" --workpath="%ROOT%\build" "%ROOT%\packaging\wsl_export_wizard.spec"
cd "%ROOT%"
if errorlevel 1 (
    echo [ERROR] Export Wizard build failed
    pause
    exit /b 1
)

echo.
echo 可执行文件已生成:
echo   - dist\InSAR Desktop\InSAR Desktop.exe  (主程序，双击运行)
echo   - dist\InSAR WSL Deploy Wizard\InSAR WSL Deploy Wizard.exe  (WSL 部署向导，双击运行)
echo   - dist\InSAR WSL Export Wizard\InSAR WSL Export Wizard.exe  (WSL 导出向导，双击运行)
echo.
echo 提示: WSL 侧会从安装根目录读取 backend/lib/scripts（见 packaging\README.md 的「环境与代码分离」）。
echo 可选: 生成更新包 ZIP: 运行 packaging\make_update_package.bat
echo.
echo.
echo 完成。
pause
