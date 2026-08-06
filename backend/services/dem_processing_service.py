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


def _shell_single_quote(path: str) -> str:
    """Bash 单引号安全转义。"""
    return "'" + (path or "").replace("'", "'\"'\"'") + "'"


def build_dem_stitch_command(
    isce2_main_wsl: str,
    dem_raw_dir_wsl: str,
    bbox_south: int,
    bbox_north: int,
    bbox_west: int,
    bbox_east: int,
    output_name: Optional[str] = None,
    correct_egm96: bool = True,
) -> str:
    """
    构造 dem.py 拼接命令：工作目录为 dem_raw_dir（非 ISCE2 包目录），
    以便 Correct_geoid 写出的 basename.dem.wgs84 落在数据目录。
    """
    safe_isce2 = _shell_single_quote(isce2_main_wsl.rstrip("/"))
    safe_raw = _shell_single_quote(dem_raw_dir_wsl.rstrip("/"))
    dem_py = _shell_single_quote(f"{isce2_main_wsl.rstrip('/')}/applications/dem.py")
    py_args = [
        "-a stitch",
        f"-b {int(bbox_south)} {int(bbox_north)} {int(bbox_west)} {int(bbox_east)}",
        "-s 1",
        f"-d {safe_raw}",
        "-l",
        "-m xml",
    ]
    if output_name:
        safe_name = output_name.replace("'", "'\"'\"'")
        py_args.append(f"-o '{safe_name}'")
    if correct_egm96:
        py_args.append("-c")
    # PYTHONPATH 指向 isce 包根，使 applications/dem.py 可 import isce*
    py_cmd = (
        f"PYTHONPATH={safe_isce2}:${{PYTHONPATH:-}} python {dem_py} " + " ".join(py_args)
    )
    return f"cd {safe_raw} && {py_cmd}"


def _dtype_bytes(dtype: str) -> Optional[int]:
    d = (dtype or "").strip().upper().replace(" ", "")
    mapping = {
        "BYTE": 1,
        "UINT8": 1,
        "SHORT": 2,
        "SHORT_REAL": 2,
        "INT16": 2,
        "USHORT": 2,
        "UINT16": 2,
        "INT": 4,
        "INT32": 4,
        "FLOAT": 4,
        "FLOAT32": 4,
        "REAL*4": 4,
        "DOUBLE": 8,
        "FLOAT64": 8,
        "REAL*8": 8,
        "CFLOAT": 8,
        "CDOUBLE": 16,
    }
    return mapping.get(d)


def _xml_property_value(root, names: Tuple[str, ...]) -> Optional[str]:
    want = {n.lower() for n in names}
    for prop in root.iter():
        tag = (prop.tag or "").lower()
        if tag.endswith("property") or tag == "property":
            name = (prop.get("name") or "").strip().lower()
            if name not in want:
                continue
            for child in list(prop):
                if (child.tag or "").lower().endswith("value") and child.text:
                    return child.text.strip()
            if prop.text and prop.text.strip():
                return prop.text.strip()
        # 兼容 <WIDTH>3601</WIDTH> 一类扁平标签
        local = tag.split("}")[-1]
        if local.lower() in want and prop.text and prop.text.strip():
            return prop.text.strip()
    return None


def parse_isce_dem_xml(xml_path: str) -> dict:
    """从 ISCE DEM .xml 解析 width/length/data_type。"""
    import xml.etree.ElementTree as ET

    tree = ET.parse(xml_path)
    root = tree.getroot()
    width_s = _xml_property_value(root, ("width", "WIDTH", "file_length_x"))
    length_s = _xml_property_value(root, ("length", "LENGTH", "file_length", "FILE_LENGTH"))
    dtype_s = _xml_property_value(root, ("data_type", "DATA_TYPE", "datatype", "type"))
    width = int(float(width_s)) if width_s else None
    length = int(float(length_s)) if length_s else None
    return {
        "width": width,
        "length": length,
        "data_type": dtype_s,
        "bytes_per_sample": _dtype_bytes(dtype_s or ""),
    }


def resolve_vrt_source_filename(vrt_path: str) -> Optional[str]:
    """解析 VRT 中 SourceFilename，返回绝对路径（若可解析）。"""
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(vrt_path)
    except Exception:
        return None
    root = tree.getroot()
    src_el = None
    for el in root.iter():
        if (el.tag or "").split("}")[-1] == "SourceFilename":
            src_el = el
            break
    if src_el is None or not (src_el.text or "").strip():
        return None
    name = src_el.text.strip()
    relative = (src_el.get("relativeToVRT") or "0").strip() in ("1", "true", "True")
    if os.path.isabs(name):
        return name
    base = os.path.dirname(os.path.abspath(vrt_path))
    if relative or not os.path.isabs(name):
        return os.path.normpath(os.path.join(base, name))
    return name


