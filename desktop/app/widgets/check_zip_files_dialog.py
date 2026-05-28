"""
工具：检查指定目录下所有 .zip 文件是否可正常打开，列出完整与损坏列表。
"""
from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)


class CheckZipFilesDialog(QDialog):
    """检查 ZIP 文件完整性：选择目录后执行，输出正常与错误文件列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检查 ZIP 文件")
        self.setMinimumSize(480, 400)
        self.resize(520, 460)
        self.setModal(False)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("扫描指定目录下所有包含 \"zip\" 的文件，尝试用 zipfile 打开，区分正常与损坏。")
        title.setWordWrap(True)
        title.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(title)

        grp = QGroupBox("路径")
        form = QFormLayout(grp)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("待检查的目录（如已下载的 Sentinel 数据目录）")
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.folder_edit, 1)
        btn = QPushButton("浏览…")
        btn.clicked.connect(lambda: self._browse_folder())
        h.addWidget(btn)
        form.addRow("目录:", w)
        layout.addWidget(grp)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(180)
        self.log_edit.setPlaceholderText("执行结果：正常 / 错误列表…")
        layout.addWidget(QLabel("结果"))
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.run_btn = QPushButton("检查")
        self.run_btn.clicked.connect(self._on_run)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择待检查目录")
        if path:
            self.folder_edit.setText(path)

    def _on_run(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "参数错误", "请选择目录。")
            return
        self.log_edit.clear()
        self.run_btn.setEnabled(False)
        try:
            from backend.tools.check_zip_files import run_check_zip_files
            correct, errors = run_check_zip_files(folder)
            self.log_edit.appendPlainText(f"正常: {len(correct)} 个")
            for name in correct:
                self.log_edit.appendPlainText("  " + name)
            self.log_edit.appendPlainText("")
            self.log_edit.appendPlainText(f"损坏/无法打开: {len(errors)} 个")
            for name in errors:
                self.log_edit.appendPlainText("  " + name)
            if errors:
                QMessageBox.warning(self, "检查完成", f"共 {len(correct) + len(errors)} 个 zip 文件，其中 {len(errors)} 个损坏或无法打开。")
            else:
                QMessageBox.information(self, "检查完成", f"共 {len(correct)} 个 zip 文件，均正常。")
        except Exception as e:
            logger.exception("检查 ZIP 失败")
            self.log_edit.appendPlainText("错误: " + str(e))
            QMessageBox.critical(self, "执行失败", str(e))
        finally:
            self.run_btn.setEnabled(True)
