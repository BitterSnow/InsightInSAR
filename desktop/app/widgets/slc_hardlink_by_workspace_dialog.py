"""
工具：按工作区 KML 与日期范围，从 SLC 目录筛选并硬链接到目标目录。
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
)
from PySide6.QtCore import Qt

from ..workspace_bbox import read_bbox_from_kml

logger = logging.getLogger(__name__)


class SlcHardlinkByWorkspaceDialog(QDialog):
    """SLC 按工作区硬链接：日期范围 + KML 工作区 + 硬链接目标目录。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SLC 按工作区硬链接")
        self.setMinimumSize(580, 480)
        self.resize(620, 520)
        self.setModal(False)
        self._build_ui()

    def _path_with_browse(
        self,
        line: QLineEdit,
        is_dir: bool,
        caption: str,
        filter_str: str | None = None,
    ) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(line, 1)
        btn = QPushButton("浏览…")

        def browse() -> None:
            if is_dir:
                p = QFileDialog.getExistingDirectory(self, caption)
            else:
                p, _ = QFileDialog.getOpenFileName(
                    self, caption, "", filter_str or "KML (*.kml);;所有 (*.*)"
                )
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
            "在 SLC 目录中按成像日期与工作区范围（KML 外接矩形）筛选产品："
            "以各 IW 条带 geolocation 真实覆盖与工作区相交为准（不用 manifest 整景外框）；"
            "单景可完全覆盖则全部硬链接；否则仅链接多 Frame 并集能盖住工作区的必要景。"
            "目录须为同一 relativeOrbitNumber（Path）。"
        )
        title.setWordWrap(True)
        title.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(title)

        grp = QGroupBox("参数")
        form = QFormLayout(grp)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.slc_dir_edit = QLineEdit()
        self.slc_dir_edit.setPlaceholderText("含 .zip 或 .SAFE 的 SLC 目录")
        form.addRow("SLC 目录:", self._path_with_browse(self.slc_dir_edit, True, "选择 SLC 目录"))

        date_row = QHBoxLayout()
        date_row.setContentsMargins(0, 0, 0, 0)
        self.start_date_edit = QLineEdit()
        self.start_date_edit.setPlaceholderText("YYYYMMDD")
        self.start_date_edit.setMaxLength(8)
        self.end_date_edit = QLineEdit()
        self.end_date_edit.setPlaceholderText("YYYYMMDD")
        self.end_date_edit.setMaxLength(8)
        date_row.addWidget(QLabel("起始"))
        date_row.addWidget(self.start_date_edit)
        date_row.addWidget(QLabel("结束"))
        date_row.addWidget(self.end_date_edit)
        date_row.addStretch()
        date_w = QWidget()
        date_w.setLayout(date_row)
        form.addRow("日期范围:", date_w)

        self.kml_edit = QLineEdit()
        self.kml_edit.setPlaceholderText("工作区 KML（经纬度）")
        form.addRow("工作区 KML:", self._path_with_browse(
            self.kml_edit, False, "选择工作区 KML", "KML (*.kml);;所有 (*.*)"
        ))

        self._kml_bbox_label = QLabel("")
        self._kml_bbox_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self._kml_bbox_label.setWordWrap(True)
        form.addRow("", self._kml_bbox_label)
        self.kml_edit.textChanged.connect(self._update_kml_preview)

        self.link_dir_edit = QLineEdit()
        self.link_dir_edit.setPlaceholderText("硬链接输出目录（与源文件同名，已存在则覆盖）")
        form.addRow("硬链接目录:", self._path_with_browse(self.link_dir_edit, True, "选择硬链接目标目录"))

        layout.addWidget(grp)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(180)
        self.log_edit.setPlaceholderText("执行日志…")
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.run_btn = QPushButton("执行硬链接")
        self.run_btn.clicked.connect(self._on_run)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _update_kml_preview(self) -> None:
        path = self.kml_edit.text().strip()
        if not path:
            self._kml_bbox_label.setText("")
            return
        if not os.path.isfile(path):
            self._kml_bbox_label.setText("KML 文件不存在")
            self._kml_bbox_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
            return
        try:
            n, s, w, e = read_bbox_from_kml(path)
            self._kml_bbox_label.setText(
                f"外接矩形：S={s:.4f}  N={n:.4f}  W={w:.4f}  E={e:.4f}"
            )
            self._kml_bbox_label.setStyleSheet("color: #22c55e; font-size: 12px;")
        except ValueError as exc:
            self._kml_bbox_label.setText(str(exc))
            self._kml_bbox_label.setStyleSheet("color: #ef4444; font-size: 12px;")

    def _on_run(self) -> None:
        slc_dir = self.slc_dir_edit.text().strip()
        start_d = self.start_date_edit.text().strip()
        end_d = self.end_date_edit.text().strip()
        kml_path = self.kml_edit.text().strip()
        link_dir = self.link_dir_edit.text().strip()

        if not all([slc_dir, start_d, end_d, kml_path, link_dir]):
            QMessageBox.warning(self, "参数错误", "请填写全部参数。")
            return
        if len(start_d) != 8 or len(end_d) != 8 or not start_d.isdigit() or not end_d.isdigit():
            QMessageBox.warning(self, "参数错误", "日期须为 8 位数字 YYYYMMDD。")
            return
        if start_d > end_d:
            QMessageBox.warning(self, "参数错误", "起始日期不能晚于结束日期。")
            return
        if not os.path.isfile(kml_path):
            QMessageBox.warning(self, "参数错误", "工作区 KML 文件不存在。")
            return

        try:
            n, s, w, e = read_bbox_from_kml(kml_path)
            workspace_snwe = (s, n, w, e)
        except ValueError as exc:
            QMessageBox.warning(self, "KML 错误", str(exc))
            return

        self.log_edit.clear()
        self.run_btn.setEnabled(False)
        try:
            from backend.tools.slc_hardlink_by_workspace import run_slc_hardlink_by_workspace

            result = run_slc_hardlink_by_workspace(
                slc_dir, start_d, end_d, workspace_snwe, link_dir
            )
            self.log_edit.appendPlainText(result.message)
            self.log_edit.appendPlainText(
                f"工作区外接矩形：S={s:.4f} N={n:.4f} W={w:.4f} E={e:.4f}"
            )
            if result.path_orbits:
                for orbit, names in sorted(result.path_orbits.items()):
                    self.log_edit.appendPlainText(
                        f"relativeOrbitNumber（Path）{orbit}：目录内 {len(names)} 景"
                    )
            if result.selected:
                self.log_edit.appendPlainText("")
                self.log_edit.appendPlainText("已选产品（相交 IW 条带见日志/后端）：")
                for p in result.selected:
                    iws = result.selected_swaths.get(p) or []
                    iw_txt = f"  IW{','.join(str(x) for x in iws)}" if iws else ""
                    self.log_edit.appendPlainText(f"  {os.path.basename(p)}{iw_txt}")
            if result.skipped_dates:
                self.log_edit.appendPlainText("")
                self.log_edit.appendPlainText("跳过的成像日：")
                for d, reason in sorted(result.skipped_dates.items()):
                    self.log_edit.appendPlainText(f"  {d}: {reason}")
            for err in result.link_errors:
                self.log_edit.appendPlainText("⚠ " + err)

            if not result.selected and not result.link_errors:
                QMessageBox.warning(self, "未链接", result.message)
            elif result.link_errors:
                QMessageBox.warning(
                    self,
                    "部分失败",
                    f"已链接 {result.linked_count} 个，部分失败见日志。",
                )
            else:
                QMessageBox.information(
                    self,
                    "完成",
                    f"已创建 {result.linked_count} 个硬链接到：\n{link_dir}",
                )
        except Exception as e:
            logger.exception("SLC 按工作区硬链接失败")
            self.log_edit.appendPlainText("错误: " + str(e))
            QMessageBox.critical(self, "执行失败", str(e))
        finally:
            self.run_btn.setEnabled(True)
