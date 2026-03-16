#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Section 11 排查：VRT 元数据检查 + hgt_01.rdr 原始字节验证（LSB/MSB）。
用法: python scripts/diagnose_geom_troubleshoot.py [geom_iw1_dir]
默认: D:\\processing\\tianfu\\processing\\geom_reference\\IW1
"""
from __future__ import print_function
import os
import sys
import struct
import xml.etree.ElementTree as ET

def main():
    geom_iw1 = sys.argv[1] if len(sys.argv) > 1 else r"D:\processing\tianfu\processing\geom_reference\IW1"
    hgt_rdr = os.path.join(geom_iw1, "hgt_01.rdr")
    hgt_vrt = os.path.join(geom_iw1, "hgt_01.rdr.vrt")
    config_glob = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(geom_iw1))), "configs", "config_run_01*")

    print("=" * 60)
    print("11.2 VRT metadata: {}".format(hgt_vrt))
    print("=" * 60)
    if not os.path.isfile(hgt_vrt):
        print("VRT not found, skip.")
    else:
        try:
            tree = ET.parse(hgt_vrt)
            root = tree.getroot()
            # GDAL VRT: SourceFilename, DataType (e.g. Float64), ByteOrder in band or raster
            for node in root.iter():
                if node.tag.endswith("SourceFilename") or node.tag == "SourceFilename":
                    print("  SourceFilename: {}".format(node.text or ""))
                if "ByteOrder" in (node.attrib or {}):
                    print("  ByteOrder (attr): {}".format(node.attrib.get("ByteOrder")))
            # Some VRT use Metadata with key
            for m in root.iter():
                if m.tag.endswith("Metadata") and m.attrib.get("domain") == "IMAGE_STRUCTURE":
                    for c in m:
                        if "ByteOrder" in str(c.attrib):
                            print("  ByteOrder: {}".format(c.attrib.get("name"), c.text))
            # Plain text scan for ByteOrder / DataType
            with open(hgt_vrt, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if "ByteOrder" in text or "byteOrder" in text:
                for line in text.splitlines():
                    if "ByteOrder" in line or "byteOrder" in line or "DataType" in line or "dataType" in line:
                        print("  " + line.strip())
            if "Float64" in text or "Float32" in text:
                print("  (VRT 中含 Float64/Float32 描述)")
            else:
                print("  (未在 VRT 中显式找到 DataType/ByteOrder 行)")
        except Exception as e:
            print(" 解析 VRT 异常: {}".format(e))

    print()
    print("=" * 60)
    print("11.3 原始字节验证: {}".format(hgt_rdr))
    print("=" * 60)
    if not os.path.isfile(hgt_rdr):
        print("未找到 .rdr 文件，跳过。")
        return
    n_doubles = 16
    n_bytes = n_doubles * 8
    try:
        with open(hgt_rdr, "rb") as f:
            raw = f.read(n_bytes)
    except Exception as e:
        print(" 读取失败: {}".format(e))
        return
    if len(raw) < 16:
        print(" 文件过短。")
        return
    # LSB
    lsb_vals = []
    for i in range(min(n_doubles, len(raw) // 8)):
        lsb_vals.append(struct.unpack("<d", raw[i*8:(i+1)*8])[0])
    # MSB
    msb_vals = []
    for i in range(min(n_doubles, len(raw) // 8)):
        msb_vals.append(struct.unpack(">d", raw[i*8:(i+1)*8])[0])

    def valid_range(vals, name, low=-500, high=10000):
        v = [x for x in vals if x == x and abs(x) != float("inf")]
        if not v:
            print("  {}: no valid (all NaN/Inf)".format(name))
            return
        mn, mx = min(v), max(v)
        ok = low <= mn and mx <= high
        print("  {}: min={:.4f} max={:.4f} first4={} {}".format(
            name, mn, mx, [round(x, 2) for x in vals[:4]], "[OK]" if ok else "[ABNORMAL]"))
    valid_range(lsb_vals, "LSB")
    valid_range(msb_vals, "MSB")
    print("  First 32 bytes (hex):", raw[:32].hex())

    print()
    print("=" * 60)
    print("11.1 检查 run_01 进程数 (config 路径)")
    print("=" * 60)
    processing_dir = os.path.dirname(os.path.dirname(geom_iw1))
    config_dir = os.path.join(processing_dir, "configs")
    if os.path.isdir(config_dir):
        for name in os.listdir(config_dir):
            if name.startswith("config_run_01"):
                path = os.path.join(config_dir, name)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "numProcess" in line or "num_process" in line.lower():
                                print("  {}: {}".format(name, line.strip()))
                except Exception as e:
                    print("  {}: 读失败 {}".format(name, e))
    else:
        print("  configs 目录不存在: {}".format(config_dir))
    print()
    print("Done.")

if __name__ == "__main__":
    main()
