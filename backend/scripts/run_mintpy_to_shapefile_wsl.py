"""
WSL 内执行 MintPy 转矢量。参数经环境变量 INSAR_MINTPY_VECTOR_JSON（JSON）传入，结果 JSON 打印到 stdout。
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    raw = os.environ.get("INSAR_MINTPY_VECTOR_JSON")
    if not raw:
        print(json.dumps({"success": False, "error_message": "缺少 INSAR_MINTPY_VECTOR_JSON"}), file=sys.stderr)
        return 1
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error_message": str(e)}), file=sys.stderr)
        return 1

    vel_path = params.get("vel_path")
    h5_file_path = params.get("h5_file_path")
    out_dir = params.get("out_dir")
    pixel_span = int(params.get("pixel_span") or 1)
    output_format = params.get("output_format") or "gpkg"
    max_points = int(params.get("max_points") or 0)

    if not vel_path or not h5_file_path or not out_dir:
        print(json.dumps({"success": False, "error_message": "缺少 vel_path / h5_file_path / out_dir"}), file=sys.stderr)
        return 1

    root = os.environ.get("INSAR_PROJECT_ROOT", ".")
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from backend.tools.mintpy_to_shapefile import run_mintpy_to_shapefile

        count, out_file = run_mintpy_to_shapefile(
            vel_path,
            h5_file_path,
            out_dir,
            pixel_span=pixel_span,
            output_format=output_format,
            max_points=max_points,
        )
        print(json.dumps({"success": True, "count": count, "output_path": out_file}))
        return 0
    except Exception as e:
        print(json.dumps({"success": False, "error_message": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
