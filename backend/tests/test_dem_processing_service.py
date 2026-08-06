"""DEM 拼接：SRTM 瓦片名、dem.py 命令 cwd、EGM96→WGS84 产物校验。"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.dem_processing_service import (
    build_dem_stitch_command,
    copy_dem_product_group,
    format_srtm_tile_name,
    list_srtm_tiles_for_bbox,
    resolve_vrt_source_filename,
    run_dem_stitch_wsl,
    select_primary_dem_product,
    validate_dem_raster_product,
)


def test_format_srtm_tile_name_longitude_padded_to_three_digits():
    assert format_srtm_tile_name(28, 96) == "N28E096"
    assert format_srtm_tile_name(28, 5) == "N28E005"
    assert format_srtm_tile_name(28, 105) == "N28E105"


def test_format_srtm_tile_name_latitude_padded_to_two_digits():
    assert format_srtm_tile_name(8, 96) == "N08E096"
    assert format_srtm_tile_name(-35, -74) == "S35W074"


def test_list_srtm_tiles_for_bbox_single_tile():
    assert list_srtm_tiles_for_bbox(28, 29, 96, 97) == ["N28E096"]


def test_correct_egm96_default_is_true():
    sig = inspect.signature(run_dem_stitch_wsl)
    assert sig.parameters["correct_egm96"].default is True


def test_build_dem_stitch_command_cwd_is_raw_dir_not_isce2():
    cmd = build_dem_stitch_command(
        isce2_main_wsl="/root/miniconda3/envs/isce2/lib/python3.11/site-packages/isce",
        dem_raw_dir_wsl="/mnt/n/NASASRTM1",
        bbox_south=28,
        bbox_north=29,
        bbox_west=96,
        bbox_east=97,
        output_name="test_dem",
        correct_egm96=True,
    )
    assert cmd.startswith("cd '/mnt/n/NASASRTM1' &&")
    assert "cd '/root/miniconda3" not in cmd.split("&&")[0]
    assert "/applications/dem.py" in cmd
    assert " -c" in cmd or cmd.rstrip().endswith("-c")
    assert "PYTHONPATH='/root/miniconda3/envs/isce2/lib/python3.11/site-packages/isce'" in cmd


def test_build_dem_stitch_command_without_correct_omits_c():
    cmd = build_dem_stitch_command(
        isce2_main_wsl="/opt/isce",
        dem_raw_dir_wsl="/mnt/d/dem_raw",
        bbox_south=1,
        bbox_north=2,
        bbox_west=3,
        bbox_east=4,
        correct_egm96=False,
    )
    assert " -c" not in cmd
    assert not cmd.rstrip().endswith("-c")


def _write_isce_xml(xml_path: Path, width: int, length: int, dtype: str = "FLOAT") -> None:
    xml_path.write_text(
        f"""<?xml version="1.0"?>
<imageFile>
  <property name="width"><value>{width}</value></property>
  <property name="length"><value>{length}</value></property>
  <property name="data_type"><value>{dtype}</value></property>
</imageFile>
""",
        encoding="utf-8",
    )


def _write_vrt(vrt_path: Path, source_name: str, relative: bool = True) -> None:
    rel = ' relativeToVRT="1"' if relative else ""
    vrt_path.write_text(
        f"""<VRTDataset rasterXSize="2" rasterYSize="2">
  <VRTRasterBand dataType="Float32" band="1">
    <SimpleSource>
      <SourceFilename{rel}>{source_name}</SourceFilename>
    </SimpleSource>
  </VRTRasterBand>
