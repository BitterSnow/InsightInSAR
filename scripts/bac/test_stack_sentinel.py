"""
Diagnostic: run stackSentinel with minimal PATH (no UCRT64) and stream stdout/stderr
to see any output before crash. Usage: run from project root with isce2-build Python
  D:\env\miniconda3\envs\isce2-build\python.exe scripts\test_stack_sentinel.py
Or with same args as in stack_init.log (edit WORK_DIR etc below).
"""
from __future__ import annotations

import os
import subprocess
import sys

# Same paths as stack_processing_service
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ISCE_ROOT = os.path.join(PROJECT_ROOT, "lib", "isce2-main")
TOPS_STACK = os.path.join(ISCE_ROOT, "contrib", "stack", "topsStack")
STACK_SENTINEL_PY = os.path.join(TOPS_STACK, "stackSentinel.py")

# Defaults from stack_init.log (override via env if needed)
WORK_DIR = os.environ.get("INSAR_TEST_WORK_DIR", r"D:\processing\tianfu\processing")
SLC_DIR = os.environ.get("INSAR_TEST_SLC", os.path.join(PROJECT_ROOT, "data", "radar"))
ORBIT_DIR = os.path.join(PROJECT_ROOT, "data", "orbit")
AUX_DIR = os.path.join(PROJECT_ROOT, "data", "auxcal")
DEM_PATH = os.path.join(PROJECT_ROOT, "data", "dem", "demLat_N30_N33_Lon_E101_E105.dem")

OUTPUT_LOG = os.path.join(PROJECT_ROOT, "scripts", "test_stack_sentinel_result.txt")


def get_python_exe():
    for p in [
        os.environ.get("ISCE2_PYTHON"),
        r"D:\env\miniconda3\envs\isce2-build\python.exe",
        r"C:\ProgramData\Anaconda3\envs\isce2-build\python.exe",
    ]:
        if p and os.path.isfile(p):
            return p
    return sys.executable


def build_env(include_ucrt64: bool) -> dict:
    env = os.environ.copy()
    python_exe = get_python_exe()
    conda_bin = os.path.dirname(python_exe)
    conda_lib = os.path.join(conda_bin, "Library", "bin")
    install_packages = os.path.join(ISCE_ROOT, "install", "packages")
    contrib_stack = os.path.join(ISCE_ROOT, "contrib", "stack")
    path_parts = [conda_lib, conda_bin]
    if include_ucrt64:
        ucrt64 = os.path.join(PROJECT_ROOT, "tools", "msys64", "ucrt64", "bin")
        if os.path.isdir(ucrt64):
            path_parts.insert(0, ucrt64)
    env["PATH"] = os.pathsep.join(path_parts) + os.pathsep + env.get("PATH", "")
    pp = [PROJECT_ROOT, install_packages, contrib_stack] if os.path.isdir(install_packages) else [PROJECT_ROOT, contrib_stack]
    env["PYTHONPATH"] = os.pathsep.join(pp)
    env["INSAR_PROJECT_ROOT"] = PROJECT_ROOT
    env["PYTHONUNBUFFERED"] = "1"
    return env


def run(label: str, env: dict, log_file) -> int:
    argv = [
        get_python_exe(),
        STACK_SENTINEL_PY,
        "-s", SLC_DIR,
        "-o", ORBIT_DIR,
        "-a", AUX_DIR,
        "-w", WORK_DIR,
        "-d", DEM_PATH,
        "-p", "vv",
        "-W", "interferogram",
        "-n", "1",
        "-C", "geometry",
        "-c", "1",
        "--num_proc", "1",
        "-b", "31.72", "32.199", "101.78", "102.09",
    ]
    log_file.write(f"\n{'='*60}\n{label}\nCommand: {' '.join(argv)}\n")
    log_file.flush()
    os.makedirs(WORK_DIR, exist_ok=True)
    proc = subprocess.Popen(
        argv,
        cwd=WORK_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="replace",
    )
    line_count = 0
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            line_count += 1
            print(line, end="")
            log_file.write(line)
            log_file.flush()
    code = proc.wait()
    log_file.write(f"Exit code: {code}\n")
    log_file.flush()
    return code


def main():
    with open(OUTPUT_LOG, "w", encoding="utf-8") as f:
        f.write("stackSentinel diagnostic: minimal PATH vs PATH with UCRT64\n")
        code_min = run("Run 1: MINIMAL PATH (no UCRT64)", build_env(include_ucrt64=False), f)
        code_ucrt = run("Run 2: PATH with UCRT64", build_env(include_ucrt64=True), f)
        f.write(f"\n-> Minimal PATH exit: {code_min}, With UCRT64 exit: {code_ucrt}\n")
    print(f"\nResult written to {OUTPUT_LOG}")
    return 0 if (code_min == 0 or code_ucrt == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
