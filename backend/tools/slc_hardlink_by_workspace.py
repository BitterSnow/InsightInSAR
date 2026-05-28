"""
按工作区范围与日期，从 SLC 目录筛选产品并在目标目录创建硬链接。
"""
from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.services.s1_processing_service import resolve_safe_paths

logger = logging.getLogger(__name__)

# (min_lon, min_lat, max_lon, max_lat)
Bbox = Tuple[float, float, float, float]

_DATE_RE = re.compile(r"(\d{8})T\d{6}")


@dataclass
class SlcProductInfo:
    path: str
    filename: str
    acq_date: str  # YYYYMMDD
    relative_orbit: Optional[int]
    footprint: Bbox
    intersecting_swaths: List[int] = field(default_factory=list)


@dataclass
class HardlinkRunResult:
    success: bool
    message: str
    workspace_snwe: Tuple[float, float, float, float]  # S, N, W, E
    path_orbits: Dict[int, List[str]] = field(default_factory=dict)
    selected: List[str] = field(default_factory=list)
    selected_swaths: Dict[str, List[int]] = field(default_factory=dict)
    skipped_dates: Dict[str, str] = field(default_factory=dict)
    link_errors: List[str] = field(default_factory=list)
    linked_count: int = 0


def snwe_to_bbox(south: float, north: float, west: float, east: float) -> Bbox:
    return (west, south, east, north)


def parse_acquisition_date(path: str) -> Optional[str]:
    """从 SAFE 产品名解析成像日期 YYYYMMDD。"""
    name = os.path.basename(path.rstrip("/\\"))
    if name.lower().endswith(".zip"):
        name = name[:-4]
    m = _DATE_RE.search(name)
    return m.group(1) if m else None


def bbox_intersects(a: Bbox, b: Bbox) -> bool:
    min_lon1, min_lat1, max_lon1, max_lat1 = a
    min_lon2, min_lat2, max_lon2, max_lat2 = b
    return not (
        max_lon1 < min_lon2
        or max_lon2 < min_lon1
        or max_lat1 < min_lat2
        or max_lat2 < min_lat1
    )


def bbox_contains(outer: Bbox, inner: Bbox) -> bool:
    """outer 是否完全包含 inner（用于 footprint 是否盖住工作区矩形）。"""
    o_min_lon, o_min_lat, o_max_lon, o_max_lat = outer
    i_min_lon, i_min_lat, i_max_lon, i_max_lat = inner
    return (
        o_min_lon <= i_min_lon
        and o_min_lat <= i_min_lat
        and o_max_lon >= i_max_lon
        and o_max_lat >= i_max_lat
    )


def bbox_union(boxes: List[Bbox]) -> Bbox:
    min_lon = min(b[0] for b in boxes)
    min_lat = min(b[1] for b in boxes)
    max_lon = max(b[2] for b in boxes)
    max_lat = max(b[3] for b in boxes)
    return (min_lon, min_lat, max_lon, max_lat)


def _workspace_to_snwe(workspace: Bbox) -> Tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = workspace
    return (min_lat, max_lat, min_lon, max_lon)


def _geolocation_hull_polygon(annotation_root) -> Optional[object]:
    """从 annotation geolocationGrid 点集生成凸包（需 shapely）。"""
    try:
        from shapely.geometry import MultiPoint
    except ImportError:
        return None
    pts: List[Tuple[float, float]] = []
    for point in annotation_root.iter():
        if not point.tag.endswith("geolocationGridPoint"):
            continue
        lon = lat = None
        for child in point:
            if child.tag.endswith("longitude"):
                lon = float(child.text)
            elif child.tag.endswith("latitude"):
                lat = float(child.text)
        if lon is not None and lat is not None:
            pts.append((lon, lat))
    if len(pts) < 3:
        return None
    return MultiPoint(pts).convex_hull


