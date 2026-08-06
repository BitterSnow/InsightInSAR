# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder spec for InSAR WSL 导出向导.
# Build from repo root: pyinstaller packaging/wsl_export_wizard.spec

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "packaging" / "wsl_export_wizard.py")],
    pathex=[str(REPO_ROOT), str(REPO_ROOT / "packaging")],
    binaries=[],
    datas=[(str(REPO_ROOT / "packaging" / "wizard_icon.ico"), ".")],
    hiddenimports=[
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "wsl_sanitize",
        "cds_wsl_bridge",
        "wsl_config_path",
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
    name="InSAR WSL Export Wizard",
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
    name="InSAR WSL Export Wizard",
)
