"""
MintPy 快速设置对话框：仅需选择工作目录即可进入时间序列分析。

用于"打开时间序列分析"快速入口，自动检测并预填目录，自动后台初始化。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFrame,
    QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


class MintPyInitWorker(QThread):
    """后台初始化 MintPy 工作目录。"""
    finished_with_result = Signal(dict)

    def __init__(
        self,
        work_dir: str,
        stack_work_dir: str | None,
        stack_product_dir: str | None,
        parent=None,
    ):
        super().__init__(parent)
        self._work_dir = work_dir
        self._stack_work_dir = stack_work_dir
        self._stack_product_dir = stack_product_dir

    def run(self) -> None:
        try:
            from backend.services.mintpy_processing_service import init_mintpy_workdir

            result = init_mintpy_workdir(
                self._work_dir,
                stack_work_dir=self._stack_work_dir,
                stack_product_dir=self._stack_product_dir,
            )
            self.finished_with_result.emit(result)
        except Exception as e:
            logging.exception("MintPy 初始化异常: work_dir=%s", self._work_dir)
            self.finished_with_result.emit({"success": False, "error_message": str(e)})


class MintPyQuickSetupDialog(QDialog):
    """
    精简的时间序列设置对话框。

    只有一个目录选择字段，自动预填，确认后自动初始化并 emit setup_complete。
    """

    setup_complete = Signal(str)  # work_dir

    def __init__(
        self,
        parent=None,
        default_work_dir: str | None = None,
        stack_work_dir: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("选择时间序列工作目录")
        self.setMinimumSize(420, 140)
        self.resize(480, 160)
        self.setModal(True)

        self._stack_work_dir = (stack_work_dir or "").strip()
        self._default_work_dir = (default_work_dir or "").strip()
        self._worker: MintPyInitWorker | None = None

        self._build_ui()
        self._prefill()

    def _prefill(self) -> None:
        # 优先使用传入的默认工作目录
        if self._default_work_dir:
            self.work_dir_edit.setText(self._default_work_dir)
            return
        # 否则从 stack_work_dir 推导
        if self._stack_work_dir and os.path.isdir(self._stack_work_dir):
            mintpy_sub = os.path.join(self._stack_work_dir, "mintpy")
            self.work_dir_edit.setText(mintpy_sub)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 说明文字
        hint = QLabel("选择或输入 MintPy 工作目录，系统将自动初始化并打开处理界面。")
        hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 目录选择行
        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(8)

        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("MintPy 工作目录（如 …/stack/mintpy）")
        self.work_dir_edit.setMinimumWidth(300)

        browse_btn = QPushButton("浏览…")
        browse_btn.setFixedWidth(64)
        browse_btn.clicked.connect(self._on_browse)

        dir_layout.addWidget(self.work_dir_edit, 1)
        dir_layout.addWidget(browse_btn)
        layout.addWidget(dir_row)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self._on_ok)
        self.ok_btn.setDefault(True)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 MintPy 工作目录")
        if path:
            self.work_dir_edit.setText(path)

    def _on_ok(self) -> None:
        work_dir = self.work_dir_edit.text().strip()
        if not work_dir:
            QMessageBox.warning(self, "参数错误", "请填写工作目录。")
            return

        # 禁用按钮，显示处理中
        self.ok_btn.setEnabled(False)
        self.ok_btn.setText("初始化中…")
        self.work_dir_edit.setEnabled(False)

        # 推导 stack_product_dir
        stack_product_dir = self._stack_work_dir or None
        if not stack_product_dir and os.path.dirname(work_dir):
            parent = os.path.dirname(work_dir)
            if os.path.basename(work_dir).lower() == "mintpy":
                stack_product_dir = parent

        # 启动后台初始化
        self._worker = MintPyInitWorker(
            work_dir,
            stack_work_dir=self._stack_work_dir or None,
            stack_product_dir=stack_product_dir,
            parent=self,
        )
        self._worker.finished_with_result.connect(self._on_init_finished)
        self._worker.start()

    def _on_init_finished(self, result: dict) -> None:
        self.ok_btn.setEnabled(True)
        self.ok_btn.setText("确定")
        self.work_dir_edit.setEnabled(True)

        if self._worker:
            self._worker.deleteLater()
            self._worker = None

        if result.get("success"):
            work_dir = result.get("work_dir", self.work_dir_edit.text().strip())
            self.setup_complete.emit(work_dir)
            self.accept()
        else:
            err = result.get("error_message", "未知错误")
            QMessageBox.warning(self, "初始化失败", err)

    def get_work_dir(self) -> str | None:
        return self.work_dir_edit.text().strip() or None