def extract_footprint_for_workspace(
    sentinel1_path: str,
    workspace: Bbox,
) -> Tuple[Bbox, List[int]]:
    """
    按 KML 工作区计算产品有效覆盖：仅统计与工作区多边形相交的 IW 条带，
    不用 manifest 整景外框（避免误选仅擦边或不相交的 Frame）。
    返回 (相交条带并集 bbox, 相交条带编号列表)。
    """
    from backend.scripts.subswath_detector import (
        SubswathDetector,
        _is_slc_annotation_path,
        _open_safe_archive,
    )

    try:
        from shapely.geometry import box as shapely_box
    except ImportError:
        shapely_box = None  # type: ignore

    s, n, w, e = _workspace_to_snwe(workspace)
    detector = SubswathDetector(str(sentinel1_path), bbox_snwe=(s, n, w, e))
    all_fps = detector.extract_subswath_footprints()

    if shapely_box is None:
        intersecting = {
            k: v for k, v in all_fps.items() if bbox_intersects(v, workspace)
        }
    else:
        ws_poly = shapely_box(workspace[0], workspace[1], workspace[2], workspace[3])
        intersecting = {}
        from pathlib import Path
        import xml.etree.ElementTree as ET

        with _open_safe_archive(Path(sentinel1_path)) as z:
            ann_by_swath: Dict[int, str] = {}
            for ann_file in z.namelist():
                if not _is_slc_annotation_path(ann_file):
                    continue
                low = ann_file.lower()
                sw = None
                if "iw1" in low:
                    sw = 1
                elif "iw2" in low:
                    sw = 2
                elif "iw3" in low:
                    sw = 3
                if sw is None or sw in ann_by_swath:
                    continue
                ann_by_swath[sw] = ann_file

            for sw, ann_file in ann_by_swath.items():
                root = ET.fromstring(z.read(ann_file))
                hull = _geolocation_hull_polygon(root)
                if hull is None:
                    fp = all_fps.get(sw)
                    if fp and bbox_intersects(fp, workspace):
                        intersecting[sw] = fp
                    continue
                inter = ws_poly.intersection(hull)
                if not inter.is_empty and inter.area > 0 and sw in all_fps:
                    intersecting[sw] = all_fps[sw]

    if not intersecting:
        raise ValueError(
            f"产品与 KML 工作区无相交 IW 条带（annotation 覆盖与 {workspace} 无重叠）: "
            f"{os.path.basename(sentinel1_path)}"
        )

    return bbox_union(list(intersecting.values())), sorted(intersecting.keys())


def _inspect_product(path: str, workspace: Bbox) -> SlcProductInfo:
    from backend.scripts.subswath_detector import extract_relative_orbit_number

    acq = parse_acquisition_date(path)
    if not acq:
        raise ValueError(f"无法从文件名解析成像日期: {path}")
    footprint, swaths = extract_footprint_for_workspace(path, workspace)
    rel_orbit = extract_relative_orbit_number(path)
    return SlcProductInfo(
        path=os.path.abspath(path),
        filename=os.path.basename(path),
        acq_date=acq,
        relative_orbit=rel_orbit,
        footprint=footprint,
        intersecting_swaths=swaths,
    )


def validate_same_relative_orbit(products: List[SlcProductInfo]) -> Tuple[bool, str, Dict[int, List[str]]]:
    """校验目录内产品 relativeOrbitNumber 一致。"""
    by_orbit: Dict[int, List[str]] = defaultdict(list)
    unknown: List[str] = []
    for p in products:
        if p.relative_orbit is None:
            unknown.append(p.filename)
        else:
            by_orbit[p.relative_orbit].append(p.filename)
    if unknown:
        return (
            False,
            f"以下产品无法读取 relativeOrbitNumber（Path）：{', '.join(unknown[:5])}"
            + (" …" if len(unknown) > 5 else ""),
            dict(by_orbit),
        )
    if len(by_orbit) > 1:
        parts = [f"Path {k}: {len(v)} 景" for k, v in sorted(by_orbit.items())]
        return (
            False,
            "SLC 目录中存在多个 relativeOrbitNumber（非同 Path）：" + "；".join(parts),
            dict(by_orbit),
        )
    return True, "", dict(by_orbit)


def select_products_for_date(
    candidates: List[SlcProductInfo],
    workspace: Bbox,
) -> List[SlcProductInfo]:
    """
    单日筛选：优先全部「完全覆盖」工作区的产品；否则取并集可盖住工作区的最小必要集合。
    仅相交但不能参与并集覆盖的 Frame 不选。
    """
    if not candidates:
        return []

    full_cover = [p for p in candidates if bbox_contains(p.footprint, workspace)]
    if full_cover:
        return full_cover

    intersecting = [p for p in candidates if bbox_intersects(p.footprint, workspace)]
    if not intersecting:
        return []

    union_all = bbox_union([p.footprint for p in intersecting])
    if not bbox_contains(union_all, workspace):
        return []

    selected = list(intersecting)
    changed = True
    while changed and len(selected) > 1:
        changed = False
        for item in list(selected):
            others = [x for x in selected if x.path != item.path]
            if not others:
                continue
            u = bbox_union([x.footprint for x in others])
            if bbox_contains(u, workspace):
                selected.remove(item)
                changed = True
                break

    return selected


