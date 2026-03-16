"""
从 Shapefile 或 KML 文件读取四至范围 (N, S, W, E)。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def read_bbox_from_shapefile(file_path: str | Path) -> tuple[float, float, float, float]:
    """
    读取 .shp 的边界框，返回 (N, S, W, E)。
    若文件无效或无几何则抛出 ValueError。
    """
    try:
        import shapefile
    except ImportError:
        raise ValueError("请安装 pyshp 以支持 Shapefile：pip install pyshp")
    path = Path(file_path)
    if not path.suffix.lower() == ".shp":
        path = Path(str(file_path) + ("" if str(file_path).lower().endswith(".shp") else ".shp"))
    if not path.exists():
        raise ValueError(f"文件不存在：{path}")
    try:
        with shapefile.Reader(str(path)) as shp:
            bbox = shp.bbox
        if bbox is None or len(bbox) < 4:
            raise ValueError("无法从 Shapefile 读取边界框")
        # shapefile bbox: [xmin, ymin, xmax, ymax] -> (N=ymax, S=ymin, W=xmin, E=xmax)
        w, s, e, n = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        return (n, s, w, e)
    except Exception as e:
        raise ValueError(f"读取 Shapefile 失败：{e}") from e


def read_bbox_from_kml(file_path: str | Path) -> tuple[float, float, float, float]:
    """
    读取 .kml 的边界（LatLonBox 或 coordinates 范围），返回 (N, S, W, E)。
    若无法解析则抛出 ValueError。
    """
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"文件不存在：{path}")
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        # KML 2.0 namespace
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        # 尝试 LatLonBox
        for box in root.iter("{http://www.opengis.net/kml/2.2}LatLonBox"):
            n = box.find("{http://www.opengis.net/kml/2.2}north")
            s = box.find("{http://www.opengis.net/kml/2.2}south")
            w = box.find("{http://www.opengis.net/kml/2.2}west")
            e = box.find("{http://www.opengis.net/kml/2.2}east")
            if n is not None and s is not None and w is not None and e is not None:
                return (float(n.text), float(s.text), float(w.text), float(e.text))
        # 无 namespace 的 LatLonBox
        for box in root.iter("LatLonBox"):
            n = box.find("north")
            s = box.find("south")
            w = box.find("west")
            e = box.find("east")
            if n is not None and s is not None and w is not None and e is not None:
                return (float(n.text), float(s.text), float(w.text), float(e.text))
        # 从 <coordinates> 解析所有点求 bbox
        lats, lons = [], []
        for coord_elem in root.iter():
            if "coordinates" in coord_elem.tag or coord_elem.tag.endswith("coordinates"):
                text = (coord_elem.text or "").strip()
                for part in text.replace("\n", " ").split():
                    parts = part.split(",")
                    if len(parts) >= 2:
                        try:
                            lon, lat = float(parts[0]), float(parts[1])
                            lons.append(lon)
                            lats.append(lat)
                        except ValueError:
                            continue
        if lats and lons:
            return (max(lats), min(lats), min(lons), max(lons))
        raise ValueError("KML 中未找到 LatLonBox 或 coordinates")
    except ET.ParseError as e:
        raise ValueError(f"KML 解析失败：{e}") from e
    except Exception as e:
        raise ValueError(f"读取 KML 失败：{e}") from e


def read_bbox_from_file(file_path: str | Path) -> tuple[float, float, float, float]:
    """
    根据扩展名调用 Shapefile 或 KML 解析，返回 (N, S, W, E)。
    仅支持 .shp 与 .kml。
    """
    path = Path(file_path)
    suf = path.suffix.lower()
    if suf == ".shp":
        return read_bbox_from_shapefile(path)
    if suf == ".kml":
        return read_bbox_from_kml(path)
    raise ValueError("仅支持 Shapefile (.shp) 或 KML (.kml) 格式")
