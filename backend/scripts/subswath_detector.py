#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentinel-1 Subswath Detector

根据任务区范围（shapefile）判断Sentinel-1 IW模式数据需要处理哪些subswath。
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import logging


class _SafeDirArchive:
    """只读“归档”接口：对 .SAFE 目录提供与 ZipFile 兼容的 namelist()/read()，便于与 zip 共用一套解析逻辑。"""
    def __init__(self, safe_dir: Path):
        self._root = Path(safe_dir)
        self._namelist: Optional[List[str]] = None

    def namelist(self) -> List[str]:
        if self._namelist is not None:
            return self._namelist
        out: List[str] = []
        for root, _dirs, files in os.walk(self._root):
            for f in files:
                full = Path(root) / f
                rel = full.relative_to(self._root)
                out.append(rel.as_posix())
        self._namelist = out
        return out

    def read(self, name: str) -> bytes:
        p = self._root / name
        if not p.is_file():
            raise KeyError(name)
        return p.read_bytes()

    def __enter__(self) -> "_SafeDirArchive":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


_SLC_ANNOTATION_RE = re.compile(
    r"/s1[a-z]-iw[123]-slc-(?:vv|vh)-",
    re.IGNORECASE,
)


def _is_slc_annotation_path(path: str) -> bool:
    """仅匹配 IW SLC 产品 annotation（排除 calibration/noise/rfi 子目录）。"""
    p = path.replace("\\", "/").lower()
    if not p.endswith(".xml") or "/annotation/" not in p:
        return False
    if any(x in p for x in ("/calibration/", "/noise/", "/rfi/")):
        return False
    return bool(_SLC_ANNOTATION_RE.search(p))


def _parse_gml_coordinates_bbox(coords_str: str) -> Optional[Tuple[float, float, float, float]]:
    """解析 manifest gml:coordinates（lat,lon 对）为 (min_lon, min_lat, max_lon, max_lat)。"""
    coords = []
    for pair in coords_str.strip().split():
        parts = pair.split(",")
        if len(parts) != 2:
            continue
        try:
            lat, lon = float(parts[0]), float(parts[1])
            coords.append((lon, lat))
        except ValueError:
            continue
    if not coords:
        return None
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def extract_product_footprint(sentinel1_path: str) -> Tuple[float, float, float, float]:
    """
    产品级覆盖范围 (min_lon, min_lat, max_lon, max_lat)。
    优先 manifest.safe；失败则用各 subswath footprint 并集。
    """
    path = Path(sentinel1_path)
    with _open_safe_archive(path) as z:
        manifest_files = [f for f in z.namelist() if "manifest.safe" in f.lower()]
        if manifest_files:
            root = ET.fromstring(z.read(manifest_files[0]))
            for elem in root.iter():
                if elem.tag.endswith("coordinates") and elem.text and len(elem.text) > 20:
                    bbox = _parse_gml_coordinates_bbox(elem.text)
                    if bbox:
                        return bbox
    detector = SubswathDetector(str(path), bbox_snwe=(0.0, 1.0, 0.0, 1.0))
    footprints = detector.extract_subswath_footprints()
    if not footprints:
        raise ValueError(f"无法解析产品覆盖范围: {sentinel1_path}")
    min_lon = min(fp[0] for fp in footprints.values())
    min_lat = min(fp[1] for fp in footprints.values())
    max_lon = max(fp[2] for fp in footprints.values())
    max_lat = max(fp[3] for fp in footprints.values())
    return (min_lon, min_lat, max_lon, max_lat)


def extract_relative_orbit_number(sentinel1_path: str) -> Optional[int]:
    """从 manifest.safe 读取 relativeOrbitNumber（同 Path 校验用）。"""
    path = Path(sentinel1_path)
    try:
        with _open_safe_archive(path) as z:
            manifest_files = [f for f in z.namelist() if "manifest.safe" in f.lower()]
            if not manifest_files:
                return None
            root = ET.fromstring(z.read(manifest_files[0]))
            values: List[int] = []
            for elem in root.iter():
                if elem.tag.endswith("relativeOrbitNumber") and elem.text:
                    try:
                        values.append(int(elem.text.strip()))
                    except ValueError:
                        continue
            if values:
                return values[0]
    except Exception:
        return None
    return None


