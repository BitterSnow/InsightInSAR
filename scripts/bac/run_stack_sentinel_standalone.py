"""
Run stackSentinel.py in an isolated environment (conda + SystemRoot only, no parent PATH).
Use when desktop-spawned subprocess crashes with 3228369023; run from CMD with isce2-build to test.

  D:\env\miniconda3\envs\isce2-build\python.exe scripts\run_stack_sentinel_standalone.py -w D:\processing\tianfu\processing -s D:\coding\insar-system\data\radar ...

All arguments after this script are passed to stackSentinel.py (same as stack_processing_service).
"""
from __future__ import annotations

import os
import subprocess
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ISCE_ROOT = os.path.join(PROJECT_ROOT, "lib", "isce2-main")
TOPS_STACK = os.path.join(ISCE_ROOT, "contrib", "stack", "topsStack")
STACK_SENTINEL_PY = os.path.join(TOPS_STACK, "stackSentinel.py")
INSTALL_PACKAGES = os.path.join(ISCE_ROOT, "install", "packages")


def isce_dll_dirs():
    """Directories under install/packages that contain .pyd or .dll."""
    if not os.path.isdir(INSTALL_PACKAGES):
        return []
    seen = set()
    for root, _dirs, files in os.walk(INSTALL_PACKAGES):
        for f in files:
            if f.endswith(".pyd") or f.lower().endswith(".dll"):
                seen.add(os.path.normpath(root))
                break
    return list(seen)


def main():
    # Build isolated env (no parent PATH)
    python_exe = sys.executable
    conda_bin = os.path.dirname(python_exe)
    conda_lib = os.path.join(conda_bin, "Library", "bin")
    install_packages = os.path.join(ISCE_ROOT, "install", "packages")
    contrib_stack = os.path.join(ISCE_ROOT, "contrib", "stack")
    path_parts = [conda_lib, conda_bin]
    ucrt64 = os.path.join(PROJECT_ROOT, "tools", "msys64", "ucrt64", "bin")
    if os.path.isdir(ucrt64):
        path_parts.insert(0, ucrt64)
    path_parts.extend(isce_dll_dirs())
    system_root = os.environ.get("SystemRoot", "C:\\Windows")
    path_parts.extend([os.path.join(system_root, "system32"), system_root])

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(path_parts)
    pp = [PROJECT_ROOT, install_packages, contrib_stack] if os.path.isdir(install_packages) else [PROJECT_ROOT, contrib_stack]
    env["PYTHONPATH"] = os.pathsep.join(pp)
    env["INSAR_PROJECT_ROOT"] = PROJECT_ROOT
    env["PYTHONUNBUFFERED"] = "1"

    argv = [python_exe, STACK_SENTINEL_PY] + sys.argv[1:]
    cwd = PROJECT_ROOT
    if "-w" in sys.argv:
        i = sys.argv.index("-w")
        if i + 1 < len(sys.argv):
            cwd = os.path.abspath(sys.argv[i + 1])
    print("PATH (isolated):", env["PATH"][:200], "...")
    print("CWD:", cwd)
    print("Running:", " ".join(argv[:6]), "...")
    sys.exit(subprocess.run(argv, env=env, cwd=cwd).returncode)


if __name__ == "__main__":
    main()
