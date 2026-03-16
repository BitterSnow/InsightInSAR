"""
Test where ISCE2 crashes: import step by step with minimal PATH (no UCRT64).
Run: D:\env\miniconda3\envs\isce2-build\python.exe scripts\test_isce_import.py
"""
from __future__ import annotations

import os
import subprocess
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ISCE_ROOT = os.path.join(PROJECT_ROOT, "lib", "isce2-main")
INSTALL = os.path.join(ISCE_ROOT, "install", "packages")
CONTRIB = os.path.join(ISCE_ROOT, "contrib", "stack")

OUT = os.path.join(PROJECT_ROOT, "scripts", "test_isce_import_result.txt")


def get_python():
    for p in [
        os.environ.get("ISCE2_PYTHON"),
        r"D:\env\miniconda3\envs\isce2-build\python.exe",
        r"C:\ProgramData\Anaconda3\envs\isce2-build\python.exe",
    ]:
        if p and os.path.isfile(p):
            return p
    return sys.executable


def run_import_test(import_stmt: str, log_file) -> int:
    env = os.environ.copy()
    py = get_python()
    conda_bin = os.path.dirname(py)
    conda_lib = os.path.join(conda_bin, "Library", "bin")
    env["PATH"] = os.pathsep.join([conda_lib, conda_bin]) + os.pathsep + env.get("PATH", "")
    pp = [PROJECT_ROOT, INSTALL, CONTRIB] if os.path.isdir(INSTALL) else [PROJECT_ROOT, CONTRIB]
    env["PYTHONPATH"] = os.pathsep.join(pp)
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [py, "-c", f"print('before'); {import_stmt}; print('ok')"],
        env=env,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    out, _ = proc.communicate()
    if out:
        log_file.write(out)
    return proc.returncode


def main():
    steps = [
        ("import isce", "isce"),
        ("import isceobj", "isceobj"),
        ("from isceobj.Sensor.TOPS.Sentinel1 import Sentinel1", "Sentinel1"),
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        for label, import_stmt in steps:
            f.write(f"\n--- {label} ---\n")
            f.flush()
            code = run_import_test(import_stmt, f)
            f.write(f"Exit code: {code}\n")
            f.flush()
            if code != 0:
                f.write(f"CRASH at: {label}\n")
                print(f"CRASH at: {label} (exit {code})")
                return code
    print(f"All imports OK. Result in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
