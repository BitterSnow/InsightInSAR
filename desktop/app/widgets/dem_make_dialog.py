"""
DEM 制作对话框：根据工作区与 Swath 计算范围，缺瓦片从 ESA 下载，在 WSL 内调用 dem.py 拼接。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QFormLayout,
    QFileDialog,
    QMessageBox,
    QSpinBox,
    QCheckBox,
    QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


def _sanitize_path(path: str) -> str:
    """清理路径字符串，移除可能导致 embedded null character 错误的空字节和其他非法字符。"""
    if not path:
        return path
    # 移除空字节（\x00）
    sanitized = path.replace("\x00", "")
    # 移除其他可能导致问题的控制字符
    sanitized = "".join(c for c in sanitized if c >= " " or c in "\t\r\n")
    return sanitized.strip()


class DemStitchWorker(QThread):
    """后台：补充 SRTM 瓦片（必要时从 ESA 下载）+ 在 WSL 内运行 dem.py -a stitch -l -s 1，结果复制到输出目录。"""
    log_line = Signal(str)
    finished_with_result = Signal(dict)

    def __init__(
        self,
        bbox_south: int,
        bbox_north: int,
        bbox_west: int,
        bbox_east: int,
        dem_raw_dir: str,
        output_dir: str,
        output_name: Optional[str],
        parent=None,
        correct_egm96: bool = True,
    ):
        super().__init__(parent)
        self._bbox_south = bbox_south
        self._bbox_north = bbox_north
        self._bbox_west = bbox_west
        self._bbox_east = bbox_east
        self._dem_raw_dir = dem_raw_dir
        self._output_dir = output_dir
        self._output_name = output_name or ""
        self._correct_egm96 = correct_egm96

    def run(self) -> None:
        try:
            from backend.services.dem_processing_service import run_dem_stitch_wsl

            def on_line(line: str) -> None:
                self.log_line.emit(line)

            result = run_dem_stitch_wsl(
                bbox_south=self._bbox_south,
                bbox_north=self._bbox_north,
                bbox_west=self._bbox_west,
                bbox_east=self._bbox_east,
                dem_raw_dir=self._dem_raw_dir,
                output_dir=self._output_dir,
                output_name=self._output_name.strip() or None,
                correct_egm96=self._correct_egm96,
                timeout=3600,
                stream_callback=on_line,
            )
            if not result.get("success"):
                err = result.get("error_message") or "未知错误"
                logger.error("DEM 制作失败: %s", err)
            self.finished_with_result.emit(result)
        except Exception as e:
            logger.exception("DEM 制作异常: %s", e)
            self.finished_with_result.emit({
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "error_message": str(e),
                "output_path": None,
            })


class DemMakeDialog(QDialog):
    """DEM 制作：DEM 原始数据目录、输出目录、范围（可据工作区+Swath 自动更新）、输出文件名。EGM96→WGS84 校正采用默认开启。"""
    # 制作成功并得到输出路径时发出，便于数据导入界面同步并保存到工程
    dem_succeeded = Signal(str)

    def __init__(
        self,
        parent=None,
        extent_south: Optional[float] = None,
        extent_north: Optional[float] = None,
        extent_west: Optional[float] = None,
        extent_east: Optional[float] = None,
        safe_path: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("DEM 制作")
        self.setMinimumSize(540, 460)
        self.setModal(False)
        self._worker: Optional[DemStitchWorker] = None
        self._extent = (extent_south, extent_north, extent_west, extent_east)
        self._safe_path = (safe_path or "").strip()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("DEM 制作")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel(
            "DEM 原始数据存放目录；缺瓦片时从 ESA 下载，再在 WSL（Ubuntu）内用 dem.py 拼接。"
            "默认启用 EGM96→WGS84 椭球高改正（dem.py -c）。"
            "网络盘（如 N:）若 WSL 未自动挂载，程序会尝试 drvfs 补挂。"
        )
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        grp = QGroupBox("路径与范围")
        form = QFormLayout(grp)
        form.setSpacing(8)

        self.raw_dir_edit = QLineEdit()
        self.raw_dir_edit.setPlaceholderText("如 N:\\NASASRTM1（WSL 路径 /mnt/n/...）")
        browse_raw = QPushButton("浏览…")
        browse_raw.clicked.connect(self._on_browse_raw_dir)
        raw_row = QWidget()
        raw_h = QHBoxLayout(raw_row)
        raw_h.setContentsMargins(0, 0, 0, 0)
        raw_h.addWidget(self.raw_dir_edit, 1)
        raw_h.addWidget(browse_raw)
        form.addRow("DEM 原始数据目录:", raw_row)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("拼接后的 DEM 输出到此目录")
        browse_out = QPushButton("浏览…")
        browse_out.clicked.connect(self._on_browse_output_dir)
        out_row = QWidget()
        out_h = QHBoxLayout(out_row)
        out_h.setContentsMargins(0, 0, 0, 0)
        out_h.addWidget(self.output_dir_edit, 1)
        out_h.addWidget(browse_out)
        form.addRow("输出目录:", out_row)

        self.bbox_s = QSpinBox()
        self.bbox_s.setRange(-90, 90)
        self.bbox_s.setValue(int(self._extent[0]) if self._extent[0] is not None else 30)
        self.bbox_s.setToolTip("南纬（整数）")
        self.bbox_n = QSpinBox()
        self.bbox_n.setRange(-90, 90)
        self.bbox_n.setValue(int(self._extent[1]) if self._extent[1] is not None else 33)
        self.bbox_n.setToolTip("北纬（整数）")
        self.bbox_w = QSpinBox()
        self.bbox_w.setRange(-180, 180)
        self.bbox_w.setValue(int(self._extent[2]) if self._extent[2] is not None else -115)
        self.bbox_w.setToolTip("西经（整数）")
        self.bbox_e = QSpinBox()
        self.bbox_e.setRange(-180, 180)
        self.bbox_e.setValue(int(self._extent[3]) if self._extent[3] is not None else -112)
        self.bbox_e.setToolTip("东经（整数）")
        bbox_row = QWidget()
        bbox_h = QHBoxLayout(bbox_row)
        bbox_h.setContentsMargins(0, 0, 0, 0)
        bbox_h.addWidget(QLabel("南:"))
        bbox_h.addWidget(self.bbox_s)
        bbox_h.addWidget(QLabel("北:"))
        bbox_h.addWidget(self.bbox_n)
        bbox_h.addWidget(QLabel("西:"))
        bbox_h.addWidget(self.bbox_w)
        bbox_h.addWidget(QLabel("东:"))
        bbox_h.addWidget(self.bbox_e)
        self.update_bbox_btn = QPushButton("根据工作区与 Swath 更新范围")
        self.update_bbox_btn.setToolTip("根据定义的工作区与 SAFE 数据计算需使用的 Swath，再按 Swath 范围计算 DEM 范围并填入上方")
        self.update_bbox_btn.clicked.connect(self._on_update_bbox_from_workspace)
        bbox_h.addWidget(self.update_bbox_btn)
        bbox_h.addStretch()
        form.addRow("处理范围 (S N W E):", bbox_row)

        self.out_name_edit = QLineEdit()
        self.out_name_edit.setPlaceholderText("可选，不填则自动命名")
        form.addRow("输出文件名:", self.out_name_edit)

        layout.addWidget(grp)

        layout.addWidget(QLabel("执行日志"))
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(160)
        self.log_edit.setPlaceholderText("点击「开始制作」后先检查/下载瓦片，再在 WSL 内运行 dem.py…")
        layout.addWidget(self.log_edit)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.run_btn = QPushButton("开始制作")
        self.run_btn.clicked.connect(self._on_run)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _on_browse_raw_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 DEM 原始数据所在文件夹")
        if path:
            self.raw_dir_edit.setText(path)

    def _on_browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 DEM 输出目录")
        if path:
            self.output_dir_edit.setText(path)

    @Slot()
    def _on_update_bbox_from_workspace(self) -> None:
        """根据工作区与 SAFE 计算 Swath 并得到 DEM 范围，更新四个 spinbox。"""
        s = self._extent[0]
        n = self._extent[1]
        w = self._extent[2]
        e = self._extent[3]
        if s is None or n is None or w is None or e is None:
            QMessageBox.warning(
                self,
                "工作区未定义",
                "请先在 Stack 流程配置或本对话框内填写「处理范围」（N/S/W/E）。",
            )
            return
        safe = self._safe_path or None
        try:
            from backend.services.dem_processing_service import get_dem_bbox_from_workspace_safe
            dem_s, dem_n, dem_w, dem_e = get_dem_bbox_from_workspace_safe(
                (s, n, w, e),
                safe_path=safe,
            )
            self.bbox_s.setValue(dem_s)
            self.bbox_n.setValue(dem_n)
            self.bbox_w.setValue(dem_w)
            self.bbox_e.setValue(dem_e)
            QMessageBox.information(
                self,
                "范围已更新",
                f"根据工作区与 Swath 计算得到 DEM 范围：南 {dem_s} 北 {dem_n} 西 {dem_w} 东 {dem_e}。",
            )
        except Exception as ex:
            logger.exception("DEM 根据工作区更新范围失败: %s", ex)
            QMessageBox.warning(self, "更新范围失败", str(ex))

    @Slot()
    def _on_run(self) -> None:
        s, n, w, e = self.bbox_s.value(), self.bbox_n.value(), self.bbox_w.value(), self.bbox_e.value()
        if s >= n:
            QMessageBox.warning(self, "范围错误", "南界须小于北界。")
            return
        if w >= e:
            QMessageBox.warning(self, "范围错误", "西界须小于东界。")
            return
        raw_dir = _sanitize_path(self.raw_dir_edit.text().strip())
        if not raw_dir:
            QMessageBox.warning(self, "DEM 原始数据目录", "请选择 DEM 原始数据所在文件夹。")
            return
        # 检查路径是否包含被清理的非法字符，若有则提示用户
        original_raw = self.raw_dir_edit.text().strip()
        if original_raw != raw_dir:
            logger.warning("DEM 原始数据目录路径包含非法字符，已自动清理: %r -> %r", original_raw, raw_dir)
            self.raw_dir_edit.setText(raw_dir)
        if not os.path.isdir(raw_dir):
            QMessageBox.warning(self, "DEM 原始数据目录", f"所选路径不是有效目录：{raw_dir}\n请先创建或选择有效目录。")
            return
        output_dir = _sanitize_path(self.output_dir_edit.text().strip())
        if not output_dir:
            QMessageBox.warning(self, "输出目录", "请选择 DEM 输出目录。")
            return
        original_out = self.output_dir_edit.text().strip()
        if original_out != output_dir:
            logger.warning("输出目录路径包含非法字符，已自动清理: %r -> %r", original_out, output_dir)
            self.output_dir_edit.setText(output_dir)
        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "输出目录", f"所选路径不是有效目录：{output_dir}\n请先创建或选择有效目录。")
            return
        try:
            from backend.services import wsl_runner

            if wsl_runner.use_wsl():
                _, raw_err = wsl_runner.resolve_windows_path_to_wsl(raw_dir)
                if raw_err:
                    QMessageBox.warning(self, "WSL 无法访问目录", raw_err)
                    return
                _, out_err = wsl_runner.resolve_windows_path_to_wsl(output_dir)
                if out_err:
                    QMessageBox.warning(self, "WSL 无法访问输出目录", out_err)
                    return
        except Exception as ex:
            logger.warning("WSL 路径预检跳过: %s", ex)
        out_name = _sanitize_path(self.out_name_edit.text().strip()) or None
        self.log_edit.clear()
        self.progress_bar.setVisible(True)
        self.run_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self._worker = DemStitchWorker(
            bbox_south=s,
            bbox_north=n,
            bbox_west=w,
            bbox_east=e,
            dem_raw_dir=raw_dir,
            output_dir=output_dir,
            output_name=out_name,
            parent=self,
            correct_egm96=True,
        )
        self._worker.log_line.connect(self._on_log_line)
        self._worker.finished_with_result.connect(self._on_finished)
        self._worker.start()

    def _on_log_line(self, line: str) -> None:
        self.log_edit.appendPlainText(line.rstrip())

    def _on_finished(self, result: dict) -> None:
        self._worker = None
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        if result.get("success"):
            out_path = result.get("output_path")
            datum = result.get("vertical_datum") or ""
            conv = result.get("conversion_applied")
            val = result.get("validation_message") or ""
            msg = "DEM 制作已完成。"
            if out_path:
                msg += f"\n输出: {out_path}"
                self.dem_succeeded.emit(out_path)
            else:
                msg += f"\n请到输出目录查看: {self.output_dir_edit.text().strip()}"
            if datum:
                msg += f"\n垂直基准: {datum}"
            if conv is not None:
                msg += f"\nEGM96→WGS84 转换: {'是' if conv else '否'}"
            if val:
                self.log_edit.appendPlainText(f"完整性校验: {val}")
            if result.get("xml_path"):
                self.log_edit.appendPlainText(f"XML: {result.get('xml_path')}")
            if result.get("vrt_path"):
                self.log_edit.appendPlainText(f"VRT: {result.get('vrt_path')}")
            logger.info(
                "DEM 制作完成: output_path=%s vertical_datum=%s conversion_applied=%s",
                out_path, datum, conv,
            )
            QMessageBox.information(self, "完成", msg)
        else:
            err = result.get("error_message") or result.get("stdout") or "未知错误"
            stderr = result.get("stderr", "")
            returncode = result.get("returncode", -1)
            logger.error(
                "DEM 制作失败: returncode=%s, error=%s, stderr=%s",
                returncode, err, stderr,
            )
            QMessageBox.warning(self, "DEM 制作失败", err)
