#!/usr/bin/env python3
"""
Copy libfilter.dll from ISCE2 build dir to install dir (for Windows, 方案A).
Run after: cmake --build lib/isce2-main --target libfilter
Use when: you have not run full 'cmake --install' but need Step10 (filter/coherence) to find the DLL.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISCE2 = os.path.join(ROOT, "lib", "isce2-main")
BUILD_DLL = os.path.join(ISCE2, "build", "components", "mroipac", "filter", "libfilter.dll")
INSTALL_DIRS = [
    os.path.join(ISCE2, "install", "packages", "isce", "components", "mroipac", "filter"),
    os.path.join(ISCE2, "install", "packages", "isce2", "components", "mroipac", "filter"),
]

def main():
    if not os.path.isfile(BUILD_DLL):
        print("Build libfilter first: cmake --build lib/isce2-main --target libfilter")
        return 1
    for dest_dir in INSTALL_DIRS:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, "libfilter.dll")
        shutil.copy2(BUILD_DLL, dest)
        print("Copied:", dest)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