def run_slc_hardlink_by_workspace(
    slc_dir: str,
    start_date: str,
    end_date: str,
    workspace_snwe: Tuple[float, float, float, float],
    link_dir: str,
) -> HardlinkRunResult:
    """
    主流程：同 Path 校验 → 按日期与空间筛选 → 硬链接（同名覆盖）。

    workspace_snwe: (South, North, West, East)
    start_date / end_date: YYYYMMDD，含端点。
    """
    south, north, west, east = workspace_snwe
    workspace = snwe_to_bbox(south, north, west, east)

    if not os.path.isdir(slc_dir):
        raise FileNotFoundError(f"SLC 目录不存在: {slc_dir}")
    os.makedirs(link_dir, exist_ok=True)

    start_date = start_date.strip()
    end_date = end_date.strip()
    if len(start_date) != 8 or len(end_date) != 8 or start_date > end_date:
        raise ValueError("起始/结束日期须为 YYYYMMDD，且起始 ≤ 结束。")

    paths = resolve_safe_paths(slc_dir)
    if not paths:
        return HardlinkRunResult(
            success=False,
            message="SLC 目录中未发现 .zip 或 .SAFE 数据。",
            workspace_snwe=workspace_snwe,
        )

    products: List[SlcProductInfo] = []
    inspect_errors: List[str] = []
    for p in paths:
        try:
            products.append(_inspect_product(p, workspace))
        except Exception as e:
            inspect_errors.append(f"{os.path.basename(p)}: {e}")
            logger.warning("解析产品失败 %s: %s", p, e)

    if not products:
        return HardlinkRunResult(
            success=False,
            message="无法解析任何 SLC 产品。" + (
                "\n" + "\n".join(inspect_errors[:5]) if inspect_errors else ""
            ),
            workspace_snwe=workspace_snwe,
        )

    ok_path, path_msg, path_orbits = validate_same_relative_orbit(products)
    if not ok_path:
        return HardlinkRunResult(
            success=False,
            message=path_msg,
            workspace_snwe=workspace_snwe,
            path_orbits=path_orbits,
        )

    in_range = [
        p
        for p in products
        if start_date <= p.acq_date <= end_date
    ]
    if not in_range:
        return HardlinkRunResult(
            success=False,
            message=f"日期范围内无产品（{start_date}–{end_date}）。",
            workspace_snwe=workspace_snwe,
            path_orbits=path_orbits,
        )

    by_date: Dict[str, List[SlcProductInfo]] = defaultdict(list)
    for p in in_range:
        by_date[p.acq_date].append(p)

    selected_paths: List[str] = []
    selected_swaths: Dict[str, List[int]] = {}
    skipped_dates: Dict[str, str] = {}

    for date_key in sorted(by_date.keys()):
        chosen = select_products_for_date(by_date[date_key], workspace)
        if not chosen:
            skipped_dates[date_key] = "无单景完全覆盖，且多景并集仍无法盖住工作区矩形"
            continue
        for item in chosen:
            if item.path not in selected_paths:
                selected_paths.append(item.path)
                selected_swaths[item.path] = list(item.intersecting_swaths)
                iw = ",".join(str(s) for s in item.intersecting_swaths) or "?"
                logger.info(
                    "选中 %s（相交 IW%s）footprint=%s",
                    item.filename,
                    iw,
                    item.footprint,
                )

    link_errors: List[str] = []
    linked = 0
    for src in selected_paths:
        dst = os.path.join(link_dir, os.path.basename(src))
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.link(src, dst)
            linked += 1
        except OSError as e:
            hint = ""
            if getattr(e, "winerror", None) == 17 or "same device" in str(e).lower():
                hint = "（Windows 硬链接须与源文件在同一磁盘分区）"
            msg = f"硬链接失败 {os.path.basename(src)}: {e}{hint}"
            link_errors.append(msg)
            logger.warning(msg)

    msg_parts = [
        f"工作区 S/N/W/E = {south:.4f}/{north:.4f}/{west:.4f}/{east:.4f}",
        f"日期 {start_date}–{end_date}，选中 {len(selected_paths)} 景，已硬链接 {linked} 个。",
    ]
    if skipped_dates:
        msg_parts.append(f"跳过 {len(skipped_dates)} 个成像日。")
    if inspect_errors:
        msg_parts.append(f"解析失败 {len(inspect_errors)} 个文件（未参与筛选）。")

    return HardlinkRunResult(
        success=linked > 0 and not link_errors,
        message="\n".join(msg_parts),
        workspace_snwe=workspace_snwe,
        path_orbits=path_orbits,
        selected=selected_paths,
        selected_swaths=selected_swaths,
        skipped_dates=skipped_dates,
        link_errors=link_errors,
        linked_count=linked,
    )
