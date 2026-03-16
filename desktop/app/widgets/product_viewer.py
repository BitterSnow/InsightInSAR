"""
通用产品查看器：显示栅格产品（GeoTIFF、VRT、ISCE .unw/.cor 等）。
Stack 流程「查看结果」与 MintPy 结果查看均通过此模块打开。
"""
from __future__ import annotations

import glob
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


def _read_raster_gdal(path: str) -> np.ndarray | None:
    """用 GDAL 读取栅格，返回 2D array。"""
    try:
        from osgeo import gdal
        ds = gdal.Open(path)
        if ds is None:
            return None
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray()
        ds = None
        return arr
    except Exception:
        return None


def _read_raster_rasterio(path: str) -> np.ndarray | None:
    """用 rasterio 读取栅格。"""
    try:
        import rasterio
        with rasterio.open(path) as src:
            return src.read(1)
    except Exception:
        return None


def _read_isce_image(path: str) -> np.ndarray | None:
    """读取 ISCE 格式（.unw/.cor 等 + .xml 中的 WIDTH/LENGTH）。"""
    path = path.replace("\\", "/")
    if not os.path.isfile(path):
        return None
    xml_path = path + ".xml"
    if not os.path.isfile(xml_path):
        return None
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        def get_prop(name: str) -> int:
            el = root.find(f".//property[@name='{name}']/value")
            return int(el.text or 0) if el is not None and el.text else 0
        width = get_prop("WIDTH") or get_prop("width")
        height = get_prop("LENGTH") or get_prop("length") or get_prop("FILE_LENGTH")
        if width <= 0 or height <= 0:
            return None
        arr = np.fromfile(path, dtype=np.float32)
        if arr.size != width * height:
            return None
        return arr.reshape((height, width))
    except Exception:
        return None


def _read_h5_2d(path: str) -> np.ndarray | None:
    """从 HDF5 中读取第一个 2D 或 3D 的首切片。"""
    try:
        import h5py
        with h5py.File(path, "r") as f:
            def first_2d(d):
                if d.ndim == 2:
                    return d[:]
                if d.ndim == 3:
                    return d[0, :, :]
                return None
            for key in ("velocity", "temporalCoherence", "coherence", "unwrapPhase"):
                if key in f:
                    return first_2d(f[key])
            for key in f.keys():
                d = f[key]
                if hasattr(d, "shape") and getattr(d, "ndim", 0) >= 2:
                    out = first_2d(d)
                    if out is not None:
                        return out
        return None
    except Exception:
        return None


