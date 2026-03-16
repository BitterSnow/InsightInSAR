#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只跑 Step 1 中 topo 的「第一个 burst」，跑完后即可用 QGIS 打开 geom_reference/IW1 下的
hgt_01.rdr.vrt、lat_01.rdr.vrt、lon_01.rdr.vrt 查看，无需等 5 个 burst 全部跑完。

推荐用法（保证与 Step 1 相同的 Python 环境）:
  .\\scripts\\run_topo_burst1_only.ps1 -WorkDir D:\\processing\\tianfu\\processing

也可直接调 Python（需已激活 isce2-build 或设置好 PYTHONPATH）:
  set WORK_DIR=D:\\processing\\tianfu\\processing
  python scripts/run_topo_burst1_only.py
  python scripts/run_topo_burst1_only.py --work-dir D:\\processing\\tianfu\\processing
"""
from __future__ import print_function

import configparser
import os
import subprocess
import sys


def _find_topo_params(work_dir):
    config_path = os.path.join(work_dir, "configs", "config_reference")
    if not os.path.isfile(config_path):
        return None, "config_reference 不存在: %s" % config_path

    parser = configparser.ConfigParser(delimiters=(':'), allow_no_value=True)
    parser.optionxform = str
    with open(config_path, "r", encoding="utf-8", errors="replace") as f:
        parser.read_file(f)

    def get_opt(section, key):
        for k, v in parser.items(section):
            if k.strip() == key:
                return (v or "").strip()
        return ""

    for section in parser.sections():
        if not section.startswith("Function-"):
            continue
        items = list(parser.items(section))
        if not items:
            continue
        # First option in section is the function name (e.g. topo)
        func_name = (items[0][0] or "").strip()
        if func_name != "topo":
            continue
        ref = get_opt(section, "reference")
        dem = get_opt(section, "dem")
        geom = get_opt(section, "geom_referenceDir")
        if not ref or not dem or not geom:
            return None, "config_reference 中 topo 缺少 reference/dem/geom_referenceDir"
        # paths in config may be relative to work_dir
        if not os.path.isabs(ref):
            ref = os.path.normpath(os.path.join(work_dir, ref))
        if not os.path.isabs(dem):
            dem = os.path.normpath(os.path.join(work_dir, dem))
        if not os.path.isabs(geom):
            geom = os.path.normpath(os.path.join(work_dir, geom))
        return (ref, dem, geom), None

    return None, "config_reference 中未找到 topo 段落"


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, project_root)

    work_dir = os.environ.get("WORK_DIR", "").strip()
    if "--work-dir" in sys.argv:
        i = sys.argv.index("--work-dir")
        if i + 1 < len(sys.argv):
            work_dir = sys.argv[i + 1]
    if not work_dir or not os.path.isdir(work_dir):
        work_dir = os.path.join(project_root, "processing_check")
    if not os.path.isdir(work_dir):
        work_dir = r"D:\processing\tianfu\processing"
    if not os.path.isdir(work_dir):
        print("未找到工作目录。请设置 WORK_DIR 或使用 --work-dir <path>")
        return 1

    params, err = _find_topo_params(work_dir)
    if err:
        print(err)
        return 1

    reference, dem, geom_reference_dir = params
    if not os.path.isdir(reference):
        print("reference 目录不存在:", reference)
        return 1
    if not os.path.isfile(dem) and not os.path.isfile(dem + ".xml"):
        print("dem 不存在:", dem)
        return 1

    from backend.services.stack_processing_service import _get_stack_env, _get_stack_python_exe

    env = _get_stack_env(work_dir)
    python_exe = _get_stack_python_exe()
    tops_stack = os.path.join(project_root, "lib", "isce2-main", "contrib", "stack", "topsStack")
    topo_script = os.path.join(tops_stack, "topo.py")

    if not os.path.isfile(topo_script):
        print("未找到 topo.py:", topo_script)
        return 1

    env["INSAR_PROJECT_ROOT"] = project_root
    cmd = [
        python_exe, topo_script,
        "-m", reference,
        "-d", dem,
        "-g", geom_reference_dir,
        "-b", "1",
        "-n", "1",
    ]
    print("只跑第一个 burst 的 topo（约几分钟）。")
    print("命令:", " ".join(cmd))
    print("工作目录:", work_dir)
    ret = subprocess.run(cmd, env=env, cwd=work_dir)
    if ret.returncode != 0:
        print("topo 退出码:", ret.returncode)
        return ret.returncode

    iw1 = os.path.join(geom_reference_dir, "IW1")
    print("\n完成。请用 QGIS 打开以下文件查看:")
    for name in ["hgt_01.rdr.vrt", "lat_01.rdr.vrt", "lon_01.rdr.vrt"]:
        p = os.path.join(iw1, name)
        if os.path.isfile(p):
            print("  ", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
