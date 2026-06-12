"""
DEM 制作：在 WSL 内调用 ISCE2 applications/dem.py 进行 SRTM 拼接。
支持根据工作区+Swath 计算 DEM 范围、缺失瓦片从 ESA SRTMGL1 自动下载。
"""
from __future__ import annotations

import logging
import math
import os
import shutil
import time
import zipfile
import urllib.request
from typing import Callable, List, Optional, Tuple

from backend.services import wsl_runner

logger = logging.getLogger(__name__)

ESA_SRTMGL1_URL = "https://step.esa.int/auxdata/dem/SRTMGL1"


def get_dem_bbox_from_workspace_safe(
    bbox_snwe: Tuple[float, float, float, float],
    safe_path: Optional[str] = None,
) -> Tuple[int, int, int, int]:
    """
    根据定义的工作区与 SAFE 数据计算需拼接的 DEM 范围（整数 S,N,W,E）。
    若提供 safe_path（.zip）则通过 Swath 检测器取所需 Swath 的并集范围；
    否则直接用工作区 bbox 扩展到整度。
    """
    south, north, west, east = bbox_snwe
    if safe_path and os.path.isfile(safe_path) and safe_path.lower().endswith(".zip"):
        try:
            import sys
            _scripts = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
            if _scripts not in sys.path:
                sys.path.insert(0, _scripts)
            from subswath_detector import SubswathDetector
            detector = SubswathDetector(sentinel1_zip_path=safe_path, bbox_snwe=(south, north, west, east))
            swaths = detector.detect_subswaths()
            footprints = detector.extract_subswath_footprints()
            if swaths and footprints:
                min_lon = min(footprints[s][0] for s in swaths if s in footprints)
                min_lat = min(footprints[s][1] for s in swaths if s in footprints)
                max_lon = max(footprints[s][2] for s in swaths if s in footprints)
                max_lat = max(footprints[s][3] for s in swaths if s in footprints)
                south = min_lat
                north = max_lat
                west = min_lon
                east = max_lon
        except Exception:
            pass
    dem_s = int(math.floor(south))
    dem_n = int(math.ceil(north))
    dem_w = int(math.floor(west))
    dem_e = int(math.ceil(east))
    return (dem_s, dem_n, dem_w, dem_e)


def format_srtm_tile_name(lat: int, lon: int) -> str:
    """
    SRTMGL1 瓦片名：纬度 2 位、经度 3 位（如 N28E096、N08E105、S35W074）。
    """
    lat_str = f"N{abs(lat):02d}" if lat >= 0 else f"S{abs(lat):02d}"
    lon_str = f"E{abs(lon):03d}" if lon >= 0 else f"W{abs(lon):03d}"
    return lat_str + lon_str


def list_srtm_tiles_for_bbox(south: int, north: int, west: int, east: int) -> List[str]:
    """返回覆盖 bbox 所需的 SRTM 1°x1° 瓦片名列表，如 ['N26E105', 'S35W074']。"""
    tiles: List[str] = []
    for lat in range(south, north):
        for lon in range(west, east):
            tiles.append(format_srtm_tile_name(lat, lon))
    return tiles


def _download_srtm_tile(tile_name: str, dest_dir: str, stream_callback: Optional[Callable[[str], None]] = None) -> None:
    """下载单块 SRTMGL1 瓦片 zip 到 dest_dir 并解压出 .hgt。"""
    url = f"{ESA_SRTMGL1_URL}/{tile_name}.SRTMGL1.hgt.zip"
    zip_path = os.path.join(dest_dir, f"{tile_name}.SRTMGL1.hgt.zip")
    if stream_callback:
        stream_callback(f"下载 {tile_name}: {url}\n")
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)
    if stream_callback:
        stream_callback(f"已解压 {tile_name}\n")


