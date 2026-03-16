#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速看 geom_reference/IW1 下 lat/lon/hgt 的 .rdr 文件前 4 个 Float64（LSB）是否合理。
若此处正常而 QGIS 仍显示 179/-179，则问题在 VRT 或 QGIS 解释方式。
用法: python scripts/diagnose_geom_first_values.py [geom_iw1_dir]
"""
from __future__ import print_function
import os
import sys
import struct

def read_first_doubles(path, n=4):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read(n * 8)
        if len(raw) < n * 8:
            return None
        return [struct.unpack("<d", raw[i*8:(i+1)*8])[0] for i in range(n)]
    except Exception:
        return None

def main():
    geom_iw1 = sys.argv[1] if len(sys.argv) > 1 else r"D:\processing\tianfu\processing\geom_reference\IW1"
    for name, expect in [("lat_01.rdr", "纬度 -90~90"), ("lon_01.rdr", "经度 -180~180"), ("hgt_01.rdr", "高程 约 0~几千米")]:
        path = os.path.join(geom_iw1, name)
        vals = read_first_doubles(path)
        if vals is None:
            print("{}: 无文件或读失败".format(name))
            continue
        print("{} (LSB 前4): {}  <- 期望 {}".format(name, [round(x, 4) for x in vals], expect))
    print("\n若 lat~31、lon~101、hgt 合理而 QGIS 仍 179/-179，请检查 VRT 的 ByteOrder/DataType 或改用“栅格 → 其他”手动指定 Float64 LSB 打开 .rdr。")

if __name__ == "__main__":
    main()
