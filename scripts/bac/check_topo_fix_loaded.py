#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在「与 stack 子进程相同」的 PYTHONPATH 下导入 zerodop.topozero，检查实际加载的
Topozero.createImages 是否包含 setLength 与 createFile 修复。
用法（由 run_topo_checks.ps1 设置 env 后调用，或手动）:
  set PYTHONPATH=<project>;<install_packages>;<topsStack>;...
  python scripts/check_topo_fix_loaded.py
"""
from __future__ import print_function

import inspect
import os
import sys


def main():
    project_root = os.environ.get("INSAR_PROJECT_ROOT") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    install_packages = os.path.join(project_root, "lib", "isce2-main", "install", "packages")
    tops_stack = os.path.join(project_root, "lib", "isce2-main", "contrib", "stack", "topsStack")
    contrib_stack = os.path.join(project_root, "lib", "isce2-main", "contrib", "stack")

    for path in (project_root, install_packages, tops_stack, contrib_stack):
        if path not in sys.path and os.path.isdir(path):
            sys.path.insert(0, path)

    print("PYTHONPATH (first 5):", [os.path.basename(p) for p in sys.path[:5]])
    print("")

    # Same load order as topsStack/topo.py: import isce adds isce/components to path, then zerodop is found
    try:
        import isce  # adds isce/components to sys.path so zerodop.topozero is findable
    except Exception as e:
        print("导入 isce 失败:", e)
        return 1
    try:
        from zerodop.topozero import createTopozero
        topo_obj = createTopozero()
        Topo = type(topo_obj)
    except Exception as e:
        print("导入 zerodop.topozero.createTopozero 失败:", e)
        return 1

    try:
        source_file = inspect.getfile(Topo)
    except Exception:
        source_file = "unknown"
    print("加载的 Topo 类来自:", source_file)
    print("")

    if not hasattr(Topo, "createImages"):
        print("Topo 无 createImages 方法")
        return 1
    try:
        source = inspect.getsource(Topo.createImages)
    except Exception as e:
        print("无法获取 createImages 源码:", e)
        return 1

    has_set_length = "setLength(self.length)" in source or "setLength(self.length)" in source
    has_create_file = "createFile(self.length)" in source
    has_ensure_block = "Ensure all write-mode output images have length set" in source

    print("createImages 中是否含 setLength(self.length):", has_set_length)
    print("createImages 中是否含 createFile(self.length):", has_create_file)
    print("createImages 中是否含修复说明注释块:", has_ensure_block)
    print("")
    if has_set_length and has_create_file:
        print("结论: 已加载带 setLength+createFile 修复的 Topozero。")
    else:
        print("结论: 当前加载的 Topozero 未包含修复，请确认 install/packages 下三处 Topozero.py 已修改。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