def ensure_srtm_tiles_in_dir(
    raw_dir: str,
    south: int,
    north: int,
    west: int,
    east: int,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """
    确保 raw_dir 中存在覆盖 bbox 的 SRTM 瓦片；缺失则从 ESA 下载并解压。
    若某瓦片已有 .hgt 或 .SRTMGL1.hgt.zip 则跳过。
    """
    tiles = list_srtm_tiles_for_bbox(south, north, west, east)
    for tile_name in tiles:
        hgt_path = os.path.join(raw_dir, f"{tile_name}.hgt")
        zip_path = os.path.join(raw_dir, f"{tile_name}.SRTMGL1.hgt.zip")
        if os.path.isfile(hgt_path):
            continue
        if os.path.isfile(zip_path):
            try:
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(raw_dir)
            except Exception:
                pass
            if os.path.isfile(hgt_path):
                continue
        try:
            _download_srtm_tile(tile_name, raw_dir, stream_callback)
        except Exception as e:
            if stream_callback:
                stream_callback(f"下载 {tile_name} 失败: {e}\n")
            raise


def run_dem_stitch_wsl(
    bbox_south: int,
    bbox_north: int,
    bbox_west: int,
    bbox_east: int,
    dem_raw_dir: str,
    output_dir: str,
    output_name: Optional[str] = None,
    correct_egm96: bool = True,
    timeout: Optional[int] = 3600,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    1) 若 dem_raw_dir 中缺少覆盖 bbox 的 SRTM 瓦片，则从 ESA 下载并解压；
    2) 在 WSL 内执行 dem.py -a stitch -l -s 1，用本地瓦片拼接 DEM（结果先写在 dem_raw_dir）；
    3) 将生成的文件复制到 output_dir，并返回输出目录中的主文件路径。
    dem_raw_dir: DEM 原始瓦片所在文件夹；output_dir: 拼接结果输出目录（可与 dem_raw_dir 不同）。
    """
    if stream_callback:
        stream_callback("检查并补充 SRTM 瓦片…\n")
    try:
        ensure_srtm_tiles_in_dir(
            dem_raw_dir,
            bbox_south,
            bbox_north,
            bbox_west,
            bbox_east,
            stream_callback=stream_callback,
        )
    except Exception as e:
        logger.exception("补充 SRTM 瓦片失败: %s", e)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": f"补充 SRTM 瓦片失败: {e}",
            "output_path": None,
        }
    if stream_callback:
        stream_callback("瓦片就绪，在 WSL 内执行 dem.py 拼接…\n")
    if not wsl_runner.use_wsl():
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": "DEM 制作需在 WSL 模式下运行（INSAR_USE_WSL=1）。请使用 scripts/start_desktop_wsl.bat 启动。",
            "output_path": None,
        }
    isce_env, isce_env_err = wsl_runner.build_wsl_isce2_extra_env()
    if isce_env_err or not isce_env:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": isce_env_err or "无法定位 WSL conda ISCE2 环境。",
            "output_path": None,
        }
    isce2_main = isce_env.get("INSAR_WSL_ISCE2_MAIN") or ""
    if not isce2_main:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": "未找到 WSL ISCE2 包路径（INSAR_WSL_ISCE2_MAIN）。",
            "output_path": None,
        }
    # 清理路径中的空字节和非法字符，防止 embedded null character 错误
    dem_raw_dir_clean = dem_raw_dir.replace("\x00", "").strip()
    output_dir_clean = output_dir.replace("\x00", "").strip()
    env_script = wsl_runner.get_wsl_env_script()
    out_dir_wsl, path_err = wsl_runner.resolve_windows_path_to_wsl(dem_raw_dir_clean)
    if path_err or not out_dir_wsl:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": path_err or "DEM 原始数据目录在 WSL 中不可访问。",
            "output_path": None,
        }
    safe_isce2 = isce2_main.replace("'", "'\"'\"'")
    safe_dir = out_dir_wsl.replace("'", "'\"'\"'")
    if stream_callback:
        stream_callback(f"WSL 数据目录: {out_dir_wsl}\n")
    logger.info(
        "DEM stitch: bbox=(%s,%s,%s,%s), raw_dir=%s, output_dir=%s, wsl_out_dir=%s",
        bbox_south, bbox_north, bbox_west, bbox_east,
        dem_raw_dir_clean, output_dir_clean, out_dir_wsl,
    )
    # 整条 python 命令必须是一个 shell 词，不能再用 && 把 -a/-b 等拆成单独命令
    py_args = [
        "-a stitch",
        f"-b {bbox_south} {bbox_north} {bbox_west} {bbox_east}",
        "-s 1",
        f"-d '{safe_dir}'",
        "-l",
        "-m xml",
    ]
    if output_name:
        py_args.append(f"-o '{output_name}'")
    if correct_egm96:
        py_args.append("-c")
    py_cmd = " ".join(["PYTHONPATH='.:${PYTHONPATH:-}' python applications/dem.py"] + py_args)
    cmd = f"cd '{safe_isce2}' && {py_cmd}"
    extra_env: dict[str, str] = dict(isce_env)
    distro = wsl_runner.get_wsl_distro() or "Ubuntu"
    logger.info(
        "DEM stitch 在 WSL 内执行: distro=%s, isce2_root=%s, data_dir=%s",
        distro,
        isce2_main,
        out_dir_wsl,
    )
    if stream_callback:
        stream_callback(f"WSL 发行版: {distro}\n")
    result = wsl_runner.run_wsl(
        cmd,
        env_script=env_script,
        extra_env=extra_env or None,
        timeout=timeout,
        stream_callback=stream_callback,
    )
    if not result.get("success"):
        result["output_path"] = None
        logger.error("DEM stitch WSL 命令失败: %s", result.get("error_message"))
        return result

    # dem.py 输出在 dem_raw_dir；若 output_dir 与 dem_raw_dir 不同则复制到 output_dir，否则直接使用原路径
    raw_abs = os.path.abspath(os.path.normpath(dem_raw_dir_clean))
    out_abs = os.path.abspath(os.path.normpath(output_dir_clean))
    same_dir = raw_abs == out_abs

    def copy_if_needed(src: str, dst: str) -> None:
        if os.path.abspath(os.path.normpath(src)) != os.path.abspath(os.path.normpath(dst)):
            shutil.copy2(src, dst)

    os.makedirs(output_dir_clean, exist_ok=True)
    main_out_path = None
    if output_name:
        base = output_name
        for suffix in (".wgs84", ".wgs84.xml", ".dem", ".dem.xml"):
            src = os.path.join(dem_raw_dir_clean, base + suffix)
            if os.path.isfile(src):
                dst = os.path.join(output_dir_clean, os.path.basename(src))
                copy_if_needed(src, dst)
                if main_out_path is None and suffix in (".wgs84", ".dem"):
                    main_out_path = dst
    else:
        # 未指定 -o 时 dem.py 用 defaultName(bbox)，复制最近生成的非常规瓦片文件
        cutoff = time.time() - 120
        for name in os.listdir(dem_raw_dir_clean):
            if name.endswith(".hgt") or name.endswith(".zip"):
                continue
            path = os.path.join(dem_raw_dir_clean, name)
            if not os.path.isfile(path) or os.path.getmtime(path) < cutoff:
                continue
            dst = os.path.join(output_dir_clean, name)
            copy_if_needed(path, dst)
            if main_out_path is None and not name.endswith(".xml"):
                main_out_path = dst
        if main_out_path is None:
            for name in sorted(os.listdir(output_dir_clean)):
                main_out_path = os.path.join(output_dir_clean, name)
                break
    logger.info("DEM stitch 完成: output_path=%s", main_out_path)
    result["output_path"] = main_out_path
    return result
