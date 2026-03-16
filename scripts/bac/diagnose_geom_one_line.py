#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 geom_reference/IW1 下 hgt_01.rdr、lat_01.rdr、lon_01.rdr 的同一行（默认第 0 行），
按 LSB Float64 解析，打印 min/max/mean，用于判断是否「高程/纬度/经度」写错文件。
用法:
  python scripts/diagnose_geom_one_line.py "D:\processing\tianfu\processing\geom_reference\IW1"
  python scripts/diagnose_geom_one_line.py "D:\...\IW1" --line 100
"""
from __future__ import print_function

import argparse
import os
import sys
import numpy as np


def read_line_as_float64_lsb(path, line_index, width):
    """Read one line (line_index) from raw Float64 LSB file; width in pixels."""
    size = width * 8
    offset = line_index * size
    with open(path, "rb") as f:
        f.seek(offset)
        raw = f.read(size)
    if len(raw) < size:
        return None
    return np.frombuffer(raw, dtype="<f8", count=width)


def main():
    parser = argparse.ArgumentParser(description="Read one line from hgt/lat/lon rdr and show stats.")
    parser.add_argument("geom_iw_dir", type=str, help="e.g. geom_reference/IW1 directory")
    parser.add_argument("--line", type=int, default=0, help="Line index (0-based)")
    parser.add_argument("--width", type=int, default=None, help="Width (default: read from .vrt or .xml)")
    args = parser.parse_args()

    base = os.path.abspath(args.geom_iw_dir)
    if not os.path.isdir(base):
        print("错误: 目录不存在:", base, file=sys.stderr)
        return 1

    # Default width from hgt VRT or XML if present
    width = args.width
    if width is None:
        for vrt_name in ("hgt_01.rdr.vrt", "hgt_01.vrt"):
            vrt = os.path.join(base, vrt_name)
            if os.path.isfile(vrt):
                with open(vrt, "r", encoding="utf-8") as f:
                    for line in f:
                        if "RasterXSize" in line or "rasterXSize" in line:
                            import re
                            m = re.search(r"[Rr]aster[Xx]Size=\"(\d+)\"", line)
                            if m:
                                width = int(m.group(1))
                                break
                if width is not None:
                    break
        if width is None:
            width = 21580  # fallback typical S1 burst

    line_idx = args.line
    files = [
        ("hgt_01.rdr", "高程(m)", -500, 10000),
        ("lat_01.rdr", "纬度(°)", -90, 90),
        ("lon_01.rdr", "经度(°)", -180, 180),
    ]
    print("目录: {}".format(base))
    print("行号: {} (0-based), 宽度: {}".format(line_idx, width))
    print("")
    for fname, label, expect_min, expect_max in files:
        path = os.path.join(base, fname)
        if not os.path.isfile(path):
            print("{}: 文件不存在".format(fname))
            continue
        arr = read_line_as_float64_lsb(path, line_idx, width)
        if arr is None:
            print("{}: 读取失败或行越界".format(fname))
            continue
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            print("{} ({}): 无有效值, raw min={:.4f} max={:.4f}".format(
                fname, label, float(np.nanmin(arr)), float(np.nanmax(arr))))
        else:
            mn, mx, mu = finite.min(), finite.max(), finite.mean()
            ok = expect_min <= mn and mx <= expect_max
            status = " [合理]" if ok else " [异常]"
            print("{} ({}): min={:.4f} max={:.4f} mean={:.4f}{}".format(
                fname, label, float(mn), float(mx), float(mu), status))
    print("")
    print("若 hgt 显示经度范围(-180~180)或 lat/lon 显示高程范围(几百~几千)，可能是 accessor 与文件对应错乱。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
