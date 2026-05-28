"""
工具：从包含下载链接的 Python 文件中提取链接，与本地目录对比，
已存在的创建硬链接到目标目录，未下载的写入待下载列表。
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

logger = logging.getLogger(__name__)


class NewDataToDownloadDialog(QDialog):
    """新数据待下载列表：填写链接文件、本地目录、输出文件、硬链接目标目录后执行。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新数据待下载列表")
        self.setMinimumSize(560, 420)
        self.resize(600, 480)
        self.setModal(False)
        self._build_ui()

    def _path_with_browse(
        self,
        line: QLineEdit,
        is_dir: bool,
        caption: str,
        is_save: bool = False,
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
            elif is_save:
                p, _ = QFileDialog.getSaveFileName(self, caption, "", filter_str or "文本 (*.txt);;所有 (*.*)")
            else:
                p, _ = QFileDialog.getOpenFileName(self, caption, "", filter_str or "Python (*.py);;所有 (*.*)")
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
            "从包含 self.files = [ \"https://...zip\", ... ] 的 Python 文件提取下载链接，"
            "与本地目录对比：已存在则创建硬链接，未下载则写入待下载列表。"
        )
        title.setWordWrap(True)
        title.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(title)

        grp = QGroupBox("路径")
        form = QFormLayout(grp)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.link_file_edit = QLineEdit()
        self.link_file_edit.setPlaceholderText("包含下载链接的 .py 文件")
        form.addRow("链接文件 (.py):", self._path_with_browse(self.link_file_edit, False, "选择包含 self.files 的 Python 文件", False, "Python (*.py);;所有 (*.*)"))

        self.local_folder_edit = QLineEdit()
        self.local_folder_edit.setPlaceholderText("本地已下载数据存放目录")
        form.addRow("本地数据目录:", self._path_with_browse(self.local_folder_edit, True, "选择本地已下载数据目录"))

        self.symlink_folder_edit = QLineEdit()
        self.symlink_folder_edit.setPlaceholderText("硬链接目标目录")
        form.addRow("硬链接目标目录:", self._path_with_browse(self.symlink_folder_edit, True, "选择硬链接目标目录"))
        self.symlink_folder_edit.textChanged.connect(self._update_output_file_path)

        self.output_file_edit = QLineEdit()
        self.output_file_edit.setPlaceholderText("根据硬链接目标目录自动生成")
        self.output_file_edit.setReadOnly(True)
        self.output_file_edit.setStyleSheet("color: #94a3b8;")
        form.addRow("待下载列表输出:", self.output_file_edit)

        layout.addWidget(grp)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(120)
        self.log_edit.setPlaceholderText("执行日志…")
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.run_btn = QPushButton("执行")
        self.run_btn.clicked.connect(self._on_run)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _update_output_file_path(self) -> None:
        symlink = self.symlink_folder_edit.text().strip()
        if symlink:
            self.output_file_edit.setText(os.path.join(symlink, "needToDownload.txt"))
        else:
            self.output_file_edit.clear()

    def _on_run(self) -> None:
        link_file = self.link_file_edit.text().strip()
        local_folder = self.local_folder_edit.text().strip()
        symlink_folder = self.symlink_folder_edit.text().strip()
        output_file = self.output_file_edit.text().strip() or (os.path.join(symlink_folder, "needToDownload.txt") if symlink_folder else "")
        if not link_file or not local_folder or not symlink_folder or not output_file:
            QMessageBox.warning(self, "参数错误", "请填写链接文件、本地数据目录与硬链接目标目录。")
            return
        self.log_edit.clear()
        self.run_btn.setEnabled(False)
        try:
            from backend.tools.new_data_to_download import run_new_data_to_download
            total, existing, link_errors = run_new_data_to_download(
                link_file, local_folder, output_file, symlink_folder
            )
            self.log_edit.appendPlainText("任务完成。")
            self.log_edit.appendPlainText(f"总共链接数: {total}")
            self.log_edit.appendPlainText(f"已存在并创建硬链接: {existing} 个 -> 存放于 '{symlink_folder}'")
            self.log_edit.appendPlainText(f"尚未下载: {total - existing} 个 -> 已写入 '{output_file}'")
            for msg in link_errors:
                self.log_edit.appendPlainText("⚠ " + msg)
            if link_errors:
                QMessageBox.warning(self, "部分失败", "部分硬链接创建失败，详见日志。")
            else:
                QMessageBox.information(self, "完成", f"已处理 {total} 个链接，已存在 {existing} 个已建硬链接，待下载列表已写入。")
        except Exception as e:
            logger.exception("新数据待下载列表执行失败")
            self.log_edit.appendPlainText("错误: " + str(e))
            QMessageBox.critical(self, "执行失败", str(e))
        finally:
            self.run_btn.setEnabled(True)