def load_raster_array(path: str) -> np.ndarray | None:
    """从文件路径加载 2D 栅格数组，优先 GDAL/rasterio，其次 HDF5，再 ISCE xml。"""
    path = os.path.abspath(path.replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    arr = _read_raster_gdal(path)
    if arr is not None:
        return arr
    arr = _read_raster_rasterio(path)
    if arr is not None:
        return arr
    if path.endswith(".h5") or path.endswith(".hdf5"):
        arr = _read_h5_2d(path)
        if arr is not None:
            return arr
    if path.endswith(".unw") or path.endswith(".cor") or ".unw." in path or ".cor." in path:
        arr = _read_isce_image(path)
        if arr is not None:
            return arr
    return None


def get_stack_step_product_candidates(work_dir: str, step_id: str) -> list[str]:
    """根据 step_id 返回该步骤可能的产品路径列表（供选择或取第一个）。"""
    work_dir = os.path.abspath(work_dir.replace("/", os.sep))
    candidates = []
    base = step_id.split("_")[0] + "_" + step_id.split("_")[1] if "_" in step_id else step_id
    if "run_16" in step_id or "run_17" in step_id or "run_18" in step_id or "run_19" in step_id:
        igrams = os.path.join(work_dir, "merged", "interferograms")
        if os.path.isdir(igrams):
            for ext in ("*.cor", "*.unw", "filt_*.cor", "filt_*.unw"):
                candidates.extend(glob.glob(os.path.join(igrams, "*", ext)))
            candidates = sorted(candidates)[:20]
    if not candidates and os.path.isdir(work_dir):
        for rel in ("merged/interferograms", "merged/geom_reference", "reference"):
            d = os.path.join(work_dir, rel.replace("/", os.sep))
            if os.path.isdir(d):
                for ext in ("*.vrt", "*.tif", "*.unw", "*.cor"):
                    candidates.extend(glob.glob(os.path.join(d, "*", ext)) or glob.glob(os.path.join(d, ext)))
            if candidates:
                break
    return sorted(set(candidates))[:30]


def open_product_viewer(work_dir: str, step_id: str, parent=None) -> None:
    """打开产品查看对话框：根据 work_dir/step_id 解析候选产品，选第一个或弹选择框。"""
    candidates = get_stack_step_product_candidates(work_dir, step_id)
    if not candidates:
        QMessageBox.information(
            parent or None,
            "查看结果",
            "未找到本步产出文件（如 merged/interferograms 下的 .cor/.unw）。请先运行该步骤。",
        )
        return
    path = candidates[0]
    dlg = ProductViewerDialog(parent, initial_path=path, candidate_paths=candidates)
    dlg.exec()


class ProductViewerDialog(QDialog):
    """栅格产品查看对话框：显示 2D 数组（matplotlib 嵌入）。"""

    def __init__(self, parent=None, initial_path: str = "", candidate_paths: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("产品查看")
        self.setMinimumSize(640, 480)
        self.resize(800, 600)
        self._candidates = candidate_paths or []
        self._current_path = initial_path
        self._build_ui()
        if initial_path:
            self._load_path(initial_path)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("文件:"))
        self._path_combo = QComboBox()
        self._path_combo.setMinimumWidth(400)
        self._path_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self._candidates:
            for p in self._candidates:
                self._path_combo.addItem(os.path.basename(p), p)
            if self._current_path:
                idx = self._path_combo.findData(self._current_path)
                if idx >= 0:
                    self._path_combo.setCurrentIndex(idx)
        elif self._current_path:
            self._path_combo.addItem(os.path.basename(self._current_path), self._current_path)
        self._path_combo.currentIndexChanged.connect(self._on_combo_changed)
        row.addWidget(self._path_combo, 1)
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._on_browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)
        if _HAS_MPL:
            self._fig = Figure(figsize=(8, 6))
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self._canvas)
        else:
            layout.addWidget(QLabel("请安装 matplotlib 以显示栅格。"))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_combo_changed(self, index: int) -> None:
        if index < 0:
            return
        path = self._path_combo.currentData()
        if path:
            self._load_path(path)

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择栅格文件", "",
            "栅格 (*.tif *.tiff *.vrt *.unw *.cor *.h5);;所有 (*.*)",
        )
        if path:
            self._current_path = path
            self._path_combo.insertItem(0, os.path.basename(path), path)
            self._path_combo.setCurrentIndex(0)
            self._load_path(path)

    def _load_path(self, path: str) -> None:
        self._current_path = path
        arr = load_raster_array(path)
        if arr is None:
            if _HAS_MPL:
                self._fig.clear()
                ax = self._fig.add_subplot(111)
                ax.text(0.5, 0.5, "无法加载栅格\n（需 GDAL/rasterio 或 ISCE .unw+.xml）", ha="center", va="center")
                self._canvas.draw()
            return
        if not _HAS_MPL:
            return
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        vmin, vmax = np.nanpercentile(arr, [2, 98])
        if vmin >= vmax:
            vmin, vmax = np.nanmin(arr), np.nanmax(arr)
        im = ax.imshow(arr, cmap="gray", vmin=vmin, vmax=vmax, aspect="auto")
        self._fig.colorbar(im, ax=ax, label="值")
        ax.set_title(Path(path).name)
        self._canvas.draw()
