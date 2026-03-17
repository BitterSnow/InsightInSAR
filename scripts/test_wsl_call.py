#!/usr/bin/env python3
"""
Test WSL invocation OUTSIDE of the Desktop app.

Usage (PowerShell):
  .venv\\Scripts\\python.exe scripts\\test_wsl_call.py

Optional environment variables:
  INSAR_WSL_DISTRO=Ubuntu|default|<your distro name>
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple


def wsl_exe() -> str:
    if os.name != "nt":
        return "wsl"
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    full = os.path.join(sysroot, "System32", "wsl.exe")
    return full if os.path.isfile(full) else "wsl.exe"


def get_distro() -> Optional[str]:
    v = (os.environ.get("INSAR_WSL_DISTRO") or "").strip()
    if not v:
        return "Ubuntu"
    if v.lower() == "default":
        return None
    return v


def run(argv: List[str], timeout: int = 20) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:
        return -999, "", f"{type(e).__name__}: {e}"


def banner(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def main() -> int:
    exe = wsl_exe()
    distro = get_distro()

    banner("Environment")
    print(f"platform: {sys.platform}")
    print(f"python:   {sys.executable}")
    print(f"wsl.exe:  {exe}")
    print(f"PATH has wsl.exe: {bool(shutil.which('wsl.exe') or shutil.which('wsl'))}")
    print(f"INSAR_WSL_DISTRO: {os.environ.get('INSAR_WSL_DISTRO')!r} -> {distro!r}")

    banner("Check: wsl.exe exists and runnable")
    code, out, err = run([exe, "--status"], timeout=20)
    print(f"returncode: {code}")
    if out.strip():
        print("--- stdout ---")
        print(out.rstrip())
    if err.strip():
        print("--- stderr ---")
        print(err.rstrip())

    banner("Check: bash command (default distro)")
    argv = [exe]
    if distro:
        argv += ["-d", distro]
    argv += ["-e", "bash", "-lc", "echo OK_FROM_WSL && uname -a && whoami"]
    code, out, err = run(argv, timeout=20)
    print(f"argv: {' '.join(argv)}")
    print(f"returncode: {code}")
    if out.strip():
        print("--- stdout ---")
        print(out.rstrip())
    if err.strip():
        print("--- stderr ---")
        print(err.rstrip())

    banner("Check: wslpath conversion")
    win_path = os.path.abspath(os.path.join(os.getcwd(), ".."))  # project root guess
    argv = [exe]
    if distro:
        argv += ["-d", distro]
    argv += ["-e", "wslpath", "-a", win_path.replace("\\", "/")]
    code, out, err = run(argv, timeout=20)
    print(f"win_path: {win_path}")
    print(f"argv: {' '.join(argv)}")
    print(f"returncode: {code}")
    if out.strip():
        print("--- stdout ---")
        print(out.rstrip())
    if err.strip():
        print("--- stderr ---")
        print(err.rstrip())

    banner("Summary")
    if code == -999:
        print("FAIL: subprocess exception occurred (see stderr above).")
        return 2
    print("If any step above shows Permission denied / Access is denied,")
    print("then the issue is system-level (outside the app).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

