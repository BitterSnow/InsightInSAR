"""Unit tests for SLC hardlink by workspace selection logic."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.tools.slc_hardlink_by_workspace import (
    Bbox,
    SlcProductInfo,
    bbox_contains,
    bbox_intersects,
    bbox_union,
    select_products_for_date,
    snwe_to_bbox,
    validate_same_relative_orbit,
)


def _p(path: str, date: str, fp: Bbox, orbit: int = 62) -> SlcProductInfo:
    return SlcProductInfo(
        path=path,
        filename=os.path.basename(path),
        acq_date=date,
        relative_orbit=orbit,
        footprint=fp,
    )


def test_bbox_contains_workspace():
    ws = snwe_to_bbox(29.0, 30.0, 103.0, 104.0)
    big = (102.0, 28.0, 105.0, 31.0)
    small = (103.5, 29.5, 103.8, 29.8)
    assert bbox_contains(big, ws)
    assert not bbox_contains(small, ws)


def test_select_all_full_cover():
    ws = snwe_to_bbox(29.2, 29.4, 103.86, 104.1)
    inner = (103.0, 29.0, 104.5, 29.5)
    outer = (103.0, 29.0, 104.5, 30.0)
    cands = [
        _p("/a.zip", "20260412", inner),
        _p("/b.zip", "20260412", outer),
    ]
    sel = select_products_for_date(cands, ws)
    assert len(sel) == 2
    assert {x.filename for x in sel} == {"a.zip", "b.zip"}


def test_select_union_two_frames():
    ws = snwe_to_bbox(29.2, 29.4, 103.86, 104.1)
    left = (103.86, 29.2, 103.95, 29.4)
    right = (104.0, 29.2, 104.1, 29.4)
    edge = (103.0, 29.0, 103.7, 29.3)  # intersects but union with left+right not needed if alone
    cands = [_p("/l.zip", "20260412", left), _p("/r.zip", "20260412", right), _p("/e.zip", "20260412", edge)]
    sel = select_products_for_date(cands, ws)
    names = {x.filename for x in sel}
    assert "l.zip" in names and "r.zip" in names
    assert "e.zip" not in names
    assert bbox_contains(bbox_union([x.footprint for x in sel]), ws)


def test_skip_date_no_cover():
    ws = snwe_to_bbox(29.2, 29.4, 103.86, 104.1)
    partial = (103.0, 29.0, 103.5, 29.3)
    sel = select_products_for_date([_p("/p.zip", "20260412", partial)], ws)
    assert sel == []


def test_select_excludes_bbox_only_touch_outside_workspace():
    """条带外接框与 KML 相交但工作区中心不在条带内时，仍可能因多边形相交入选；此处测明显不相交。"""
    ws = snwe_to_bbox(30.0, 30.5, 120.0, 120.5)
    far = (100.0, 20.0, 101.0, 21.0)
    sel = select_products_for_date([_p("/far.zip", "20260412", far)], ws)
    assert sel == []


def test_validate_same_path():
    ok, msg, orbits = validate_same_relative_orbit(
        [_p("/a.zip", "20260101", (0, 0, 1, 1), 62), _p("/b.zip", "20260102", (0, 0, 1, 1), 62)]
    )
    assert ok and not msg
    ok2, msg2, _ = validate_same_relative_orbit(
        [_p("/a.zip", "20260101", (0, 0, 1, 1), 62), _p("/b.zip", "20260102", (0, 0, 1, 1), 63)]
    )
    assert not ok2 and "非同 Path" in msg2 or "relativeOrbitNumber" in msg2
