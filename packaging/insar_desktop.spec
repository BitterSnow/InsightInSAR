# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder spec for InSAR Desktop.
# Build: from repo root, run:
#   pyinstaller packaging/insar_desktop.spec
# Output: dist/InSAR Desktop/ with exe + backend/ + desktop/ + shared_models.py.
# Deploy: copy lib/isce2-main and lib/MintPy-main next to the output for WSL use.

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "desktop" / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[
        (str(REPO_ROOT / "backend"), "backend"),
        (str(REPO_ROOT / "desktop"), "desktop"),
        (str(REPO_ROOT / "shared_models.py"), "."),
        (str(REPO_ROOT / "public" / "img"), "public/img"),
    ],
    hiddenimports=[
        "wsl_config_path",
        "cds_wsl_bridge",
        "backend.services.wsl_runner",
        "backend.services.s1_processing_service",
        "backend.services.stack_processing_service",
        "backend.services.mintpy_processing_service",
        "backend.services.mintpy_vector_export_service",
        "backend.scripts.run_mintpy_to_shapefile_wsl",
        "backend.services.dem_processing_service",
        "backend.scripts.subswath_detector",
        "backend.scripts.run_s1_extract_wsl",
        "backend.scripts.run_stack_wsl",
        "backend.scripts.run_mintpy_wsl",
        "backend.scripts.run_mintpy_init_wsl",
        "geopandas",
        "shapely",
        "shapely.ops",
        "qt_material",
        "qtawesome",
        "h5py",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["isce", "isceobj", "mintpy"],  # WSL mode only; no Windows ISCE2
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InSAR Desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(REPO_ROOT / "packaging" / "desktop_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="InSAR Desktop",
)
