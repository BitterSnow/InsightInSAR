#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断 topo 输出的 hgt/lat/lon 是否为字节序问题：分别按 LSB 和 MSB 读取 Float64，
看哪一端数值像高程（几百～几千米）。可选：检查 DEM 的 Int16 字节序。
用法:
  python scripts/diagnose_topo_byteorder.py --geom-dir "D:\\processing\\tianfu\\processing\\geom_reference"
  python scripts/diagnose_topo_byteorder.py --hgt "D:\\...\\geom_reference\\hgt.rdr" --dem "D:\\...\\dem.dem"
"""
from __future__ import print_function

import argparse
import os
import sys
import numpy


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose topo output (hgt.rdr) and optionally DEM byte order."
    )
    parser.add_argument(
        "--geom-dir",
        type=str,
        default=None,
        help="geom_reference 目录（内含 hgt.rdr, lat.rdr, lon.rdr）",
    )
    parser.add_argument(
        "--hgt",
        type=str,
        default=None,
        help="直接指定 hgt.rdr 文件路径（与 --geom-dir 二选一）",
    )
    parser.add_argument(
        "--dem",
        type=str,
        default=None,
        help="可选：DEM 原始文件路径（.dem），用于检查 DEM 字节序",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=1000 * 1000,
        help="采样像素数（每个 double 8 字节）；默认 1000000",
    )
    args = parser.parse_args()

    hgt_path = args.hgt
    if not hgt_path and args.geom_dir:
        hgt_path = os.path.join(
            os.path.abspath(args.geom_dir), "hgt.rdr"
        )
    if not hgt_path or not os.path.isfile(hgt_path):
        print("错误: 未找到 hgt.rdr。请指定 --geom-dir 或 --hgt。", file=sys.stderr)
        sys.exit(1)

    n = args.sample
    size = n * 8  # Float64
    print("=" * 60)
    print("1. 检查 hgt.rdr 字节序（前 {} 个 Float64）".format(n))
    print("   文件: {}".format(hgt_path))
    print("=" * 60)

    try:
        with open(hgt_path, "rb") as f:
            raw = f.read(size)
    except Exception as e:
        print("读取失败: {}".format(e), file=sys.stderr)
        sys.exit(1)

    if len(raw) < 8:
        print("文件过短。", file=sys.stderr)
        sys.exit(1)

    # LSB (little-endian) Float64
    arr_lsb = numpy.frombuffer(raw, dtype="<f8", count=len(raw) // 8)
    # MSB (big-endian) Float64
    arr_msb = numpy.frombuffer(raw, dtype=">f8", count=len(raw) // 8)

    valid_lsb = arr_lsb[numpy.isfinite(arr_lsb)]
    valid_msb = arr_msb[numpy.isfinite(arr_msb)]
    if valid_lsb.size == 0:
        valid_lsb = arr_lsb
    if valid_msb.size == 0:
        valid_msb = arr_msb

    print("LSB (小端, VRT 通常标 LSB):")
    print("  min={:.4f}, max={:.4f}, mean={:.4f}".format(
        float(valid_lsb.min()), float(valid_lsb.max()), float(valid_lsb.mean())
    ))
    print("MSB (大端):")
    print("  min={:.4f}, max={:.4f}, mean={:.4f}".format(
        float(valid_msb.min()), float(valid_msb.max()), float(valid_msb.mean())
    ))

    # 合理高程约 0–9000 m；合理纬度约 -90–90；经度 -180–180
    def looks_like_elevation(a):
        finite = a[numpy.isfinite(a)]
        if finite.size == 0:
            return False
        return -500 <= finite.min() and finite.max() <= 10000

    lsb_ok = looks_like_elevation(arr_lsb)
    msb_ok = looks_like_elevation(arr_msb)
    print("")
    if lsb_ok and not msb_ok:
        print("结论: LSB 数值像高程，MSB 不像。磁盘应为小端，VRT 标 LSB 正确；问题可能在 DEM/轨道或 topo 计算。")
    elif msb_ok and not lsb_ok:
        print("结论: MSB 数值像高程，LSB 不像。磁盘实际为大端，但 VRT 标为 LSB 会导致 QGIS 显示异常。")
        print("建议: 在 runTopo 中对 height/lat/lon Image 显式 setByteOrder('MSB') 后 createImage，或让 renderVRT 按实际写出 MSB。")
    elif lsb_ok and msb_ok:
        print("结论: LSB 与 MSB 均在合理范围，无法单靠此区分；或采样区恰好都合理。可增大 --sample 或查 DEM/轨道。")
    else:
        print("结论: LSB 与 MSB 均不像高程，可能 topo 输入有误（DEM、轨道、多普勒等）或计算异常。")

    if args.dem and os.path.isfile(args.dem):
        print("")
        print("=" * 60)
        print("2. 检查 DEM 字节序（前 50000 个 Int16）")
        print("   文件: {}".format(args.dem))
        print("   预期: 若为 SRTM/EGM96 高程，约 342–5638（参考 dem.aux.xml 统计）")
        print("=" * 60)
        try:
            with open(args.dem, "rb") as f:
                raw_dem = f.read(50000 * 2)
        except Exception as e:
            print("读取失败: {}".format(e), file=sys.stderr)
        else:
            if len(raw_dem) >= 2:
                d_lsb = numpy.frombuffer(raw_dem, dtype="<i2", count=len(raw_dem) // 2)
                d_msb = numpy.frombuffer(raw_dem, dtype=">i2", count=len(raw_dem) // 2)
                print("LSB Int16: min={}, max={}, mean={:.1f}".format(
                    int(d_lsb.min()), int(d_lsb.max()), float(d_lsb.mean())
                ))
                print("MSB Int16: min={}, max={}, mean={:.1f}".format(
                    int(d_msb.min()), int(d_msb.max()), float(d_msb.mean())
                ))
                if 300 <= d_lsb.min() and d_lsb.max() <= 6000:
                    print("LSB 落在常见高程范围，DEM 应为小端。")
                elif 300 <= d_msb.min() and d_msb.max() <= 6000:
                    print("MSB 落在常见高程范围，DEM 可能为大端或需检查。")

    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
