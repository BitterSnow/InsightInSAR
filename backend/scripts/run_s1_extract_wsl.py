"""
WSL 内执行单景 S1 导入（run_sentinel1_extract）。参数通过环境变量 INSAR_S1_EXTRACT_JSON 传入，结果 JSON 打印到 stdout。
供 Windows 侧通过 wsl_runner 调用。
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    raw = os.environ.get("INSAR_S1_EXTRACT_JSON")
    if not raw:
        print(json.dumps({"success": False, "error_message": "缺少 INSAR_S1_EXTRACT_JSON"}), file=sys.stderr)
        return 1
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error_message": str(e)}), file=sys.stderr)
        return 1
    zip_path = params.get("zip_path")
    orbit_dir = params.get("orbit_dir")
    dem_path = params.get("dem_path")
    aux_dir = params.get("aux_dir")
    out_dir = params.get("out_dir")
    swaths = params.get("swaths", [1, 2, 3])
    polarization = params.get("polarization", "vv")
    region_of_interest = params.get("region_of_interest")
    if not all([zip_path, orbit_dir, out_dir]):
        print(json.dumps({"success": False, "error_message": "缺少 zip_path/orbit_dir/out_dir"}), file=sys.stderr)
        return 1
    sys.path.insert(0, os.environ.get("INSAR_PROJECT_ROOT", "."))
    from backend.services.s1_processing_service import run_sentinel1_extract

    def progress_cb(pct: float, msg: str) -> None:
        print(f"[{pct:.1f}%] {msg}", flush=True)

    result = run_sentinel1_extract(
        zip_path=zip_path,
        orbit_dir=orbit_dir,
        dem_path=dem_path or "",
        aux_dir=aux_dir or "",
        out_dir=out_dir,
        swaths=swaths,
        polarization=polarization,
        region_of_interest=region_of_interest,
        progress_callback=progress_cb,
        virtual_slc=True,
    )
    print(json.dumps(result))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
