"""
工具：将 MintPy 速度栅格与 TimeSeries HDF5 转为 Shapefile 点图层。
"""
from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QFormLayout,
    QWidget,
    QSpinBox,
    QProgressBar,
)
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class MintPyToShapefileWorker(QThread):
    finished_with_result = Signal(object)  # dict with success, count or error_message

    def __init__(self, vel_tiff: str, h5_path: str, out_dir: str, pixel_span: int, parent=None):
        super().__init__(parent)
        self.vel_tiff = vel_tiff
        self.h5_path = h5_path
        self.out_dir = out_dir
        self.pixel_span = pixel_span

    def run(self) -> None:
        try:
            from backend.tools.mintpy_to_shapefile import run_mintpy_to_shapefile
            count = run_mintpy_to_shapefile(
                self.vel_tiff, self.h5_path, self.out_dir, self.pixel_span
            )
            self.finished_with_result.emit({"success": True, "count": count})
        except Exception as e:
            logger.exception("MintPy 转 Shapefile 失败")
            self.finished_with_result.emit({"success": False, "error_message": str(e)})


class MintPyToShapefileDialog(QDialog):
    """MintPy SBAS 转 Shapefile：指定工作目录、TimeSeries HDF5、Velocity GeoTIFF、采样间隔后执行。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MintPy 转 Shapefile")
        self.setMinimumSize(560, 440)
        self.resize(600, 500)
        self.setModal(False)
        self._worker: MintPyToShapefileWorker | None = None
        self._build_ui()

    def _path_with_browse(self, line: QLineEdit, is_dir: bool, caption: str, filter_str: str | None = None) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(line, 1)
        btn = QPushButton("浏览…")

        def browse() -> None:
            if is_dir:
                p = QFileDialog.getExistingDirectory(self, caption)
            else:
                p, _ = QFileDialog.getOpenFileName(self, caption, "", filter_str or "所有 (*.*)")
            if p:
                line.setText(p)

        btn.clicked.connect(browse)
        h.addWidget(btn)
        return w

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("从 MintPy 速度栅格与 TimeSeries HDF5 生成点 Shapefile（vel + 每期位移），输出 sbas_points.shp。")
        title.setWordWrap(True)
        title.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(title)

        grp = QGroupBox("路径与参数")
        form = QFormLayout(grp)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("输出目录（工作目录）")
        form.addRow("工作目录（输出）:", self._path_with_browse(self.work_dir_edit, True, "选择输出目录"))

        self.h5_edit = QLineEdit()
        self.h5_edit.setPlaceholderText("timeseries HDF5 文件")
        form.addRow("TimeSeries HDF5:", self._path_with_browse(self.h5_edit, False, "选择 HDF5 文件", "HDF5 (*.h5);;所有 (*.*)"))

        self.vel_edit = QLineEdit()
        self.vel_edit.setPlaceholderText("velocity GeoTIFF")
        form.addRow("Velocity GeoTIFF:", self._path_with_browse(self.vel_edit, False, "选择 GeoTIFF", "GeoTIFF (*.tif *.tiff);;所有 (*.*)"))

        self.span_spin = QSpinBox()
        self.span_spin.setRange(1, 100)
        self.span_spin.setValue(1)
        self.span_spin.setToolTip("点采样间隔（像素）")
        form.addRow("点采样间隔（像素）:", self.span_spin)

        layout.addWidget(grp)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(QLabel("进度"))
        layout.addWidget(self.progress_bar)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(100)
        self.log_edit.setPlaceholderText("执行日志…")
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.run_btn = QPushButton("开始转换")
        self.run_btn.clicked.connect(self._on_run)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.work_dir_edit.setEnabled(enabled)
        self.h5_edit.setEnabled(enabled)
        self.vel_edit.setEnabled(enabled)
        self.span_spin.setEnabled(enabled)
        self.run_btn.setEnabled(enabled)

    def _on_run(self) -> None:
        work_dir = self.work_dir_edit.text().strip()
        h5_path = self.h5_edit.text().strip()
        vel_path = self.vel_edit.text().strip()
        span = self.span_spin.value()
        if not work_dir or not h5_path or not vel_path:
            QMessageBox.warning(self, "参数错误", "请填写工作目录、HDF5 与 GeoTIFF 路径。")
            return
        out_shp = os.path.join(work_dir, "sbas_points.shp")
        if os.path.exists(out_shp):
            reply = QMessageBox.question(
                self,
                "确认覆盖",
                "输出目录中已存在 sbas_points.shp，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.log_edit.clear()
        self.log_edit.appendPlainText("正在从 HDF5 生成 Shapefile…")
        self._set_form_enabled(False)
        self._worker = MintPyToShapefileWorker(vel_path, h5_path, work_dir, span, self)
        self._worker.finished_with_result.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, result: dict) -> None:
        self._set_form_enabled(True)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        if result.get("success"):
            count = result.get("count", 0)
            self.log_edit.appendPlainText(f"成功生成 {count} 个点。输出文件：sbas_points.shp")
            QMessageBox.information(self, "完成", f"Shapefile 已生成，共 {count} 个有效点。")
        else:
            err = result.get("error_message", "未知错误")
            self.log_edit.appendPlainText("错误: " + err)
            QMessageBox.critical(self, "转换失败", err)
