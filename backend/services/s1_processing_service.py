"""
Sentinel-1 TOPS processing service: runs in WSL only (Python-driven ISCE2 via run_s1_extract_wsl).
Uses isceobj.Sensor.TOPS.Sentinel1.Sentinel1 in WSL for parse() and extractImage().
Supports regionOfInterest via target.shp (bbox SNWE) or explicit bbox_snwe.
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Callable, List, Optional

# In Docker (insar-ubuntu20), ISCE2 is installed; for local dev, add lib path
_ISCE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "lib", "isce2-main")
)
# Phase 3: Windows local — prefer installed packages (minimal S1 build output)
_ISCE_INSTALL_PACKAGES = os.path.join(_ISCE_ROOT, "install", "packages")
if os.path.isdir(_ISCE_INSTALL_PACKAGES) and _ISCE_INSTALL_PACKAGES not in sys.path:
    sys.path.insert(0, _ISCE_INSTALL_PACKAGES)
elif os.path.isdir(_ISCE_ROOT) and _ISCE_ROOT not in sys.path:
    sys.path.insert(0, _ISCE_ROOT)

# Optional: add contrib/stack for sentinelSLC if needed later (orbit discovery etc.)
_TOPS_STACK = os.path.join(_ISCE_ROOT, "contrib", "stack", "topsStack")
if os.path.isdir(_TOPS_STACK) and _TOPS_STACK not in sys.path:
    sys.path.insert(0, os.path.join(_ISCE_ROOT, "contrib", "stack"))


def bbox_from_shapefile(shp_path: str) -> List[float]:
    """
    Read target.shp and return [South, North, West, East] in degrees (SNWE).
    Uses geopandas if available, else fiona.
    """
    shp_path = os.path.abspath(shp_path)
    if not os.path.isfile(shp_path):
        raise FileNotFoundError(f"Shapefile not found: {shp_path}")

    try:
        import geopandas as gpd

        gdf = gpd.read_file(shp_path)
        if gdf.crs and gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        bounds = gdf.total_bounds  # minx, miny, maxx, maxy (lon, lat, lon, lat)
        south, north = float(bounds[1]), float(bounds[3])
        west, east = float(bounds[0]), float(bounds[2])
        return [south, north, west, east]
    except ImportError:
        try:
            import fiona
            from shapely.geometry import shape

            with fiona.open(shp_path) as src:
                minx, miny, maxx, maxy = 1e10, 1e10, -1e10, -1e10
                for feat in src:
                    geom = shape(feat["geometry"])
                    b = geom.bounds
                    minx, miny = min(minx, b[0]), min(miny, b[1])
                    maxx, maxy = max(maxx, b[2]), max(maxy, b[3])
            return [miny, maxy, minx, maxx]  # SNWE
        except ImportError as e:
            raise RuntimeError(
                "Need geopandas or fiona+shapely to read target.shp. Install e.g. geopandas."
            ) from e


def resolve_safe_paths(path: str) -> List[str]:
    """
    将用户选择的路径解析为 SAFE 列表，供 ISCE2 使用。
    - 若为文件：返回 [path]（单个 .zip 或单一路径）。
    - 若为目录：返回该目录下所有 .zip 与所有 *.SAFE 子目录的绝对路径列表（排序）。
    这样前端选择“雷达数据目录”（内含多个日期的 .zip）时，会逐个导入。
    """
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        return []
    items: List[str] = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if name.lower().endswith(".zip") and os.path.isfile(full):
            items.append(full)
        elif name.upper().endswith(".SAFE") and os.path.isdir(full):
            items.append(full)
    return items


def resolve_region_of_interest(
    target_shp_path: Optional[str],
    bbox_snwe: Optional[List[float]],
) -> List[float]:
    """
    Resolve ROI as [South, North, West, East]. target_shp overrides bbox_snwe if both set.
    """
    if target_shp_path:
        return bbox_from_shapefile(target_shp_path)
    if bbox_snwe and len(bbox_snwe) == 4:
        return list(bbox_snwe)
    return []


def fix_vrt_relative_path(vrt_path: str, zip_path: str) -> None:
    """
    修复 VRT 文件中的相对路径，确保 relativeToVRT="1" 的路径能够正确指向 ZIP 文件。
    
    ISCE2 生成的 VRT 文件中，对于 /vsizip 路径，可能使用绝对路径。
    我们需要将其转换为相对于 VRT 文件位置的相对路径，以便后续处理能够正确访问。
    
    Args:
        vrt_path: VRT 文件路径
        zip_path: ZIP 文件路径（容器内路径，例如 /app/data/radar/xxx.zip）
    """
    if not os.path.exists(vrt_path):
        return
    
    try:
        tree = ET.parse(vrt_path)
        root = tree.getroot()
        
        # 计算从 VRT 文件到 ZIP 文件的相对路径
        vrt_dir = os.path.dirname(vrt_path)
        zip_abs_path = os.path.abspath(zip_path)
        
        try:
            rel_path_to_zip = os.path.relpath(zip_abs_path, vrt_dir)
            # 转换为 POSIX 路径（使用 /）
            rel_path_to_zip = rel_path_to_zip.replace("\\", "/")
        except ValueError:
            # 如果无法计算相对路径（例如跨驱动器），保持原路径不变
            return
        
        # 查找所有 SourceFilename 元素
        modified = False
        for source_filename in root.findall(".//SourceFilename"):
            if source_filename.get("relativeToVRT") == "1":
                current_path = source_filename.text
                if current_path and current_path.startswith("/vsizip/"):
                    # 提取 ZIP 文件内的路径部分
                    # 格式: /vsizip//app/data/radar/xxx.zip/SAFE/measurement/xxx.tiff
                    # 需要提取: /SAFE/measurement/xxx.tiff
                    parts = current_path.split("/")
                    vsizip_idx = parts.index("vsizip")
                    if vsizip_idx + 1 < len(parts):
                        # 找到 ZIP 文件名（包含 .zip）
                        zip_internal_start_idx = None
                        for i in range(vsizip_idx + 1, len(parts)):
                            if parts[i].endswith(".zip"):
                                zip_internal_start_idx = i + 1
                                break
                        
                        if zip_internal_start_idx is not None:
                            # ZIP 文件内的路径
                            zip_internal_path = "/" + "/".join(parts[zip_internal_start_idx:])
                            
                            # 构建新的相对路径：/vsizip/ + 相对路径 + ZIP 内的路径
                            new_path = f"/vsizip/{rel_path_to_zip}{zip_internal_path}"
                            source_filename.text = new_path
                            modified = True
        
        # 如果修改了路径，保存 VRT 文件
        if modified:
            tree.write(vrt_path, encoding="utf-8", xml_declaration=False)
    except Exception as e:
        # 如果修复失败，记录错误但不中断处理
        import logging
        logging.warning(f"Failed to fix VRT relative path in {vrt_path}: {e}")


def run_sentinel1_extract(
    zip_path: str,
    orbit_dir: str,
    dem_path: str,
    aux_dir: str,
    out_dir: str,
    swaths: List[int],
    polarization: str = "vv",
    region_of_interest: Optional[List[float]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    virtual_slc: bool = True,
) -> dict:
    """
    Run ISCE2 Sentinel1 TOPS extract in-process: parse() + extractImage() per swath.
    No XML config files, no subprocess calls.

    Args:
        zip_path: Path to S1 SAFE zip (or directory).
        orbit_dir: Directory containing orbit EOF files.
        dem_path: Path to DEM (used by stack later; not by extractImage).
        aux_dir: Aux directory for antenna/cal.
        out_dir: Output directory for SLC/VRT (e.g. .../reference or .../slc/YYYYMMDD).
        swaths: List of swath numbers, e.g. [1, 2, 3].
        polarization: e.g. 'vv'.
        region_of_interest: Optional [South, North, West, East] for crop.
        progress_callback: Optional callback(progress_pct, step_description).
        virtual_slc: If True, extractImage(virtual=True) to produce VRT.

    Returns:
        dict with keys: slc_vrt_paths (list), metadata (dict), success (bool), error_message (optional).
    """
    try:
        # 尝试标准导入路径（Docker / 部分环境）
        from isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
    except ImportError:
        try:
            # 容器内 conda 环境的导入路径
            from isce.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
        except ImportError:
            try:
                # Phase 3: Windows 本机 install/packages（isce2 布局）
                from isce2.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
            except ImportError as e:
                return {
                    "success": False,
                    "slc_vrt_paths": [],
                    "metadata": {},
                    "error_message": f"ISCE2 not available: {e}. Run inside insar-ubuntu20 container or set PYTHONPATH to ISCE2 install/packages (Windows).",
                }

    zip_path = os.path.abspath(zip_path)
    orbit_dir = os.path.abspath(orbit_dir)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    def report(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    slc_vrt_paths: List[str] = []
    total_swaths = len(swaths)
    for i, swath_num in enumerate(swaths):
        step_pct = (100.0 * i) / total_swaths if total_swaths else 0.0
        report(step_pct, f"Processing swath {swath_num}...")

        obj = Sentinel1()
        obj.configure()
        obj.safe = [zip_path]
        obj.swathNumber = swath_num
        obj.output = os.path.join(out_dir, f"IW{swath_num}")
        obj.orbitDir = orbit_dir
        obj.orbitFile = None  # let reader find from orbitDir
        obj.auxDir = aux_dir
        obj.polarization = polarization
        if region_of_interest and len(region_of_interest) == 4:
            obj.regionOfInterest = region_of_interest

        obj.parse()
        report(step_pct + 10.0 / total_swaths, f"Extracting image swath {swath_num}...")
        obj.extractImage(virtual=virtual_slc)

        # Typical output: out_dir/IW1/ (with .vrt or .slc inside)
        swath_out = obj.output
        if os.path.isdir(swath_out):
            for name in os.listdir(swath_out):
                if name.endswith(".vrt") or name.endswith(".slc.vrt"):
                    vrt_path = os.path.join(swath_out, name)
                    # 修复 VRT 文件中的相对路径，确保指向 ZIP 文件的路径正确
                    fix_vrt_relative_path(vrt_path, zip_path)
                    slc_vrt_paths.append(vrt_path)
        # Some ISCE2 layouts write one VRT per swath directly under out_dir
        if not slc_vrt_paths and os.path.isdir(swath_out):
            slc_vrt_paths.append(swath_out)

    report(100.0, "S1 extract complete.")
    return {
        "success": True,
        "slc_vrt_paths": slc_vrt_paths,
        "metadata": {
            "zip_path": zip_path,
            "out_dir": out_dir,
            "swaths": swaths,
            "region_of_interest": region_of_interest,
        },
    }


def _use_wsl() -> bool:
    try:
        from backend.services import wsl_runner
        return wsl_runner.use_wsl()
    except Exception:
        return False


def run_s1_import_from_request(
    request: "InSARTaskRequest",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> dict:
    """
    Run S1 import/registration from shared_models.InSARTaskRequest.
    Resolves ROI from target_shp_path or bbox_snwe, then calls run_sentinel1_extract.
    When INSAR_USE_WSL=1: paths are converted to WSL and run_sentinel1_extract runs inside WSL.
    """
    from backend.services import wsl_runner

    roi = resolve_region_of_interest(
        getattr(request, "target_shp_path", None),
        getattr(request, "bbox_snwe", None),
    )

    # 支持“雷达数据目录”：目录内多个 .zip / .SAFE 会逐个导入
    safe_list = resolve_safe_paths(request.zip_path)
    if not safe_list:
        return {
            "success": False,
            "slc_vrt_paths": [],
            "metadata": {},
            "error_message": f"No SAFE data found in {request.zip_path!r} (expect .zip or *.SAFE).",
        }

    # 若选的是目录，radar_dir 即该目录；否则为 zip 所在目录
    radar_dir = (
        request.zip_path
        if os.path.isdir(os.path.abspath(request.zip_path))
        else os.path.dirname(os.path.abspath(request.zip_path))
    )

    # 根据处理范围（target.shp 或 bbox_snwe）自动检测需要处理的 subswath；roi 传入 ISCE 作为 -bbox 限制处理范围
    swath_list = [int(s) for s in request.swaths.split()]
    first_safe = safe_list[0]
    # 有 target.shp 或 bbox_snwe 时自动检测 subswath（用第一个 SAFE 做检测）
    if getattr(request, "target_shp_path", None) and os.path.exists(request.target_shp_path):
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from backend.scripts.subswath_detector import detect_subswaths

            if progress_callback:
                progress_callback(0.0, "检测需要处理的 subswath...")
            detected_swaths = detect_subswaths(first_safe, shapefile_path=request.target_shp_path)
            if detected_swaths:
                swath_list = detected_swaths
                if progress_callback:
                    progress_callback(5.0, f"检测到需要处理的 subswath: {swath_list}")
        except ImportError:
            pass
        except Exception as e:
            if progress_callback:
                progress_callback(0.0, f"Subswath 自动检测失败，使用指定 swaths: {e}")
    elif roi and len(roi) == 4:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from backend.scripts.subswath_detector import detect_subswaths

            if progress_callback:
                progress_callback(0.0, "根据处理范围检测需要处理的 subswath...")
            detected_swaths = detect_subswaths(first_safe, bbox_snwe=roi)
            if detected_swaths:
                swath_list = detected_swaths
                if progress_callback:
                    progress_callback(5.0, f"检测到需要处理的 subswath: {swath_list}")
        except ImportError:
            pass
        except Exception as e:
            if progress_callback:
                progress_callback(0.0, f"Subswath 自动检测失败，使用指定 swaths: {e}")

    all_slc_vrt_paths: List[str] = []
    last_metadata: dict = {}
    total = len(safe_list)
    if not _use_wsl():
        return {
            "success": False,
            "slc_vrt_paths": [],
            "metadata": {},
            "error_message": "仅支持 WSL 模式。请设置 INSAR_USE_WSL=1 并用 scripts/start_desktop_wsl.bat 启动。",
        }

    step_base = (request.output_dir or "").strip()
    if step_base:
        step_base = wsl_runner.windows_path_to_wsl(step_base)
    if not step_base:
        step_base = wsl_runner.get_wsl_workspace_root() + "/s1_import"
    radar_dir_wsl = wsl_runner.windows_path_to_wsl(radar_dir)

    project_root = wsl_runner.get_wsl_project_root()
    if not project_root:
        return {"success": False, "slc_vrt_paths": [], "metadata": {}, "error_message": "WSL 模式下请设置 INSAR_WSL_PROJECT_ROOT"}
    env_script = wsl_runner.get_wsl_env_script()
    for idx, one_safe_path in enumerate(safe_list):
        if progress_callback and total > 1:
            progress_callback(100.0 * idx / total, f"导入第 {idx + 1}/{total} 景…")
        base = (
            os.path.splitext(os.path.basename(one_safe_path))[0]
            if os.path.isfile(one_safe_path)
            else os.path.basename(one_safe_path)
        )
        out_dir = (step_base.rstrip("/") + "/" + base) if step_base else (radar_dir_wsl.rstrip("/") + "/processing/s1_import/" + base)
        extract_json = json.dumps({
            "zip_path": wsl_runner.windows_path_to_wsl(one_safe_path),
            "orbit_dir": wsl_runner.windows_path_to_wsl(request.orbit_dir),
            "dem_path": wsl_runner.windows_path_to_wsl(request.dem_path),
            "aux_dir": wsl_runner.windows_path_to_wsl(request.aux_dir),
            "out_dir": out_dir,
            "swaths": swath_list,
            "polarization": request.polarization,
            "region_of_interest": roi,
        })
        cmd = f"cd '{project_root}' && PYTHONPATH='.' INSAR_PROJECT_ROOT='{project_root}' python3 -m backend.scripts.run_s1_extract_wsl"
        result = wsl_runner.run_wsl(cmd, env_script=env_script, extra_env={"INSAR_S1_EXTRACT_JSON": extract_json}, timeout=7200)
        if not result.get("success"):
            out = (result.get("stdout") or "").strip()
            for line in reversed(out.splitlines()):
                if line.strip().startswith("{"):
                    try:
                        data = json.loads(line)
                        return {**data, "slc_vrt_paths": all_slc_vrt_paths + data.get("slc_vrt_paths", [])}
                    except json.JSONDecodeError:
                        pass
            return {"success": False, "slc_vrt_paths": all_slc_vrt_paths, "metadata": {}, "error_message": result.get("error_message", "WSL S1 导入失败")}
        stdout = (result.get("stdout") or "").strip()
        for line in reversed(stdout.splitlines()):
            if line.strip().startswith("{"):
                try:
                    data = json.loads(line)
                    all_slc_vrt_paths.extend(data.get("slc_vrt_paths", []))
                    last_metadata = data.get("metadata", {})
                    break
                except json.JSONDecodeError:
                    continue
    last_metadata["zip_paths"] = safe_list
    return {"success": True, "slc_vrt_paths": all_slc_vrt_paths, "metadata": last_metadata}


# Allow running as a one-off test (e.g. in container)
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="SAFE zip path")
    ap.add_argument("--orbit-dir", required=True)
    ap.add_argument("--dem", required=True)
    ap.add_argument("--aux-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--swaths", default="1 2 3")
    ap.add_argument("--target-shp", default=None)
    ap.add_argument("--bbox", default=None, help="SNWE space-separated")
    args = ap.parse_args()
    roi = []
    if args.target_shp:
        roi = bbox_from_shapefile(args.target_shp)
    elif args.bbox:
        roi = [float(x) for x in args.bbox.split()]
    swaths = [int(s) for s in args.swaths.split()]
    result = run_sentinel1_extract(
        zip_path=args.zip,
        orbit_dir=args.orbit_dir,
        dem_path=args.dem,
        aux_dir=args.aux_dir,
        out_dir=args.out_dir,
        swaths=swaths,
        region_of_interest=roi if roi else None,
        progress_callback=lambda p, m: print(f"[{p:.0f}%] {m}"),
    )
    print("Result:", result)
