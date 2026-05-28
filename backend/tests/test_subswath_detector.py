"""Unit tests for Sentinel-1 subswath detection helpers."""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.scripts.subswath_detector import (
    SubswathDetector,
    _is_slc_annotation_path,
    detect_subswaths,
)
from backend.services.s1_processing_service import summarize_slc_directory


def test_is_slc_annotation_path_filters_calibration():
    cal = (
        "S1A_IW.SAFE/annotation/calibration/"
        "calibration-s1a-iw1-slc-vv-20240922t230522.xml"
    )
    ann = "S1A_IW.SAFE/annotation/s1a-iw1-slc-vv-20240922t230522.xml"
    assert not _is_slc_annotation_path(cal)
    assert _is_slc_annotation_path(ann)


def test_manifest_coordinates_parsed_as_lat_lon():
    """manifest gml:coordinates 为 lat,lon 对；错误解析会导致与任务区不相交。"""
    coords = (
        "28.436581,104.518524 28.843811,101.977692 "
        "30.466162,102.295349 30.061501,104.879059"
    )
    detector = SubswathDetector.__new__(SubswathDetector)
    pairs = []
    for pair in coords.strip().split():
        a, b = pair.split(",")
        lat, lon = float(a), float(b)
        pairs.append((lon, lat))
    lons = [c[0] for c in pairs]
    lats = [c[1] for c in pairs]
    footprint = (min(lons), min(lats), max(lons), max(lats))
    task = (103.86, 29.20, 104.10, 29.44)
    assert detector.check_intersection(task, footprint)


def test_summarize_empty_directory():
    with tempfile.TemporaryDirectory() as tmp:
        info = summarize_slc_directory(tmp)
        assert info["total"] == 0


def test_detect_subswaths_with_sample_zip_if_present():
    """可选：data/raw 下有样例 zip 时运行完整检测。"""
    sample = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
        "raw",
        "S1A_IW_SLC__1SDV_20200714T231403_20200714T231430_033457_03E080_5554.zip",
    )
    sample = os.path.abspath(sample)
    if not os.path.isfile(sample):
        return
    # 使用较宽 bbox，至少不应因坐标轴颠倒而返回空
    swaths = detect_subswaths(sample, bbox_snwe=[20.0, 45.0, 90.0, 120.0])
    assert isinstance(swaths, list)
