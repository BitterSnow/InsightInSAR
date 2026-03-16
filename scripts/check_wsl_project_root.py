#!/usr/bin/env python3
"""
检查 WSL 项目根（INSAR_WSL_PROJECT_ROOT）是否正确：
- 是否已设置
- 在 WSL 内该路径是否存在
- 是否包含 lib/MintPy-main/src（MintPy 步骤会优先使用本仓库版本）

用法：
  1) 用 start_desktop_wsl.bat 启动后，在相同环境运行此脚本（会继承 INSAR_WSL_PROJECT_ROOT）
  2) 或先设置再运行： set INSAR_WSL_PROJECT_ROOT=/mnt/d/coding/insar-system && python scripts/check_wsl_project_root.py
"""
from __future__ import annotations

import os
import sys

# 保证可导入 backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def main() -> int:
    os.environ.setdefault("INSAR_USE_WSL", "1")
    from backend.services.wsl_runner import check_wsl_project_root

    result = check_wsl_project_root()
    ok = result.get("ok", False)
    msg = result.get("message", "")
    path = result.get("path")
    mintpy_ok = result.get("mintpy_src_exists")

    print("WSL 项目根检查")
    print("-" * 50)
    if path:
        print(f"  路径: {path}")
    print(f"  结果: {'通过' if ok else '未通过'}")
    if mintpy_ok is not None:
        print(f"  lib/MintPy-main/src: {'存在' if mintpy_ok else '不存在'}")
    print(f"  说明: {msg}")
    print("-" * 50)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