def _open_safe_archive(path: Path):
    """打开 .zip 或 .SAFE 目录，返回提供 namelist()/read() 的上下文管理器。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"路径不存在: {path}")
    if path.is_file() and path.suffix.lower() == ".zip":
        return zipfile.ZipFile(path, "r")
    if path.is_dir() and str(path).upper().endswith(".SAFE"):
        return _SafeDirArchive(path)
    raise ValueError(
        f"Sentinel-1 路径须为 .zip 或 .SAFE 目录: {path}"
    )


# geopandas/shapely 仅在通过 shapefile 指定任务区时需要，使用 bbox_snwe 时不必安装
_GPD = None
_UNARY_UNION = None

def _ensure_geopandas():
    """仅在需要读取 shapefile 时导入 geopandas/shapely。"""
    global _GPD, _UNARY_UNION
    if _GPD is not None:
        return
    try:
        import geopandas as gpd
        from shapely.ops import unary_union
        _GPD = gpd
        _UNARY_UNION = unary_union
    except ImportError as e:
        raise ImportError(
            f"使用 shapefile 指定任务区需要安装: pip install geopandas shapely. {e}"
        )

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SubswathDetector:
    """Sentinel-1 Subswath检测器。任务区可由 shapefile 或 bbox_snwe（处理范围四坐标）指定。"""

    def __init__(
        self,
        sentinel1_zip_path: str,
        shapefile_path: Optional[str] = None,
        bbox_snwe: Optional[Tuple[float, float, float, float]] = None,
    ):
        """
        初始化检测器。任务区二选一：shapefile_path 或 bbox_snwe。

        Args:
            sentinel1_zip_path: Sentinel-1 数据 zip 或 .SAFE 目录路径
            shapefile_path: 任务区 shapefile 文件路径（与 bbox_snwe 二选一）
            bbox_snwe: 处理范围 [South, North, West, East] 单位度（与 shapefile_path 二选一）
        """
        self.sentinel1_zip_path = Path(sentinel1_zip_path)
        self.shapefile_path = Path(shapefile_path) if shapefile_path else None
        self.bbox_snwe = bbox_snwe

        if not self.sentinel1_zip_path.exists():
            raise FileNotFoundError(
                f"Sentinel-1数据文件不存在: {self.sentinel1_zip_path}"
            )
        if self.shapefile_path and not self.shapefile_path.exists():
            raise FileNotFoundError(
                f"Shapefile文件不存在: {self.shapefile_path}"
            )
        if not self.shapefile_path and not (self.bbox_snwe and len(self.bbox_snwe) == 4):
            raise ValueError("必须提供 shapefile_path 或 bbox_snwe（4 个浮点数 [S,N,W,E]）")

        logger.info("初始化Subswath检测器")
        logger.info("  Sentinel-1数据: %s", self.sentinel1_zip_path)
        if self.shapefile_path:
            logger.info("  任务区shapefile: %s", self.shapefile_path)
        else:
            logger.info("  任务区bbox_snwe: %s", self.bbox_snwe)
    
    def extract_task_area_bbox(self) -> Tuple[float, float, float, float]:
        """
        提取任务区的边界框（bounding box）。
        若构造时提供了 bbox_snwe，则直接转换为 (min_lon, min_lat, max_lon, max_lat)；
        否则从 shapefile 读取。
        
        Returns:
            (min_lon, min_lat, max_lon, max_lat) 边界框坐标
            
        Raises:
            ValueError: 如果 shapefile 为空或无法读取
        """
        if self.bbox_snwe is not None and len(self.bbox_snwe) == 4:
            south, north, west, east = self.bbox_snwe
            min_lon, min_lat, max_lon, max_lat = west, south, east, north
            logger.info(
                "任务区边界框(由bbox_snwe): "
                "(%.6f, %.6f) - (%.6f, %.6f)",
                min_lon, min_lat, max_lon, max_lat,
            )
            return (min_lon, min_lat, max_lon, max_lat)

        try:
            _ensure_geopandas()
            logger.info("读取任务区shapefile...")
            gdf = _GPD.read_file(self.shapefile_path)
            
            if gdf.empty:
                raise ValueError(
                    f"Shapefile为空，无法提取任务区范围: {self.shapefile_path}"
                )
            
            union_geom = _UNARY_UNION(gdf.geometry)
            bbox = union_geom.bounds  # (minx, miny, maxx, maxy)
            min_lon, min_lat, max_lon, max_lat = bbox
            
            logger.info(
                "任务区边界框: (%.6f, %.6f) - (%.6f, %.6f)",
                min_lon, min_lat, max_lon, max_lat,
            )
            return (min_lon, min_lat, max_lon, max_lat)
            
        except Exception as e:
            raise ValueError(
                f"读取shapefile失败: {self.shapefile_path}. "
                f"错误信息: {str(e)}"
            )
    
    def extract_subswath_footprints(self) -> dict:
        """
        从Sentinel-1 SAFE数据中提取每个subswath的覆盖范围
        
        Returns:
            dict: {subswath_number: (min_lon, min_lat, max_lon, max_lat), ...}
            
        Raises:
            ValueError: 如果无法解析Sentinel-1数据
        """
        try:
            logger.info("解析Sentinel-1 SAFE数据...")
            
            footprints = {}
            
            with _open_safe_archive(self.sentinel1_zip_path) as z:
                # 获取所有annotation XML文件
                annotation_files = [
                    f for f in z.namelist()
                    if _is_slc_annotation_path(f)
                ]
                
                if not annotation_files:
                    raise ValueError(
                        f"在Sentinel-1数据中未找到annotation文件: "
                        f"{self.sentinel1_zip_path}"
                    )
                
                logger.info(f"找到 {len(annotation_files)} 个annotation文件")
                
                # 按subswath分组处理
                subswath_files = {}
                for ann_file in annotation_files:
                    # 提取subswath编号 (iw1, iw2, iw3)
                    if 'iw1' in ann_file.lower():
                        subswath_num = 1
                    elif 'iw2' in ann_file.lower():
                        subswath_num = 2
                    elif 'iw3' in ann_file.lower():
                        subswath_num = 3
                    else:
                        continue
                    
                    # 只处理一个极化（VV或VH），避免重复
                    if subswath_num not in subswath_files:
                        subswath_files[subswath_num] = ann_file
                
                # 解析每个subswath的覆盖范围
                for subswath_num, ann_file in subswath_files.items():
                    try:
                        logger.info(f"解析subswath {subswath_num}...")
                        xml_content = z.read(ann_file)
                        root = ET.fromstring(xml_content)
                        
                        # 方法1: 尝试从geolocationGrid提取坐标
                        bbox = self._extract_bbox_from_geolocation_grid(root)
                        
                        # 方法2: 如果方法1失败，尝试从manifest.safe提取
                        if bbox is None:
                            bbox = self._extract_bbox_from_manifest(z, subswath_num)
                        
                        if bbox:
                            footprints[subswath_num] = bbox
                            logger.info(
                                f"Subswath {subswath_num} 覆盖范围: "
                                f"({bbox[0]:.6f}, {bbox[1]:.6f}) - "
                                f"({bbox[2]:.6f}, {bbox[3]:.6f})"
                            )
                        else:
                            logger.warning(
                                f"无法提取subswath {subswath_num}的覆盖范围"
                            )
                            
                    except Exception as e:
                        logger.warning(
                            f"解析subswath {subswath_num}失败: {str(e)}"
                        )
                        continue
            
            if not footprints:
                raise ValueError(
                    f"无法从Sentinel-1数据中提取任何subswath的覆盖范围: "
                    f"{self.sentinel1_zip_path}"
                )
            
            return footprints
            
        except zipfile.BadZipFile:
            raise ValueError(
                f"无效的zip文件: {self.sentinel1_zip_path}"
            )
        except (ValueError, FileNotFoundError):
            raise
        except Exception as e:
            raise ValueError(
                f"解析Sentinel-1数据失败: {self.sentinel1_zip_path}. "
                f"错误信息: {str(e)}"
            )
    
    def _extract_bbox_from_geolocation_grid(
        self, root: ET.Element
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        从geolocationGrid中提取边界框
        
        Args:
            root: XML根元素
            
        Returns:
            (min_lon, min_lat, max_lon, max_lat) 或 None
        """
        try:
            lons = []
            lats = []
            for point in root.iter():
                if not point.tag.endswith("geolocationGridPoint"):
                    continue
                lon_elem = lat_elem = None
                for child in point:
                    if child.tag.endswith("longitude"):
                        lon_elem = child
                    elif child.tag.endswith("latitude"):
                        lat_elem = child
                if lon_elem is not None and lat_elem is not None:
                    try:
                        lon = float(lon_elem.text)
                        lat = float(lat_elem.text)
                        lons.append(lon)
                        lats.append(lat)
                    except (ValueError, AttributeError, TypeError):
                        continue
            
            if not lons or not lats:
                return None
            
            min_lon = min(lons)
            max_lon = max(lons)
            min_lat = min(lats)
            max_lat = max(lats)
            
            return (min_lon, min_lat, max_lon, max_lat)
            
        except Exception as e:
            logger.debug(f"从geolocationGrid提取边界框失败: {str(e)}")
            return None
    
    def _extract_bbox_from_manifest(
        self, zip_file: zipfile.ZipFile, subswath_num: int
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        从manifest.safe中提取subswath的边界框
        
        Args:
            zip_file: 打开的zip文件对象
            subswath_num: subswath编号
            
        Returns:
            (min_lon, min_lat, max_lon, max_lat) 或 None
        """
        try:
            # 查找manifest.safe文件
            manifest_files = [
                f for f in zip_file.namelist() 
                if 'manifest.safe' in f.lower()
            ]
            
            if not manifest_files:
                return None
            
            manifest_content = zip_file.read(manifest_files[0])
            root = ET.fromstring(manifest_content)
            
            # 查找包含subswath信息的metadata
            # Sentinel-1的manifest.safe中包含footprint信息
            # 这里简化处理，实际可能需要更复杂的解析
            
            # 尝试查找gml:coordinates或gml:posList
            namespaces = {
                'gml': 'http://www.opengis.net/gml',
                'safe': 'http://www.esa.int/safe/sentinel-1.0'
            }
            
            # 查找footprint
            footprint = root.find('.//gml:coordinates', namespaces)
            if footprint is not None:
                # 解析坐标字符串
                coords_str = footprint.text
                if coords_str:
                    bbox = _parse_gml_coordinates_bbox(coords_str)
                    if bbox:
                        return bbox
            
            return None
            
        except Exception as e:
            logger.debug(f"从manifest提取边界框失败: {str(e)}")
            return None
    
    def check_intersection(
        self, 
        bbox1: Tuple[float, float, float, float],
        bbox2: Tuple[float, float, float, float]
    ) -> bool:
        """
        检查两个边界框是否相交
        
        Args:
            bbox1: (min_lon, min_lat, max_lon, max_lat)
            bbox2: (min_lon, min_lat, max_lon, max_lat)
            
        Returns:
            bool: 是否相交
        """
        min_lon1, min_lat1, max_lon1, max_lat1 = bbox1
        min_lon2, min_lat2, max_lon2, max_lat2 = bbox2
        
        # 检查是否相交
        return not (
            max_lon1 < min_lon2 or 
            max_lon2 < min_lon1 or 
            max_lat1 < min_lat2 or 
            max_lat2 < min_lat1
        )
    
    def detect_subswaths(self) -> List[int]:
        """
        检测需要处理的subswath
        
        Returns:
            List[int]: 需要处理的subswath编号列表，如[1, 2]或[]
            
        Raises:
            ValueError: 如果处理过程中出现错误
        """
        try:
            # 1. 提取任务区边界框
            task_bbox = self.extract_task_area_bbox()
            
            # 2. 提取所有subswath的覆盖范围
            subswath_footprints = self.extract_subswath_footprints()
            
            # 3. 检查每个subswath是否与任务区相交
            required_subswaths = []
            
            for subswath_num in sorted(subswath_footprints.keys()):
                subswath_bbox = subswath_footprints[subswath_num]
                
                if self.check_intersection(task_bbox, subswath_bbox):
                    required_subswaths.append(subswath_num)
                    logger.info(
                        f"Subswath {subswath_num} 与任务区相交，需要处理"
                    )
                else:
                    logger.info(
                        f"Subswath {subswath_num} 与任务区不相交，跳过"
                    )
            
            logger.info(f"检测完成，需要处理的subswath: {required_subswaths}")
            
            return required_subswaths
            
        except Exception as e:
            logger.error(f"检测subswath失败: {str(e)}")
            raise


def _get_sensing_date_from_path(sentinel1_path: str) -> str:
    """
    从 SAFE 路径或文件名解析成像日期。如 S1A_IW_SLC__1SDV_20220101T123456 -> 2022-01-01。
    """
    path = Path(sentinel1_path)
    name = path.stem if path.suffix.lower() in (".zip",) else path.name
    # 常见模式: ..._20220101T... 或 20220101
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _bbox_to_nwse(bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) -> (N, W, S, E) 用于显示。"""
    min_lon, min_lat, max_lon, max_lat = bbox
    return (max_lat, min_lon, min_lat, max_lon)


def detect_subswaths(
    sentinel1_zip_path: str,
    shapefile_path: Optional[str] = None,
    bbox_snwe: Optional[List[float]] = None,
) -> List[int]:
    """
    根据任务区范围判断 Sentinel-1 数据需要处理哪些 subswath。
    任务区可由 shapefile 或 bbox_snwe（处理范围四坐标）指定，二选一。

    Args:
        sentinel1_zip_path: Sentinel-1 数据 zip 或 .SAFE 目录路径
        shapefile_path: 任务区 shapefile 文件路径（与 bbox_snwe 二选一）
        bbox_snwe: 处理范围 [South, North, West, East] 单位度（与 shapefile_path 二选一）

    Returns:
        List[int]: 需要处理的 subswath 编号列表，如 [1, 2] 或 []

    Raises:
        FileNotFoundError: 如果文件不存在
        ValueError: 若未提供 shapefile_path 或 bbox_snwe，或数据格式错误

    Example:
        >>> subswaths = detect_subswaths(
        ...     'data/raw/S1A_IW_SLC.zip',
        ...     shapefile_path='data/raw/target.shp'
        ... )
        >>> subswaths = detect_subswaths(
        ...     'data/raw/S1A_IW_SLC.zip',
        ...     bbox_snwe=[30.0, 31.0, 116.0, 117.0]  # S, N, W, E
        ... )
    """
    if shapefile_path and bbox_snwe:
        raise ValueError("shapefile_path 与 bbox_snwe 只能提供其一")
    if not shapefile_path and not bbox_snwe:
        raise ValueError("必须提供 shapefile_path 或 bbox_snwe")
    if bbox_snwe is not None and len(bbox_snwe) != 4:
        raise ValueError("bbox_snwe 须为 4 个浮点数 [South, North, West, East]")
    detector = SubswathDetector(
        sentinel1_zip_path,
        shapefile_path=shapefile_path,
        bbox_snwe=tuple(bbox_snwe) if bbox_snwe else None,
    )
    return detector.detect_subswaths()


def detect_subswaths_with_details(
    sentinel1_zip_path: str,
    shapefile_path: Optional[str] = None,
    bbox_snwe: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    检测需处理的 subswath，并返回用于日志展示的详细信息。

    Returns:
        dict:
            - swaths: List[int]，需处理的 swath 编号
            - date: str，成像日期（如 2022-01-01），可能为空
            - input_nwse: (N, W, S, E) 输入处理范围
            - swath_footprints_nwse: {swath_id: (N, W, S, E), ...}
            - intersection: {swath_id: bool, ...}
    """
    if shapefile_path and bbox_snwe:
        raise ValueError("shapefile_path 与 bbox_snwe 只能提供其一")
    if not shapefile_path and not bbox_snwe:
        raise ValueError("必须提供 shapefile_path 或 bbox_snwe")
    if bbox_snwe is not None and len(bbox_snwe) != 4:
        raise ValueError("bbox_snwe 须为 4 个浮点数 [South, North, West, East]")

    detector = SubswathDetector(
        sentinel1_zip_path,
        shapefile_path=shapefile_path,
        bbox_snwe=tuple(bbox_snwe) if bbox_snwe else None,
    )
    task_bbox = detector.extract_task_area_bbox()
    footprints = detector.extract_subswath_footprints()

    # 输入范围：task_bbox 为 (min_lon, min_lat, max_lon, max_lat)，转为 (N, W, S, E)
    input_nwse = _bbox_to_nwse(task_bbox)

    swath_footprints_nwse = {}
    intersection = {}
    required = []

    for sid in sorted(footprints.keys()):
        fp = footprints[sid]
        swath_footprints_nwse[sid] = _bbox_to_nwse(fp)
        inter = detector.check_intersection(task_bbox, fp)
        intersection[sid] = inter
        if inter:
            required.append(sid)

    date_str = _get_sensing_date_from_path(sentinel1_zip_path)

    return {
        "swaths": required,
        "date": date_str,
        "input_nwse": input_nwse,
        "swath_footprints_nwse": swath_footprints_nwse,
        "intersection": intersection,
    }


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("用法: python subswath_detector.py <sentinel1_zip_path> [<shapefile_path>]")
        print("  或: python subswath_detector.py <sentinel1_zip_path> --bbox South North West East")
        sys.exit(1)

    sentinel1_path = sys.argv[1]
    shapefile_path = None
    bbox_snwe = None
    if len(sys.argv) >= 6 and sys.argv[2] == "--bbox":
        bbox_snwe = [float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])]
    elif len(sys.argv) >= 3:
        shapefile_path = sys.argv[2]

    try:
        result = detect_subswaths(sentinel1_path, shapefile_path=shapefile_path, bbox_snwe=bbox_snwe)
        print(f"需要处理的subswath: {result}")
    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        sys.exit(1)
