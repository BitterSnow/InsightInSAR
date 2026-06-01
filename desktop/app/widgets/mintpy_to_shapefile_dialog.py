"""
工具：将 MintPy 速度栅格与 TimeSeries HDF5 转为矢量点图层（GeoPackage / Shapefile）。
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
    QComboBox,
)
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

OUTPUT_GPKG = "gpkg"
OUTPUT_SHP = "shp"


class MintPyToShapefileWorker(QThread):
    finished_with_result = Signal(object)  # dict with success, count, output_path or error_message

    def __init__(
        self,
        vel_h5: str,
        h5_path: str,
        out_dir: str,
        pixel_span: int,
        output_format: str,
        max_points: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.vel_h5 = vel_h5
        self.h5_path = h5_path
        self.out_dir = out_dir
        self.pixel_span = pixel_span
        self.output_format = output_format
        self.max_points = max_points

    def run(self) -> None:
        try:
            from backend.services.mintpy_vector_export_service import run_mintpy_vector_export

            result = run_mintpy_vector_export(
                self.vel_h5,
                self.h5_path,
                self.out_dir,
                pixel_span=self.pixel_span,
                output_format=self.output_format,
                max_points=self.max_points,
            )
            if result.get("success"):
                self.finished_with_result.emit(result)
            else:
                self.finished_with_result.emit(
                    {"success": False, "error_message": result.get("error_message") or "转换失败"}
                )
        except Exception as e:
            logger.exception("MintPy 转矢量失败")
            self.finished_with_result.emit({"success": False, "error_message": str(e)})


class MintPyToShapefileDialog(QDialog):
    """MintPy SBAS 转矢量：Velocity / TimeSeries HDF5 → GeoPackage 或 Shapefile。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MintPy 转矢量")
        self.setMinimumSize(560, 460)
        self.resize(600, 520)
        self.setModal(False)
        self._worker: MintPyToShapefileWorker | None = None
        self._build_ui()

    def _selected_output_format(self) -> str:
        return OUTPUT_GPKG if self.format_combo.currentIndex() == 0 else OUTPUT_SHP

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

        title = QLabel(
            "从 MintPy velocity / TimeSeries HDF5 生成点矢量（vel + 每期位移）。"
            "大范围建议：采样间隔 4～10、或限制最大点数；默认 GeoPackage。"
        )
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
        self.vel_edit.setPlaceholderText("velocity HDF5，如 geo_velocity.h5")
        form.addRow(
            "Velocity HDF5:",
            self._path_with_browse(
                self.vel_edit, False, "选择 Velocity HDF5", "HDF5 (*.h5);;所有 (*.*)"
            ),
        )

        self.format_combo = QComboBox()
        self.format_combo.addItem("GeoPackage (.gpkg)", OUTPUT_GPKG)
        self.format_combo.addItem("Shapefile (.shp)", OUTPUT_SHP)
        self.format_combo.setToolTip("矢量输出格式，默认 GeoPackage")
        form.addRow("输出格式:", self.format_combo)

        self.span_spin = QSpinBox()
        self.span_spin.setRange(1, 100)
        self.span_spin.setValue(4)
        self.span_spin.setToolTip(
            "每隔 N 个像素取 1 个点。1=最密最慢；大范围建议 4～20，速度可提升数倍～数十倍。"
        )
        form.addRow("点采样间隔（像素）:", self.span_spin)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(0, 50_000_000)
        self.max_points_spin.setSingleStep(10000)
        self.max_points_spin.setValue(0)
        self.max_points_spin.setToolTip("0 表示不限制；例如 200000 可在保留形态的同时显著加速。")
        form.addRow("最大输出点数:", self.max_points_spin)

        layout.addWidget(grp)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
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
        self.format_combo.setEnabled(enabled)
        self.span_spin.setEnabled(enabled)
        self.max_points_spin.setEnabled(enabled)
        self.run_btn.setEnabled(enabled)

    def _on_run(self) -> None:
        from backend.tools.mintpy_to_shapefile import output_path

        work_dir = self.work_dir_edit.text().strip()
        h5_path = self.h5_edit.text().strip()
        vel_path = self.vel_edit.text().strip()
        span = self.span_spin.value()
        max_pts = self.max_points_spin.value()
        out_fmt = self._selected_output_format()
        if not work_dir or not h5_path or not vel_path:
            QMessageBox.warning(self, "参数错误", "请填写工作目录、TimeSeries HDF5 与 Velocity HDF5 路径。")
            return
        try:
            from backend.services import wsl_runner

            if wsl_runner.use_wsl():
                for label, p in (
                    ("Velocity HDF5", vel_path),
                    ("TimeSeries HDF5", h5_path),
                ):
                    if not os.path.isfile(p):
                        QMessageBox.warning(self, "文件不存在", f"{label} 不存在:\n{p}")
                        return
                _, err = wsl_runner.resolve_windows_path_to_wsl(work_dir)
                if err:
                    os.makedirs(work_dir, exist_ok=True)
                    _, err = wsl_runner.resolve_windows_path_to_wsl(work_dir)
                if err:
                    QMessageBox.warning(self, "WSL 无法访问目录", err)
                    return
        except Exception as ex:
            logger.warning("WSL 路径预检跳过: %s", ex)
        out_file = output_path(work_dir, out_fmt)
        if os.path.exists(out_file):
            reply = QMessageBox.question(
                self,
                "确认覆盖",
                f"输出目录中已存在 {os.path.basename(out_file)}，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        fmt_label = "GeoPackage" if out_fmt == OUTPUT_GPKG else "Shapefile"
        self.log_edit.clear()
        self.log_edit.appendPlainText(f"正在生成 {fmt_label}…")
        self._set_form_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._worker = MintPyToShapefileWorker(
            vel_path, h5_path, work_dir, span, out_fmt, max_pts, self
        )
        self._worker.finished_with_result.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, result: dict) -> None:
        self._set_form_enabled(True)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if result.get("success") else 0)
        self.progress_bar.setVisible(False)
        if result.get("success"):
            count = result.get("count", 0)
            out_file = result.get("output_path", "")
            name = os.path.basename(out_file) if out_file else "输出文件"
            self.log_edit.appendPlainText(f"成功生成 {count} 个点。输出：{out_file or name}")
            QMessageBox.information(self, "完成", f"矢量已生成，共 {count} 个有效点。\n{name}")
        else:
            err = result.get("error_message", "未知错误")
            self.log_edit.appendPlainText("错误: " + err)
            QMessageBox.critical(self, "转换失败", err)
