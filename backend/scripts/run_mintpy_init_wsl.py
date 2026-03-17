"""
WSL 内执行 MintPy 工作目录初始化。参数通过环境变量 INSAR_MINTPY_INIT_JSON 传入，结果 JSON 打印到 stdout。
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    raw = os.environ.get("INSAR_MINTPY_INIT_JSON")
    if not raw:
        print(json.dumps({"success": False, "error_message": "缺少 INSAR_MINTPY_INIT_JSON"}), file=sys.stderr)
        return 1
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error_message": str(e)}), file=sys.stderr)
        return 1
    work_dir = params.get("work_dir")
    stack_work_dir = params.get("stack_work_dir")
    stack_product_dir = params.get("stack_product_dir")
    custom_template_path = params.get("custom_template_path")
    if not work_dir:
        print(json.dumps({"success": False, "error_message": "缺少 work_dir"}), file=sys.stderr)
        return 1
    sys.path.insert(0, os.environ.get("INSAR_PROJECT_ROOT", "."))
    from backend.services.mintpy_processing_service import init_mintpy_workdir

    result = init_mintpy_workdir(
        work_dir=work_dir,
        stack_work_dir=stack_work_dir,
        stack_product_dir=stack_product_dir,
        custom_template_path=custom_template_path,
    )
    print(json.dumps(result))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
