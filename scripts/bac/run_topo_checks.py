#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用与 stack 子进程相同的环境运行 topo 相关检查：
1) 检查实际加载的 Topozero 是否含 setLength+createFile 修复
2) 可选：仅执行 Step 1（run_01）后可由用户再跑诊断脚本

用法:
  python scripts/run_topo_checks.py                    # 只做 (1)
  python scripts/run_topo_checks.py --run-step1       # (1) + 执行 Step 1（耗时长）
"""
from __future__ import print_function

import os
import subprocess
import sys


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, project_root)
    from backend.services.stack_processing_service import _get_stack_env, _get_stack_python_exe

    work_dir = os.environ.get("WORK_DIR", "").strip()
    if not work_dir or not os.path.isdir(work_dir):
        work_dir = os.path.join(project_root, "processing_check")
    if not os.path.isdir(work_dir):
        work_dir = r"D:\processing\tianfu\processing"
    if not os.path.isdir(work_dir):
        work_dir = project_root

    env = _get_stack_env(work_dir)
    python_exe = _get_stack_python_exe()
    check_script = os.path.join(project_root, "scripts", "check_topo_fix_loaded.py")
    env["INSAR_PROJECT_ROOT"] = project_root

    print("=== 1. 检查实际加载的 Topozero 是否含 setLength+createFile 修复 ===\n")
    ret = subprocess.run(
        [python_exe, check_script],
        env=env,
        cwd=project_root,
    )
    if ret.returncode != 0:
        print("检查脚本退出码:", ret.returncode)
        return ret.returncode

    run_step1 = "--run-step1" in sys.argv
    if run_step1:
        config = os.path.join(work_dir, "configs", "config_reference")
        if not os.path.isfile(config):
            print("未找到 config_reference，跳过 Step 1。路径:", config)
            return 0
        print("\n=== 2. 执行 Step 1 (SentinelWrapper -c config_reference) ===\n")
        wrapper = os.path.join(
            project_root, "lib", "isce2-main", "contrib", "stack", "topsStack", "SentinelWrapper.py"
        )
        ret = subprocess.run(
            [python_exe, wrapper, "-c", config],
            env=env,
            cwd=work_dir,
        )
        if ret.returncode != 0:
            print("Step 1 退出码:", ret.returncode)
            return ret.returncode
        print("Step 1 完成。请再运行: python scripts/diagnose_topo_byteorder.py --hgt <geom_reference/IW1/hgt_01.rdr>")
    else:
        print("\n如需重跑 Step 1 后再诊断，请执行: python scripts/run_topo_checks.py --run-step1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