def rewrite_vrt_source_to_basename(vrt_path: str, data_basename: str) -> None:
    """将 VRT SourceFilename 改写为相对 basename，避免指向旧目录或缺失文件。"""
    import xml.etree.ElementTree as ET

    tree = ET.parse(vrt_path)
    root = tree.getroot()
    for el in root.iter():
        if (el.tag or "").split("}")[-1] == "SourceFilename":
            el.text = data_basename
            el.set("relativeToVRT", "1")
            break
    tree.write(vrt_path, encoding="utf-8", xml_declaration=True)


def product_sidecar_paths(data_path: str) -> Tuple[str, str]:
    """返回 (xml_path, vrt_path)。"""
    return data_path + ".xml", data_path + ".vrt"


def validate_dem_raster_product(data_path: str) -> Tuple[bool, str]:
    """
    校验 DEM 栅格产品完整性：实体文件、XML、VRT、尺寸、VRT SourceFilename。
    不依赖 GDAL/rasterio。
    """
    if not data_path:
        return False, "产品路径为空"
    if not os.path.isfile(data_path):
        return False, f"实体文件不存在: {data_path}"
    size = os.path.getsize(data_path)
    if size <= 0:
        return False, f"实体文件大小为 0: {data_path}"
    xml_path, vrt_path = product_sidecar_paths(data_path)
    if not os.path.isfile(xml_path):
        return False, f"缺少 XML: {xml_path}"
    if not os.path.isfile(vrt_path):
        return False, f"缺少 VRT: {vrt_path}"
    try:
        meta = parse_isce_dem_xml(xml_path)
    except Exception as e:
        return False, f"解析 XML 失败: {e}"
    width, length, bps = meta.get("width"), meta.get("length"), meta.get("bytes_per_sample")
    if not width or not length or not bps:
        return False, (
            f"XML 缺少 width/length/data_type（width={width}, length={length}, "
            f"data_type={meta.get('data_type')!r}）: {xml_path}"
        )
    expected = int(width) * int(length) * int(bps)
    if size != expected:
        return False, (
            f"实体大小与 XML 不一致: file={size} bytes, "
            f"expected={expected} (= {width}×{length}×{bps}): {data_path}"
        )
    resolved = resolve_vrt_source_filename(vrt_path)
    if not resolved:
        return False, f"VRT 无法解析 SourceFilename: {vrt_path}"
    if not os.path.isfile(resolved):
        return False, f"VRT SourceFilename 指向不存在的文件: {resolved}"
    if os.path.abspath(os.path.normpath(resolved)) != os.path.abspath(os.path.normpath(data_path)):
        # 允许同目录同 inode / 相同文件名
        if os.path.basename(resolved) != os.path.basename(data_path) or not os.path.isfile(resolved):
            return False, (
                f"VRT SourceFilename 与实体不一致: vrt->{resolved}, data={data_path}"
            )
        if os.path.getsize(resolved) != size:
            return False, f"VRT 指向文件大小与实体不一致: {resolved}"
    return True, "完整性校验通过"


