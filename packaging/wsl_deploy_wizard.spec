# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder spec for InSAR WSL 部署向导.
# Build from repo root: pyinstaller packaging/wsl_deploy_wizard.spec
# Output: dist/InSAR WSL 部署向导/ . Deploy next to InSAR Desktop exe.

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "packaging" / "wsl_deploy_wizard.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[(str(REPO_ROOT / "packaging" / "wizard_icon.ico"), ".")],
    hiddenimports=[
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "wsl_config_path",
        "packaging.wsl_sanitize",
        "cds_wsl_bridge",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InSAR WSL Deploy Wizard",
    debug=False,
    console=False,
    target_arch=None,
    icon=str(REPO_ROOT / "packaging" / "wizard_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="InSAR WSL Deploy Wizard",
)
