"""Unit tests for ASF POEORB parsing (no network)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.services.sentinel_orbit_asf import (
    find_covering_poeorb_in_list,
    parse_poeorb_validity,
    parse_safe_sensing_mission,
)


def test_parse_safe_sensing_mission():
    p = "/data/S1A_IW_SLC__1SDV_20230820T225923_20230820T225958_048546_05D6CB_49E6.zip"
    r = parse_safe_sensing_mission(p)
    assert r is not None
    mission, sensing, _ = r
    assert mission == "S1A"
    assert sensing == datetime(2023, 8, 20, 22, 59, 23, tzinfo=timezone.utc)


def test_parse_safe_sensing_mission_s1c():
    p = "/data/S1C_IW_SLC__1SDV_20251110T230338_20251110T230405_004958_009CF4_AD7B.zip"
    r = parse_safe_sensing_mission(p)
    assert r is not None
    mission, sensing, _ = r
    assert mission == "S1C"
    assert sensing == datetime(2025, 11, 10, 23, 3, 38, tzinfo=timezone.utc)


def test_parse_poeorb_validity():
    fn = "S1A_OPER_AUX_POEORB_OPOD_20230822T122852_V20230820T225923_20230822T005942.EOF"
    p = parse_poeorb_validity(fn)
    assert p is not None
    mission, vs, ve = p
    assert mission == "S1A"
    assert vs < ve
    sensing = datetime(2023, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    assert vs <= sensing <= ve


def test_find_covering_in_list():
    names = [
        "S1A_OPER_AUX_POEORB_OPOD_20230822T122852_V20230820T225923_20230822T005942.EOF",
        "S1A_OPER_AUX_POEORB_OPOD_20230823T122852_V20230821T225923_20230823T005942.EOF",
    ]
    st = datetime(2023, 8, 21, 10, 0, 0, tzinfo=timezone.utc)
    hit = find_covering_poeorb_in_list("S1A", st, names)
    assert hit == names[0]


def test_orbit_validity_around_sensing_day():
    # 常见规则：validity 写成像时刻前后各约一天（26 小时覆盖窗口）
    names = [
        "S1C_OPER_AUX_POEORB_OPOD_20251112T120000_V20251108T230000_20251110T220000.EOF",
        "S1C_OPER_AUX_POEORB_OPOD_20251113T120000_V20251110T230000_20251112T010000.EOF",
    ]
    sensing = datetime(2025, 11, 10, 23, 3, 38, tzinfo=timezone.utc)
    hit = find_covering_poeorb_in_list("S1C", sensing, names)
    assert hit == names[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