</VRTDataset>
""",
        encoding="utf-8",
    )


def _make_product(dir_path: Path, basename: str, width: int = 2, length: int = 2, dtype: str = "FLOAT") -> Path:
    """创建完整 DEM 产品组：实体 + xml + vrt。FLOAT=4 字节。"""
    data = dir_path / basename
    bps = 4 if dtype.upper() == "FLOAT" else 2
    data.write_bytes(b"\x00" * (width * length * bps))
    _write_isce_xml(Path(str(data) + ".xml"), width, length, dtype)
    _write_vrt(Path(str(data) + ".vrt"), basename, relative=True)
    return data


def test_validate_dem_raster_product_ok(tmp_path: Path):
    data = _make_product(tmp_path, "a.dem.wgs84")
    ok, msg = validate_dem_raster_product(str(data))
    assert ok, msg


def test_validate_fails_when_wgs84_missing_but_xml_vrt_exist(tmp_path: Path):
    phantom = tmp_path / "a.dem.wgs84"
    _write_isce_xml(Path(str(phantom) + ".xml"), 2, 2)
    _write_vrt(Path(str(phantom) + ".vrt"), "a.dem.wgs84")
    ok, msg = validate_dem_raster_product(str(phantom))
    assert not ok
    assert "不存在" in msg


def test_validate_fails_when_vrt_points_missing(tmp_path: Path):
    data = _make_product(tmp_path, "a.dem.wgs84")
    _write_vrt(Path(str(data) + ".vrt"), "missing.dem.wgs84", relative=True)
    ok, msg = validate_dem_raster_product(str(data))
    assert not ok
    assert "不存在" in msg or "SourceFilename" in msg


def test_validate_fails_when_size_mismatch(tmp_path: Path):
    data = _make_product(tmp_path, "a.dem.wgs84", width=2, length=2)
    data.write_bytes(b"\x00" * 7)  # 期望 16
    ok, msg = validate_dem_raster_product(str(data))
    assert not ok
    assert "不一致" in msg


def test_select_primary_correct_true_requires_wgs84(tmp_path: Path):
    dem = tmp_path / "x.dem"
    dem.write_bytes(b"\x00" * 4)
    assert select_primary_dem_product(str(tmp_path), "x", True) is None
    wgs = tmp_path / "x.dem.wgs84"
    wgs.write_bytes(b"\x00" * 4)
    assert select_primary_dem_product(str(tmp_path), "x", True) == str(wgs)


def test_select_primary_correct_false_returns_dem(tmp_path: Path):
    dem = tmp_path / "x.dem"
    dem.write_bytes(b"\x00" * 4)
    (tmp_path / "x.dem.wgs84").write_bytes(b"\x00" * 4)
    assert select_primary_dem_product(str(tmp_path), "x", False) == str(dem)


def test_copy_dem_product_group_rewrites_vrt(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    out.mkdir()
    data = _make_product(raw, "tile.dem.wgs84")
    # 故意写成绝对路径 SourceFilename
    _write_vrt(Path(str(data) + ".vrt"), str(data), relative=False)
    dst = copy_dem_product_group(str(data), str(out))
    assert os.path.isfile(dst)
    assert os.path.isfile(dst + ".xml")
    assert os.path.isfile(dst + ".vrt")
    resolved = resolve_vrt_source_filename(dst + ".vrt")
    assert resolved is not None
    assert os.path.abspath(resolved) == os.path.abspath(dst)
    ok, msg = validate_dem_raster_product(dst)
    assert ok, msg


def _mock_wsl_ok(raw_dir: Path, create_product: callable):
    """公共 fixture：mock WSL，并在 run_wsl 时于 raw_dir 写入产品。"""

    def fake_run_wsl(cmd, **kwargs):
        create_product()
        return {"success": True, "returncode": 0, "stdout": "ok", "stderr": "", "error_message": None}

    return fake_run_wsl


@patch("backend.services.dem_processing_service.ensure_srtm_tiles_in_dir")
@patch("backend.services.dem_processing_service.wsl_runner")
def test_run_dem_stitch_wgs84_complete_success(mock_wsl, mock_tiles, tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    out.mkdir()

    mock_wsl.use_wsl.return_value = True
    mock_wsl.build_wsl_isce2_extra_env.return_value = (
        {"INSAR_WSL_ISCE2_MAIN": "/opt/isce"},
        None,
    )
    mock_wsl.get_wsl_env_script.return_value = None
    mock_wsl.resolve_windows_path_to_wsl.return_value = ("/mnt/raw", None)
    mock_wsl.get_wsl_distro.return_value = "Ubuntu"

    def create():
        _make_product(raw, "demo.dem.wgs84")
        # 同时留一个 .dem，确保不会选它
        (raw / "demo.dem").write_bytes(b"\x00" * 16)

    mock_wsl.run_wsl.side_effect = _mock_wsl_ok(raw, create)

    logs: list[str] = []
    result = run_dem_stitch_wsl(
        28, 29, 96, 97,
        dem_raw_dir=str(raw),
        output_dir=str(out),
        output_name="demo",
        correct_egm96=True,
        stream_callback=logs.append,
    )
    assert result["success"] is True
    assert result["output_path"].endswith(".dem.wgs84")
    assert result["vertical_datum"] == "wgs84_ellipsoid"
    assert result["conversion_applied"] is True
    assert not result["output_path"].endswith(".dem") or result["output_path"].endswith(".dem.wgs84")
    cmd = mock_wsl.run_wsl.call_args[0][0]
    assert cmd.startswith("cd '/mnt/raw'")
    assert " -c" in cmd
    assert any("启用" in x or "-c" in x for x in logs)


@patch("backend.services.dem_processing_service.ensure_srtm_tiles_in_dir")
@patch("backend.services.dem_processing_service.wsl_runner")
def test_run_dem_stitch_missing_wgs84_fails_no_fallback(mock_wsl, mock_tiles, tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    out.mkdir()

    mock_wsl.use_wsl.return_value = True
    mock_wsl.build_wsl_isce2_extra_env.return_value = (
        {"INSAR_WSL_ISCE2_MAIN": "/opt/isce"},
        None,
    )
    mock_wsl.get_wsl_env_script.return_value = None
    mock_wsl.resolve_windows_path_to_wsl.return_value = ("/mnt/raw", None)
    mock_wsl.get_wsl_distro.return_value = "Ubuntu"

    def create():
        # 仅 EGM96 .dem + 孤儿 xml/vrt（模拟旧 bug：实体写到 isce 包目录）
        dem = raw / "demo.dem"
        dem.write_bytes(b"\x00" * 16)
        phantom = raw / "demo.dem.wgs84"
        _write_isce_xml(Path(str(phantom) + ".xml"), 2, 2)
        _write_vrt(Path(str(phantom) + ".vrt"), "demo.dem.wgs84")

    mock_wsl.run_wsl.side_effect = _mock_wsl_ok(raw, create)

    result = run_dem_stitch_wsl(
        28, 29, 96, 97,
        dem_raw_dir=str(raw),
        output_dir=str(out),
        output_name="demo",
        correct_egm96=True,
    )
    assert result["success"] is False
    assert result["output_path"] is None
    assert "禁止回退" in (result.get("error_message") or "") or "未找到" in (result.get("error_message") or "")


@patch("backend.services.dem_processing_service.ensure_srtm_tiles_in_dir")
@patch("backend.services.dem_processing_service.wsl_runner")
def test_run_dem_stitch_correct_false_returns_egm96(mock_wsl, mock_tiles, tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    out.mkdir()

    mock_wsl.use_wsl.return_value = True
    mock_wsl.build_wsl_isce2_extra_env.return_value = (
        {"INSAR_WSL_ISCE2_MAIN": "/opt/isce"},
        None,
    )
    mock_wsl.get_wsl_env_script.return_value = None
    mock_wsl.resolve_windows_path_to_wsl.return_value = ("/mnt/raw", None)
    mock_wsl.get_wsl_distro.return_value = "Ubuntu"

    def create():
        _make_product(raw, "demo.dem")

    mock_wsl.run_wsl.side_effect = _mock_wsl_ok(raw, create)

    result = run_dem_stitch_wsl(
        28, 29, 96, 97,
        dem_raw_dir=str(raw),
        output_dir=str(out),
        output_name="demo",
        correct_egm96=False,
    )
    assert result["success"] is True
    assert result["output_path"].endswith(".dem")
    assert not result["output_path"].endswith(".wgs84")
    assert result["vertical_datum"] == "egm96_orthometric"
    assert result["conversion_applied"] is False
    cmd = mock_wsl.run_wsl.call_args[0][0]
    assert " -c" not in cmd


@patch("backend.services.dem_processing_service.ensure_srtm_tiles_in_dir")
@patch("backend.services.dem_processing_service.wsl_runner")
def test_run_dem_stitch_copy_group_to_other_output_dir(mock_wsl, mock_tiles, tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    raw.mkdir()
    out.mkdir()

    mock_wsl.use_wsl.return_value = True
    mock_wsl.build_wsl_isce2_extra_env.return_value = (
        {"INSAR_WSL_ISCE2_MAIN": "/opt/isce"},
        None,
    )
    mock_wsl.get_wsl_env_script.return_value = None
    mock_wsl.resolve_windows_path_to_wsl.return_value = ("/mnt/raw", None)
    mock_wsl.get_wsl_distro.return_value = "Ubuntu"

    def create():
        _make_product(raw, "demo.dem.wgs84")

    mock_wsl.run_wsl.side_effect = _mock_wsl_ok(raw, create)

    result = run_dem_stitch_wsl(
        28, 29, 96, 97,
        dem_raw_dir=str(raw),
        output_dir=str(out),
        output_name="demo",
        correct_egm96=True,
    )
    assert result["success"] is True
    out_path = Path(result["output_path"])
    assert out_path.parent == out
    assert (out / "demo.dem.wgs84").is_file()
    assert (out / "demo.dem.wgs84.xml").is_file()
    assert (out / "demo.dem.wgs84.vrt").is_file()
    ok, msg = validate_dem_raster_product(str(out_path))
    assert ok, msg


def test_dem_make_dialog_worker_passes_correct_egm96_true():
    """桌面端 DemStitchWorker 显式传 correct_egm96=True（与服务默认一致）。"""
    from desktop.app.widgets.dem_make_dialog import DemStitchWorker

    sig = inspect.signature(DemStitchWorker.__init__)
    assert sig.parameters["correct_egm96"].default is True
