"""
将 MintPy 速度栅格与 TimeSeries HDF5 转为 Shapefile 点图层（vel + 每期位移）。
依赖：h5py, numpy, osgeo (gdal/ogr/osr)。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _xy2coor(x: float, y: float, gt: tuple) -> tuple:
    gx = gt[0] + x * gt[1] + y * gt[2]
    gy = gt[3] + x * gt[4] + y * gt[5]
    return gx, gy


def run_mintpy_to_shapefile(
    vel_tiff_path: str,
    h5_file_path: str,
    out_dir: str,
    pixel_span: int = 1,
) -> int:
    """
    读取 velocity GeoTIFF 与 timeseries HDF5，按 pixel_span 采样生成点 Shapefile。
    过滤：NaN、0、|vel|>100 的点不输出。vel 与位移均乘以 1000 存为 mm。

    Returns:
        写入的有效点数量。
    """
    try:
        from osgeo import gdal, ogr, osr
    except ImportError as e:
        raise ImportError("需要 GDAL (osgeo)：请安装 osgeo 或 conda install gdal") from e

    import h5py
    import numpy as np

    gdal.UseExceptions()

    if not os.path.isfile(vel_tiff_path):
        raise FileNotFoundError(f"Velocity GeoTIFF 不存在: {vel_tiff_path}")
    if not os.path.isfile(h5_file_path):
        raise FileNotFoundError(f"HDF5 文件不存在: {h5_file_path}")
    os.makedirs(out_dir, exist_ok=True)

    vel_ds = gdal.Open(vel_tiff_path)
    if vel_ds is None:
        raise RuntimeError(f"无法打开 GeoTIFF: {vel_tiff_path}")
    gt = vel_ds.GetGeoTransform()
    x_size = vel_ds.RasterXSize
    y_size = vel_ds.RasterYSize
    vel_array = vel_ds.GetRasterBand(1).ReadAsArray()
    vel_ds = None

    with h5py.File(h5_file_path, "r") as f:
        dates = [d.decode("utf-8") if isinstance(d, bytes) else str(d) for d in f["date"][:]]
        ts_data = f["timeseries"][:]

    if ts_data.shape[1:] != (y_size, x_size):
        raise ValueError(
            f"HDF5 与 velocity 尺寸不匹配: timeseries {ts_data.shape[1:]} vs raster {y_size}x{x_size}"
        )

    shp_path = os.path.join(out_dir, "sbas_points.shp")
    prj_path = os.path.join(out_dir, "sbas_points.prj")

    driver = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(shp_path):
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj"):
            p = os.path.join(out_dir, "sbas_points" + ext)
            if os.path.exists(p):
                os.remove(p)
    ds_shp = driver.CreateDataSource(shp_path)
    layer = ds_shp.CreateLayer("sbas_points", geom_type=ogr.wkbPoint)

    layer.CreateField(ogr.FieldDefn("vel", ogr.OFTReal))
    for date in dates:
        layer.CreateField(ogr.FieldDefn(f"D{date}", ogr.OFTReal))

    feature_defn = layer.GetLayerDefn()
    valid_count = 0

    for x in range(0, x_size, pixel_span):
        for y in range(0, y_size, pixel_span):
            v = vel_array[y, x]
            if np.isnan(v) or v == 0.0 or abs(v) > 100:
                continue

            point = ogr.Geometry(ogr.wkbPoint)
            gx, gy = _xy2coor(x, y, gt)
            point.AddPoint(gx, gy)

            feat = ogr.Feature(feature_defn)
            feat.SetGeometry(point)
            feat.SetField("vel", float(v * 1000))
            for i, date in enumerate(dates):
                disp = ts_data[i, y, x]
                val = float(disp * 1000) if not np.isnan(disp) else 0.0
                feat.SetField(f"D{date}", val)
            layer.CreateFeature(feat)
            feat = None
            valid_count += 1

    ds_shp = None

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.MorphToESRI()
    with open(prj_path, "w", encoding="utf-8") as f:
        f.write(srs.ExportToWkt())

    return valid_count
