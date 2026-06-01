"""
将 MintPy 速度栅格与 TimeSeries HDF5 转为矢量点图层（GeoPackage / Shapefile）。
依赖：h5py, numpy, osgeo；可选 geopandas（WSL conda 下批量写入更快）。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

OutputFormat = str  # "gpkg" | "shp"
LAYER_NAME = "sbas_points"
DEFAULT_OUTPUT_FORMAT = "gpkg"
OGR_BATCH_SIZE = 20000


def output_basename(output_format: OutputFormat) -> str:
    return "sbas_points.gpkg" if output_format == "gpkg" else "sbas_points.shp"


def output_path(out_dir: str, output_format: OutputFormat) -> str:
    return os.path.join(out_dir, output_basename(output_format))


def _normalize_output_format(output_format: str) -> OutputFormat:
    fmt = (output_format or DEFAULT_OUTPUT_FORMAT).strip().lower()
    if fmt in ("gpkg", "geopackage", "geo_package"):
        return "gpkg"
    if fmt in ("shp", "shapefile", "esri shapefile"):
        return "shp"
    raise ValueError(f"不支持的输出格式: {output_format}（请使用 gpkg 或 shp）")


def _decode_h5_attr(val: Any) -> Any:
    if isinstance(val, bytes):
        return val.decode("utf-8")
    if isinstance(val, np.ndarray) and val.size == 1:
        return _decode_h5_attr(val.item())
    return val


def _attr_float(attrs: dict, *names: str) -> float:
    for name in names:
        if name in attrs:
            return float(_decode_h5_attr(attrs[name]))
    raise KeyError(f"缺少地理参考属性（需要其一）: {', '.join(names)}")


def _merge_h5_attrs(*sources: dict) -> dict:
    merged: dict = {}
    for src in sources:
        for k, v in src.items():
            merged[k] = v
    return merged


def _geotransform_from_mintpy_attrs(attrs: dict) -> tuple:
    x_first = _attr_float(attrs, "X_FIRST", "x_first")
    y_first = _attr_float(attrs, "Y_FIRST", "y_first")
    x_step = _attr_float(attrs, "X_STEP", "x_step")
    y_step = _attr_float(attrs, "Y_STEP", "y_step")
    return (x_first, x_step, 0.0, y_first, 0.0, y_step)


def _find_velocity_dataset(h5_file) -> Any:
    import h5py

    if "velocity" in h5_file:
        obj = h5_file["velocity"]
        if isinstance(obj, h5py.Dataset):
            return obj
        if isinstance(obj, h5py.Group):
            for key in obj.keys():
                child = obj[key]
                if isinstance(child, h5py.Dataset) and child.ndim == 2:
                    return child
    for key in h5_file.keys():
        obj = h5_file[key]
        if isinstance(obj, h5py.Dataset) and obj.ndim == 2:
            return obj
    raise ValueError("velocity HDF5 中未找到二维速度数据集（期望 dataset 名 velocity）")


def _load_velocity_h5(vel_h5_path: str) -> Tuple[np.ndarray, tuple, int, int]:
    import h5py

    with h5py.File(vel_h5_path, "r") as f:
        dset = _find_velocity_dataset(f)
        vel_array = np.asarray(dset[()])
        attrs = _merge_h5_attrs(dict(f.attrs), dict(dset.attrs))
        gt = _geotransform_from_mintpy_attrs(attrs)
    y_size, x_size = vel_array.shape
    return vel_array, gt, x_size, y_size


def _load_velocity_geotiff(vel_tiff_path: str) -> Tuple[np.ndarray, tuple, int, int]:
    from osgeo import gdal

    gdal.UseExceptions()
    vel_ds = gdal.Open(vel_tiff_path)
    if vel_ds is None:
        raise RuntimeError(f"无法打开 GeoTIFF: {vel_tiff_path}")
    gt = vel_ds.GetGeoTransform()
    x_size = vel_ds.RasterXSize
    y_size = vel_ds.RasterYSize
    vel_array = vel_ds.GetRasterBand(1).ReadAsArray()
    vel_ds = None
    return vel_array, gt, x_size, y_size


def _load_velocity_raster(vel_path: str) -> Tuple[np.ndarray, tuple, int, int]:
    ext = os.path.splitext(vel_path)[1].lower()
    if ext in (".h5", ".he5"):
        return _load_velocity_h5(vel_path)
    if ext in (".tif", ".tiff"):
        return _load_velocity_geotiff(vel_path)
    raise ValueError(f"不支持的速度文件格式: {ext}（请使用 MintPy velocity .h5 或 GeoTIFF）")


def _pixel_coords_to_lonlat(xs: np.ndarray, ys: np.ndarray, gt: tuple) -> Tuple[np.ndarray, np.ndarray]:
    lon = gt[0] + xs.astype(np.float64) * gt[1] + ys.astype(np.float64) * gt[2]
    lat = gt[3] + xs.astype(np.float64) * gt[4] + ys.astype(np.float64) * gt[5]
    return lon, lat


def _collect_valid_pixels(
    vel_array: np.ndarray,
    pixel_span: int,
    max_points: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """按 pixel_span 稀疏采样，向量化筛选有效速度点。"""
    span = max(1, int(pixel_span))
    vel_sub = vel_array[0::span, 0::span]
    valid = np.isfinite(vel_sub) & (vel_sub != 0.0) & (np.abs(vel_sub) <= 100.0)
    ys_sub, xs_sub = np.nonzero(valid)
    if ys_sub.size == 0:
        return (
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int64),
            np.array([], dtype=np.float64),
        )
    ys = (ys_sub * span).astype(np.int64)
    xs = (xs_sub * span).astype(np.int64)
    vel_mm = vel_sub[ys_sub, xs_sub].astype(np.float64) * 1000.0

    if max_points > 0 and vel_mm.size > max_points:
        rng = np.random.default_rng(42)
        pick = rng.choice(vel_mm.size, int(max_points), replace=False)
        pick.sort()
        ys = ys[pick]
        xs = xs[pick]
        vel_mm = vel_mm[pick]
        logger.info("有效点超过上限，随机保留 %s / %s 个点", max_points, valid.sum())

    return ys, xs, vel_mm


def _sort_pixels_for_h5(
    ys: np.ndarray, xs: np.ndarray, vel_mm: np.ndarray, x_size: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """h5py 多维列表索引要求按存储顺序递增（C 行优先）。"""
    if ys.size <= 1:
        return ys, xs, vel_mm
    order = np.argsort(ys.astype(np.int64) * int(x_size) + xs.astype(np.int64), kind="mergesort")
    return ys[order], xs[order], vel_mm[order]


def _read_timeseries_at_pixels(
    h5_file_path: str,
    ys: np.ndarray,
    xs: np.ndarray,
    x_size: int,
    pixel_span: int,
) -> Tuple[List[str], np.ndarray]:
    """读取有效像素处的 timeseries；避免整幅 ts[:] 进内存。"""
    import h5py

    n = ys.size
    if n == 0:
        return [], np.empty((0, 0), dtype=np.float32)

    span = max(1, int(pixel_span))
    with h5py.File(h5_file_path, "r") as f:
        if "timeseries" not in f:
            raise ValueError("HDF5 中缺少 timeseries 数据集")
        ts_dset = f["timeseries"]
        dates = [d.decode("utf-8") if isinstance(d, bytes) else str(d) for d in f["date"][:]]
        n_dates = len(dates)

        if span > 1:
            # 先降采样再索引，数据量约为 1/span²（如 span=4 时约 1/16）
            logger.info("timeseries 按 pixel_span=%s 降采样后读取", span)
            ts_sub = np.asarray(ts_dset[:, ::span, ::span], dtype=np.float32)
            ys_s = (ys // span).astype(np.int64)
            xs_s = (xs // span).astype(np.int64)
            ts_at = ts_sub[:, ys_s, xs_s]
        else:
            try:
                ts_at = np.asarray(ts_dset[:, ys, xs], dtype=np.float32)
            except (ValueError, OSError, TypeError):
                logger.info("timeseries 高级索引失败，逐时相 2D 切片读取（%s 期）", n_dates)
                ts_at = np.empty((n_dates, n), dtype=np.float32)
                for i in range(n_dates):
                    slab = np.asarray(ts_dset[i], dtype=np.float32)
                    ts_at[i] = slab[ys, xs]

    ts_at = np.where(np.isfinite(ts_at), ts_at * 1000.0, 0.0)
    return dates, ts_at


def _field_name_for_date(date: str, output_format: OutputFormat) -> str:
    name = f"D{date}"
    if output_format == "shp" and len(name) > 10:
        name = name[:10]
    return name


def _write_with_geopandas(
    out_file: str,
    output_format: OutputFormat,
    lons: np.ndarray,
    lats: np.ndarray,
    vel_mm: np.ndarray,
    dates: List[str],
    ts_at: np.ndarray,
) -> bool:
    try:
        import geopandas as gpd
        import pandas as pd
    except ImportError:
        return False

    data: dict[str, Any] = {"vel": vel_mm}
    for i, date in enumerate(dates):
        data[_field_name_for_date(date, output_format)] = ts_at[i]

    gdf = gpd.GeoDataFrame(data, geometry=gpd.points_from_xy(lons, lats), crs="EPSG:4326")
    try:
        from shapely import force_2d

        gdf["geometry"] = force_2d(gdf.geometry.values)
    except Exception:
        pass
    driver = "GPKG" if output_format == "gpkg" else "ESRI Shapefile"
    if os.path.exists(out_file):
        os.remove(out_file)
    try:
        gdf.to_file(out_file, driver=driver, layer=LAYER_NAME, engine="pyogrio")
    except Exception:
        gdf.to_file(out_file, driver=driver, layer=LAYER_NAME)
    return True


def _wgs84_srs():
    from osgeo import osr

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    return srs


def _remove_existing_vector(path: str, driver_name: str) -> None:
    from osgeo import ogr

    if not os.path.exists(path):
        return
    driver = ogr.GetDriverByName(driver_name)
    if driver is None:
        raise RuntimeError(f"GDAL 未提供驱动: {driver_name}")
    driver.DeleteDataSource(path)


def _create_vector_layer(out_dir: str, output_format: OutputFormat):
    from osgeo import ogr

    os.makedirs(out_dir, exist_ok=True)
    srs = _wgs84_srs()

    if output_format == "gpkg":
        path = output_path(out_dir, "gpkg")
        _remove_existing_vector(path, "GPKG")
        driver = ogr.GetDriverByName("GPKG")
        if driver is None:
            raise RuntimeError("GDAL 未提供 GPKG 驱动")
        ds = driver.CreateDataSource(path)
        if ds is None:
            raise RuntimeError(f"无法创建 GeoPackage: {path}")
        layer = ds.CreateLayer(LAYER_NAME, srs=srs, geom_type=ogr.wkbPoint)
        return ds, layer, path

    path = output_path(out_dir, "shp")
    _remove_existing_vector(path, "ESRI Shapefile")
    for ext in (".shx", ".dbf", ".prj", ".cpg", ".qpj"):
        sidecar = os.path.join(out_dir, "sbas_points" + ext)
        if os.path.exists(sidecar):
            os.remove(sidecar)
    driver = ogr.GetDriverByName("ESRI Shapefile")
    ds = driver.CreateDataSource(path)
    layer = ds.CreateLayer(LAYER_NAME, srs=srs, geom_type=ogr.wkbPoint)
    return ds, layer, path


def _write_with_ogr_batch(
    layer,
    lons: np.ndarray,
    lats: np.ndarray,
    vel_mm: np.ndarray,
    dates: List[str],
    ts_at: np.ndarray,
    output_format: OutputFormat,
) -> None:
    from osgeo import ogr

    layer.CreateField(ogr.FieldDefn("vel", ogr.OFTReal))
    field_names = [_field_name_for_date(d, output_format) for d in dates]
    for name in field_names:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTReal))

    feature_defn = layer.GetLayerDefn()
    n = int(lons.size)
    use_txn = hasattr(layer, "StartTransaction")

    for start in range(0, n, OGR_BATCH_SIZE):
        end = min(start + OGR_BATCH_SIZE, n)
        if use_txn:
            layer.StartTransaction()
        for j in range(start, end):
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(float(lons[j]), float(lats[j]))
            feat = ogr.Feature(feature_defn)
            feat.SetGeometry(point)
            feat.SetField("vel", float(vel_mm[j]))
            for i, name in enumerate(field_names):
                feat.SetField(name, float(ts_at[i, j]))
            layer.CreateFeature(feat)
        if use_txn:
            layer.CommitTransaction()


def _write_shapefile_prj(out_dir: str) -> None:
    srs = _wgs84_srs()
    srs.MorphToESRI()
    prj_path = os.path.join(out_dir, "sbas_points.prj")
    with open(prj_path, "w", encoding="utf-8") as f:
        f.write(srs.ExportToWkt())


def run_mintpy_to_shapefile(
    vel_path: str,
    h5_file_path: str,
    out_dir: str,
    pixel_span: int = 1,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    max_points: int = 0,
) -> Tuple[int, str]:
    """
    读取 velocity HDF5（或 GeoTIFF）与 timeseries HDF5，按 pixel_span 采样生成矢量点图层。
    过滤：NaN、0、|vel|>100 的点不输出。vel 与位移均乘以 1000 存为 mm。

    Args:
        pixel_span: 像素步长，越大越快、点越稀（建议大范围用 4～20）。
        max_points: 最多输出点数，0 表示不限制；超出时随机抽样。

    Returns:
        (有效点数量, 输出文件路径)
    """
    try:
        from osgeo import gdal
    except ImportError as e:
        raise ImportError("需要 GDAL (osgeo)：请安装 osgeo 或 conda install gdal") from e

    import h5py

    gdal.UseExceptions()
    fmt = _normalize_output_format(output_format)
    t0 = time.perf_counter()

    if not os.path.isfile(vel_path):
        raise FileNotFoundError(f"Velocity 文件不存在: {vel_path}")
    if not os.path.isfile(h5_file_path):
        raise FileNotFoundError(f"TimeSeries HDF5 不存在: {h5_file_path}")

    vel_array, gt, x_size, y_size = _load_velocity_raster(vel_path)
    logger.info("velocity 栅格 %sx%s，pixel_span=%s", x_size, y_size, pixel_span)

    ys, xs, vel_mm = _collect_valid_pixels(vel_array, pixel_span, max_points)
    n_valid = ys.size
    if n_valid == 0:
        raise ValueError("没有满足条件的有效点（检查速度场或增大 pixel_span）")

    with h5py.File(h5_file_path, "r") as f:
        ts_shape = f["timeseries"].shape
    if ts_shape[1:] != (y_size, x_size):
        raise ValueError(
            f"TimeSeries 与 velocity 尺寸不匹配: timeseries {ts_shape[1:]} vs velocity {y_size}x{x_size}"
        )

    ys, xs, vel_mm = _sort_pixels_for_h5(ys, xs, vel_mm, x_size)
    dates, ts_at = _read_timeseries_at_pixels(h5_file_path, ys, xs, x_size, pixel_span)
    lons, lats = _pixel_coords_to_lonlat(xs, ys, gt)
    logger.info(
        "有效点 %s，时相 %s；准备写入 %s（%.1fs）",
        n_valid,
        len(dates),
        fmt,
        time.perf_counter() - t0,
    )

    out_file = output_path(out_dir, fmt)
    if _write_with_geopandas(out_file, fmt, lons, lats, vel_mm, dates, ts_at):
        logger.info("已用 GeoPandas 写入 %s（%.1fs）", out_file, time.perf_counter() - t0)
        return n_valid, out_file

    ds, layer, out_file = _create_vector_layer(out_dir, fmt)
    _write_with_ogr_batch(layer, lons, lats, vel_mm, dates, ts_at, fmt)
    ds = None
    if fmt == "shp":
        _write_shapefile_prj(out_dir)

    logger.info("已用 OGR 批量写入 %s（%.1fs）", out_file, time.perf_counter() - t0)
    return n_valid, out_file
