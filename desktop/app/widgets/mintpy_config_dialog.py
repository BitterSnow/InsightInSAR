"""
时间序列配置对话框：填写 MintPy 工作目录、可选 Stack 产品目录，执行「初始化」生成 smallbaselineApp.cfg。
成功后可选打开流程界面。从 Stack 进入时预填 stack_work_dir/mintpy。
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
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QFrame,
    QWidget,
    QFormLayout,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


def _path_field_with_browse(line: QLineEdit, caption: str) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    h.addWidget(line, 1)
    btn = QPushButton("浏览…")
    btn.clicked.connect(lambda: _browse_dir(line, caption))
    h.addWidget(btn)
    return w


def _browse_dir(edit: QLineEdit, caption: str) -> None:
    path = QFileDialog.getExistingDirectory(None, caption)
    if path:
        edit.setText(path)


class MintPyInitWorker(QThread):
    progress_updated = Signal(float, str)
    finished_with_result = Signal(dict)

    def __init__(self, work_dir: str, stack_work_dir: str | None, stack_product_dir: str | None, parent=None):
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
            self.progress_updated.emit(0.0, f"错误: {e}")
            self.finished_with_result.emit({"success": False, "error_message": str(e)})


class MintPyConfigDialog(QDialog):
    """时间序列配置：工作目录、Stack 产品目录（可选）；初始化后打开流程界面。"""

    init_succeeded = Signal(str)  # work_dir

    def __init__(self, parent=None, default_stack_work_dir: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("时间序列分析配置")
        self.setMinimumSize(520, 360)
        self.resize(560, 420)
        self.setModal(False)
        self._default_stack_work_dir = (default_stack_work_dir or "").strip()
        self._worker: MintPyInitWorker | None = None
        self._last_work_dir: str | None = None
        self._build_ui()
        self._prefill()

    def _prefill(self) -> None:
        if self._default_stack_work_dir and os.path.isdir(self._default_stack_work_dir):
            mintpy_sub = os.path.join(self._default_stack_work_dir, "mintpy")
            if not self.work_dir_edit.text().strip():
                self.work_dir_edit.setText(mintpy_sub)
            if not self.stack_product_edit.text().strip():
                self.stack_product_edit.setText(self._default_stack_work_dir)
            self.stack_product_edit.setEnabled(False)
            self._stack_product_label.setStyleSheet("color: #64748b;")
        self._update_open_btn()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        title = QLabel("时间序列分析配置（MintPy）")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("指定 MintPy 工作目录；若为独立入口可填写 Stack 产品目录（topsStack 输出根目录）以自动填充 load 路径。从 Stack 流程进入时已自动预填。")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        grp = QGroupBox("路径")
        grp_layout = QFormLayout(grp)
        grp_layout.setHorizontalSpacing(12)
        grp_layout.setVerticalSpacing(10)
        grp_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("MintPy 工作目录（如 …/stack/mintpy）")
        grp_layout.addRow("工作目录:", _path_field_with_browse(self.work_dir_edit, "选择 MintPy 工作目录"))

        self.stack_product_edit = QLineEdit()
        self.stack_product_edit.setPlaceholderText("可选：topsStack 输出根目录（含 merged/reference/baselines）")
        self._stack_product_label = QLabel("Stack 产品目录:")
        grp_layout.addRow(self._stack_product_label, _path_field_with_browse(self.stack_product_edit, "选择 Stack 产品目录"))
        layout.addWidget(grp)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(QLabel("进度"))
        layout.addWidget(self.progress_bar)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(80)
        self.log_edit.setPlaceholderText("初始化日志…")
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.init_btn = QPushButton("初始化")
        self.init_btn.clicked.connect(self._on_init)
        self.open_flow_btn = QPushButton("打开流程界面")
        self.open_flow_btn.clicked.connect(self._on_open_flow)
        self.open_flow_btn.setEnabled(False)
        self.work_dir_edit.textChanged.connect(lambda: self._update_open_btn())
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.init_btn)
        btn_layout.addWidget(self.open_flow_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _update_open_btn(self) -> None:
        self.open_flow_btn.setEnabled(bool(self.work_dir_edit.text().strip()))

    def _set_form_enabled(self, enabled: bool) -> None:
        self.work_dir_edit.setEnabled(enabled)
        self.stack_product_edit.setEnabled(enabled)
        self.init_btn.setEnabled(enabled)

    def _on_init(self) -> None:
        work_dir = self.work_dir_edit.text().strip()
        if not work_dir:
            QMessageBox.warning(self, "参数错误", "请填写工作目录。")
            return
        stack_work_dir = self._default_stack_work_dir or None
        if not stack_work_dir and os.path.dirname(work_dir):
            parent = os.path.dirname(work_dir)
            if os.path.basename(work_dir).lower() == "mintpy":
                stack_work_dir = parent
        stack_product_dir = self.stack_product_edit.text().strip() or None
        if not stack_product_dir and stack_work_dir:
            stack_product_dir = stack_work_dir
        if stack_product_dir and not os.path.isdir(stack_product_dir):
            QMessageBox.warning(self, "参数错误", "Stack 产品目录不存在。")
            return

        self.log_edit.clear()
        self.progress_bar.setValue(10)
        self.log_edit.appendPlainText("正在初始化 MintPy 工作目录…")
        self._set_form_enabled(False)
        self._worker = MintPyInitWorker(work_dir, stack_work_dir, stack_product_dir, self)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.finished_with_result.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, pct: float, msg: str) -> None:
        self.progress_bar.setValue(int(pct))
        self.log_edit.appendPlainText(msg)

    def _on_finished(self, result: dict) -> None:
        self._set_form_enabled(True)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self.progress_bar.setValue(100 if result.get("success") else 0)
        if result.get("success"):
            self._last_work_dir = result.get("work_dir", self.work_dir_edit.text().strip())
            self.open_flow_btn.setEnabled(True)
            self.init_succeeded.emit(self._last_work_dir or "")
            self.log_edit.appendPlainText("初始化完成，可点击「打开流程界面」。")
            warn = result.get("warning", "").strip()
            if warn:
                self.log_edit.appendPlainText("")
                self.log_edit.appendPlainText("⚠ " + warn.replace("\n", "\n⚠ "))
                QMessageBox.warning(self, "请检查 Stack 产品目录", warn)
            else:
                QMessageBox.information(self, "初始化完成", "smallbaselineApp.cfg 已生成，可点击「打开流程界面」查看步骤并运行。")
        else:
            err = result.get("error_message", "未知错误")
            logging.error("MintPy 初始化失败: %s", err)
            self.log_edit.appendPlainText("--- 错误 ---")
            self.log_edit.appendPlainText(err)
            QMessageBox.warning(self, "初始化失败", err)

    def _on_open_flow(self) -> None:
        if self._last_work_dir:
            self.init_succeeded.emit(self._last_work_dir)
        else:
            work_dir = self.work_dir_edit.text().strip()
            if work_dir:
                self.init_succeeded.emit(work_dir)
            else:
                QMessageBox.warning(self, "打开流程", "请先指定工作目录并完成初始化。")

    def get_work_dir(self) -> str | None:
        return self._last_work_dir or self.work_dir_edit.text().strip() or None