def select_primary_dem_product(
    raw_dir: str,
    output_name: Optional[str],
    correct_egm96: bool,
    *,
    mtime_after: Optional[float] = None,
) -> Optional[str]:
    """
    在 dem_raw_dir 中定位主产品路径。
    correct_egm96=True 仅接受 *.dem.wgs84 / {name}.dem.wgs84；
    False 仅接受 *.dem（排除 .dem.wgs84）。
    """
    raw_dir = os.path.abspath(raw_dir)
    candidates: List[str] = []

    def _ok_mtime(path: str) -> bool:
        if mtime_after is None:
            return True
        try:
            return os.path.getmtime(path) >= mtime_after
        except OSError:
            return False

    if output_name:
        base = output_name.strip()
        # dem.py -o NAME → NAME.dem；-c → NAME.dem.wgs84
        if correct_egm96:
            for cand in (
                os.path.join(raw_dir, base + ".dem.wgs84"),
                os.path.join(raw_dir, base + ".wgs84"),
            ):
                if os.path.isfile(cand) and _ok_mtime(cand):
                    return cand
            return None
        dem_path = os.path.join(raw_dir, base + ".dem")
        if os.path.isfile(dem_path) and _ok_mtime(dem_path):
            return dem_path
        return None

    try:
        names = os.listdir(raw_dir)
    except OSError:
        return None
    for name in names:
        path = os.path.join(raw_dir, name)
        if not os.path.isfile(path) or not _ok_mtime(path):
            continue
        lower = name.lower()
        if correct_egm96:
            if lower.endswith(".dem.wgs84") or (
                lower.endswith(".wgs84") and not lower.endswith(".wgs84.xml") and not lower.endswith(".wgs84.vrt")
            ):
                if lower.endswith(".xml") or lower.endswith(".vrt"):
                    continue
                candidates.append(path)
        else:
            if lower.endswith(".dem") and not lower.endswith(".dem.wgs84"):
                candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def copy_dem_product_group(src_data: str, output_dir: str) -> str:
    """
    复制实体 + .xml + .vrt 到 output_dir，并重写 VRT SourceFilename 为相对 basename。
    返回目标实体路径。
    """
    os.makedirs(output_dir, exist_ok=True)
    src_data = os.path.abspath(src_data)
    dst_data = os.path.join(output_dir, os.path.basename(src_data))
    src_xml, src_vrt = product_sidecar_paths(src_data)
    dst_xml, dst_vrt = product_sidecar_paths(dst_data)

    def _copy(src: str, dst: str) -> None:
        if os.path.abspath(src) == os.path.abspath(dst):
            return
        shutil.copy2(src, dst)

    _copy(src_data, dst_data)
    if os.path.isfile(src_xml):
        _copy(src_xml, dst_xml)
    if os.path.isfile(src_vrt):
        _copy(src_vrt, dst_vrt)
        rewrite_vrt_source_to_basename(dst_vrt, os.path.basename(dst_data))
    return dst_data


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
    2) 在 WSL 内于 dem_raw_dir 工作目录执行 dem.py（-c 时写出 .dem.wgs84 到该目录）；
    3) 完整性校验后复制产品组到 output_dir，返回主产品路径与垂直基准元数据。
    """
    def _fail(msg: str, **extra) -> dict:
        out = {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": msg,
            "output_path": None,
            "conversion_applied": bool(correct_egm96),
        }
        out.update(extra)
        if stream_callback:
            stream_callback(f"[失败] {msg}\n")
        return out

    if stream_callback:
        stream_callback("检查并补充 SRTM 瓦片…\n")
        stream_callback(
            f"EGM96→WGS84 椭球高转换: {'启用 (-c)' if correct_egm96 else '关闭'}\n"
        )
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
        return _fail(f"补充 SRTM 瓦片失败: {e}")

    if stream_callback:
        stream_callback("瓦片就绪，在 WSL 内执行 dem.py 拼接…\n")
    if not wsl_runner.use_wsl():
        return _fail(
            "DEM 制作需在 WSL 模式下运行（INSAR_USE_WSL=1）。请使用 scripts/start_desktop_wsl.bat 启动。"
        )
    isce_env, isce_env_err = wsl_runner.build_wsl_isce2_extra_env()
    if isce_env_err or not isce_env:
        return _fail(isce_env_err or "无法定位 WSL conda ISCE2 环境。")
    isce2_main = isce_env.get("INSAR_WSL_ISCE2_MAIN") or ""
    if not isce2_main:
        return _fail("未找到 WSL ISCE2 包路径（INSAR_WSL_ISCE2_MAIN）。")

    dem_raw_dir_clean = dem_raw_dir.replace("\x00", "").strip()
    output_dir_clean = output_dir.replace("\x00", "").strip()
    env_script = wsl_runner.get_wsl_env_script()
    out_dir_wsl, path_err = wsl_runner.resolve_windows_path_to_wsl(dem_raw_dir_clean)
    if path_err or not out_dir_wsl:
        return _fail(path_err or "DEM 原始数据目录在 WSL 中不可访问。")

    if stream_callback:
        stream_callback(f"WSL 数据目录（dem.py 工作目录）: {out_dir_wsl}\n")
    logger.info(
        "DEM stitch: bbox=(%s,%s,%s,%s), raw_dir=%s, output_dir=%s, wsl_cwd=%s, correct_egm96=%s",
        bbox_south, bbox_north, bbox_west, bbox_east,
        dem_raw_dir_clean, output_dir_clean, out_dir_wsl, correct_egm96,
    )

    cmd = build_dem_stitch_command(
        isce2_main_wsl=isce2_main,
        dem_raw_dir_wsl=out_dir_wsl,
        bbox_south=bbox_south,
        bbox_north=bbox_north,
        bbox_west=bbox_west,
        bbox_east=bbox_east,
        output_name=output_name,
        correct_egm96=correct_egm96,
    )
    # 日志中不打印敏感环境变量
    cmd_for_log = cmd
    if stream_callback:
        stream_callback(f"dem.py 命令: {cmd_for_log}\n")
    logger.info("DEM stitch 命令: %s", cmd_for_log)

    extra_env: dict[str, str] = dict(isce_env)
    distro = wsl_runner.get_wsl_distro() or "Ubuntu"
    if stream_callback:
        stream_callback(f"WSL 发行版: {distro}\n")

    started = time.time()
    result = wsl_runner.run_wsl(
        cmd,
        env_script=env_script,
        extra_env=extra_env or None,
        timeout=timeout,
        stream_callback=stream_callback,
    )
    if not result.get("success"):
        result["output_path"] = None
        result["conversion_applied"] = bool(correct_egm96)
        logger.error("DEM stitch WSL 命令失败: %s", result.get("error_message"))
        return result

    mtime_after = started - 5.0
    primary = select_primary_dem_product(
        dem_raw_dir_clean,
        output_name,
        correct_egm96,
        mtime_after=mtime_after,
    )
    if primary is None:
        # 再试一次不限 mtime（用户可能时钟偏差），但仍按类型严格筛选
        primary = select_primary_dem_product(
            dem_raw_dir_clean, output_name, correct_egm96, mtime_after=None
        )
    if primary is None:
        expect = ".dem.wgs84" if correct_egm96 else ".dem"
        # 若开启校正但只看到 .dem，明确禁止回退
        dem_only = select_primary_dem_product(
            dem_raw_dir_clean, output_name, False, mtime_after=None
        )
        if correct_egm96 and dem_only:
            return _fail(
                f"已请求 EGM96→WGS84（-c），但未找到实体 {expect}；"
                f"仅发现 EGM96 产品 {dem_only}。禁止回退到 .dem。"
                " 请确认 dem.py 工作目录为数据目录且 geoid 改正成功。",
                source_dem=dem_only,
            )
        return _fail(f"未在 {dem_raw_dir_clean} 找到期望主产品（*{expect}）。")

    ok, check_msg = validate_dem_raster_product(primary)
    if stream_callback:
        stream_callback(f"完整性校验: {check_msg}\n")
    if not ok:
        if correct_egm96:
            return _fail(
                f"WGS84 椭球高产品校验失败: {check_msg}。禁止回退到原始 .dem。",
                source_dem=primary if primary.lower().endswith(".dem") else None,
            )
        return _fail(f"EGM96 DEM 产品校验失败: {check_msg}")

    source_dem = primary
    # 若校正后仍保留 .dem，记录为 source
    if correct_egm96 and primary.lower().endswith(".wgs84"):
        maybe_src = primary[: -len(".wgs84")] if primary.lower().endswith(".dem.wgs84") else None
        if maybe_src and maybe_src.lower().endswith(".dem") and os.path.isfile(maybe_src):
            source_dem = maybe_src
        else:
            alt = select_primary_dem_product(
                dem_raw_dir_clean, output_name, False, mtime_after=None
            )
            if alt:
                source_dem = alt

    os.makedirs(output_dir_clean, exist_ok=True)
    raw_abs = os.path.abspath(os.path.normpath(dem_raw_dir_clean))
    out_abs = os.path.abspath(os.path.normpath(output_dir_clean))
    if raw_abs == out_abs:
        final_path = primary
        # 同目录也规范化 VRT 相对路径
        _xml, vrt_p = product_sidecar_paths(final_path)
        if os.path.isfile(vrt_p):
            rewrite_vrt_source_to_basename(vrt_p, os.path.basename(final_path))
    else:
        final_path = copy_dem_product_group(primary, output_dir_clean)
        ok2, check2 = validate_dem_raster_product(final_path)
        if stream_callback:
            stream_callback(f"复制后完整性校验: {check2}\n")
        if not ok2:
            return _fail(f"复制到输出目录后校验失败: {check2}")

    vertical_datum = "wgs84_ellipsoid" if correct_egm96 else "egm96_orthometric"
    xml_path, vrt_path = product_sidecar_paths(final_path)
    if correct_egm96 and not final_path.lower().endswith(".wgs84"):
        return _fail(
            f"内部错误：correct_egm96=True 但 output_path 不是 .wgs84: {final_path}"
        )

    if stream_callback:
        stream_callback(f"实体输出路径: {final_path}\n")
        stream_callback(f"垂直基准: {vertical_datum}\n")
        stream_callback("完整性校验结果: 通过\n")

    logger.info(
        "DEM stitch 完成: output_path=%s vertical_datum=%s",
        final_path,
        vertical_datum,
    )
    result["success"] = True
    result["output_path"] = final_path
    result["xml_path"] = xml_path if os.path.isfile(xml_path) else None
    result["vrt_path"] = vrt_path if os.path.isfile(vrt_path) else None
    result["source_dem"] = source_dem
    result["vertical_datum"] = vertical_datum
    result["conversion_applied"] = bool(correct_egm96)
    result["validation_message"] = check_msg
    return result
