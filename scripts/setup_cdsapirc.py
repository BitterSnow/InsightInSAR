#!/usr/bin/env python3
"""
将 CDS API 配置写入用户主目录 ~/.cdsapirc，供 MintPy/PyAPS ERA5 对流层校正使用。
可带参数指定 url 与 key，否则使用下方默认值（请勿将真实 key 提交到版本库）。
"""
from __future__ import annotations

import argparse
import os

DEFAULT_URL = "https://cds.climate.copernicus.eu/api"


def main() -> int:
    p = argparse.ArgumentParser(description="Write ~/.cdsapirc for CDS API (MintPy/PyAPS ERA5)")
    p.add_argument("--url", default=DEFAULT_URL, help="CDS API URL")
    p.add_argument("--key", default=os.environ.get("CDS_API_KEY", ""), help="CDS API key (或 set CDS_API_KEY=...)")
    args = p.parse_args()
    if not args.key:
        print("请提供 --key 或设置环境变量 CDS_API_KEY")
        return 1
    home = os.path.expanduser("~")
    rc = os.path.join(home, ".cdsapirc")
    content = f"url: {args.url}\nkey: {args.key}\n"
    try:
        with open(rc, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"已写入: {rc}")
        return 0
    except OSError as e:
        print(f"写入失败: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
