"""
时间序列流程界面：从 work_dir 读取 MintPy 步骤列表（get_mintpy_pipeline），
展示 13 步（与 processDDH.ipynb 一致），支持运行当前步、从本步运行、全部运行。
步骤状态持久化到 work_dir/mintpy_step_state.json；支持打开日志目录、编辑配置、查看结果。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

MINTPY_STATE_FILE = "mintpy_step_state.json"

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFrame,
    QGroupBox,
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont

from desktop.app.styles import (
    FLOW_BTN_RUN_ALL,
    FLOW_BTN_RUN_ALL_HOVER,
    FLOW_BTN_RUN_CURRENT,
    FLOW_BTN_RUN_CURRENT_HOVER,
    FLOW_BTN_RUN_FROM,
    FLOW_BTN_RUN_FROM_HOVER,
    apply_status_style,
    flow_button_stylesheet,
)


STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAIL = "fail"

MAX_POPUP_ERROR_CHARS = 600


def _truncate_error_for_popup(msg: str) -> str:
    if not msg or len(msg) <= MAX_POPUP_ERROR_CHARS:
        return msg
    return msg[:MAX_POPUP_ERROR_CHARS].rstrip() + "\n…\n（完整内容见下方日志）"


class MintPySingleStepWorker(QThread):
    progress_updated = Signal(float, str)
    step_finished = Signal(bool, str)

    def __init__(self, work_dir: str, step_id: str, parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self._step_id = step_id

    def run(self) -> None:
        try:
            from backend.services.mintpy_processing_service import run_mintpy_step

            def progress_cb(pct: float, msg: str) -> None:
                self.progress_updated.emit(pct, msg)

            result = run_mintpy_step(
                self._work_dir,
                self._step_id,
                progress_callback=progress_cb,
            )
            if result.get("success"):
                self.step_finished.emit(True, "")
            else:
                self.step_finished.emit(False, result.get("error_message", "执行失败"))
        except Exception as e:
            self.progress_updated.emit(0.0, f"错误: {e}")
            self.step_finished.emit(False, str(e))


class MintPyStepRunnerWorker(QThread):
    progress_updated = Signal(float, str)
    all_finished = Signal(bool, str)

    def __init__(self, work_dir: str, from_step_index: int, step_ids: List[str], parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self._from_step_index = from_step_index
        self._step_ids = step_ids

    def run(self) -> None:
        try:
            from backend.services.mintpy_processing_service import run_mintpy_steps

            def progress_cb(pct: float, msg: str) -> None:
                self.progress_updated.emit(pct, msg)

            result = run_mintpy_steps(
                self._work_dir,
                self._from_step_index,
                step_ids=self._step_ids,
                progress_callback=progress_cb,
            )
            if result.get("success"):
                self.all_finished.emit(True, "")
            else:
                self.all_finished.emit(False, result.get("error_message", "执行失败"))
        except Exception as e:
            self.progress_updated.emit(0.0, f"错误: {e}")
            self.all_finished.emit(False, str(e))


class MintPyFlowWidget(QWidget):
    """时间序列流程：步骤表 + 进度 + 日志；运行当前步/从本步运行/全部运行。"""

    def __init__(self, work_dir: str, parent=None):
        super().__init__(parent)
        self._work_dir = os.path.abspath(work_dir)
        self._steps: List[Dict[str, Any]] = []
        self._step_status: List[str] = []
        self._worker: MintPyStepRunnerWorker | None = None
        self._single_step_worker: MintPySingleStepWorker | None = None
        self._running_from_index = 0
        self._single_step_index = -1
        self._build_ui()
        self._load_pipeline()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        title = QLabel("时间序列流程（MintPy smallbaselineApp）")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self._work_dir_label = QLabel(self._work_dir)
        self._work_dir_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self._work_dir_label.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(self._work_dir_label)
        layout.addWidget(header)

        log_row = QHBoxLayout()
        self._log_path_label = QLabel("")
        self._log_path_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self._log_path_label.setWordWrap(True)
        log_row.addWidget(self._log_path_label, 1)
        self._open_log_dir_btn = QPushButton("打开日志目录")
        self._open_log_dir_btn.clicked.connect(self._on_open_log_dir)
        log_row.addWidget(self._open_log_dir_btn)
        layout.addLayout(log_row)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["序号", "步骤", "状态", "运行", "配置", "查看"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        progress_grp = QGroupBox("执行进度")
        progress_layout = QVBoxLayout(progress_grp)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        progress_layout.addWidget(self._progress_bar)
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(140)
        self._log_edit.setPlaceholderText("执行日志…")
        progress_layout.addWidget(self._log_edit)
        layout.addWidget(progress_grp)

        btn_layout = QHBoxLayout()
        self._run_one_btn = QPushButton("运行当前步")
        self._run_one_btn.setFixedHeight(26)
        self._run_one_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_RUN_CURRENT, FLOW_BTN_RUN_CURRENT_HOVER))
        self._run_one_btn.clicked.connect(self._on_run_current_step)
        self._run_from_btn = QPushButton("从本步运行")
        self._run_from_btn.setFixedHeight(26)
        self._run_from_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_RUN_FROM, FLOW_BTN_RUN_FROM_HOVER))
        self._run_from_btn.clicked.connect(self._on_run_from_step)
        self._run_all_btn = QPushButton("全部运行")
        self._run_all_btn.setFixedHeight(26)
        self._run_all_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_RUN_ALL, FLOW_BTN_RUN_ALL_HOVER))
        self._run_all_btn.clicked.connect(self._on_run_all)
        btn_layout.addWidget(self._run_one_btn)
        btn_layout.addWidget(self._run_from_btn)
        btn_layout.addWidget(self._run_all_btn)
        self._loading_spinner = QProgressBar()
        self._loading_spinner.setRange(0, 0)
        self._loading_spinner.setFixedSize(28, 28)
        self._loading_spinner.setVisible(False)
        self._loading_spinner.setStyleSheet("QProgressBar { border: none; background: transparent; }")
        btn_layout.addWidget(self._loading_spinner)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _load_pipeline(self) -> None:
        """从 mintpy_processing_service 获取步骤列表并刷新表格。"""
        try:
            from backend.services.mintpy_processing_service import get_mintpy_pipeline
            out = get_mintpy_pipeline(self._work_dir, use_full_list=False)
        except Exception as e:
            self._steps = []
            self._step_status = []
            self._table.setRowCount(0)
            self._log_edit.setPlainText(f"获取步骤列表失败: {e}")
            return
        self._steps = out.get("steps") or []
        self._step_status = [STATUS_PENDING] * len(self._steps)
        self._load_step_state()
        if not self._steps:
            self._table.setRowCount(0)
            if not out.get("template_exists"):
                self._log_edit.setPlainText("未找到 smallbaselineApp.cfg，请先初始化时间序列工作目录。")
            return
        self._fill_table()
        self._update_log_path_label()

    def _load_step_state(self) -> None:
        """从 work_dir/mintpy_step_state.json 合并步骤状态。"""
        path = os.path.join(self._work_dir, MINTPY_STATE_FILE)
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            states = data.get("steps") or {}
            for i, step in enumerate(self._steps):
                step_id = step.get("id", "")
                if step_id and states.get(step_id) in (STATUS_SUCCESS, STATUS_FAIL):
                    self._step_status[i] = states[step_id]
        except Exception:
            pass

    def _save_step_state(self) -> None:
        """将当前步骤状态写入 work_dir/mintpy_step_state.json。"""
        path = os.path.join(self._work_dir, MINTPY_STATE_FILE)
        try:
            states = {}
            for i, step in enumerate(self._steps):
                if i < len(self._step_status):
                    states[step.get("id", "")] = self._step_status[i]
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"steps": states}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _update_log_path_label(self) -> None:
        self._log_path_label.setText(f"工作目录: {self._work_dir}")
        self._log_path_label.setToolTip(self._work_dir)

    @Slot()
    def _on_open_log_dir(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        path = self._work_dir.replace("/", os.sep)
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _fill_table(self) -> None:
        self._table.setRowCount(len(self._steps))
        for i, step in enumerate(self._steps):
            self._table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._table.setItem(i, 1, QTableWidgetItem(step.get("name", step.get("id", ""))))
            status_item = QTableWidgetItem(self._status_text(self._step_status[i]))
            apply_status_style(status_item, self._step_status[i])
            self._table.setItem(i, 2, status_item)
            run_btn = QPushButton("运行")
            run_btn.setProperty("step_index", i)
            run_btn.clicked.connect(lambda checked=False, idx=i: self._run_single_step(idx))
            self._table.setCellWidget(i, 3, run_btn)
            cfg_btn = QPushButton("配置")
            cfg_btn.setToolTip("编辑 smallbaselineApp.cfg")
            cfg_btn.clicked.connect(self._on_edit_mintpy_config)
            self._table.setCellWidget(i, 4, cfg_btn)
            view_btn = QPushButton("查看")
            view_btn.setToolTip("查看时间序列结果")
            view_btn.clicked.connect(lambda checked=False, idx=i: self._on_view_mintpy_result(idx))
            self._table.setCellWidget(i, 5, view_btn)
        self._table.resizeRowsToContents()

    @Slot()
    def _on_edit_mintpy_config(self) -> None:
        cfg_path = os.path.join(self._work_dir, "smallbaselineApp.cfg")
        if not os.path.isfile(cfg_path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "配置", "未找到 smallbaselineApp.cfg")
            return
        try:
            import subprocess
            if os.name == "nt":
                os.startfile(cfg_path)
            else:
                subprocess.run(["xdg-open", cfg_path], check=False)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "打开失败", str(e))

    def _on_view_mintpy_result(self, index: int) -> None:
        """打开 MintPy 产品查看（velocity、coherence 等）。"""
        from .product_viewer import ProductViewerDialog
        from PySide6.QtWidgets import QMessageBox
        candidates = []
        for name in ("velocity.h5", "temporalCoherence.h5", "avgSpatialCoh.h5", "maskTempCoh.h5"):
            p = os.path.join(self._work_dir, name)
            if os.path.isfile(p):
                candidates.append(p)
        geo = os.path.join(self._work_dir, "geo")
        if os.path.isdir(geo):
            for name in ("geo_velocity.h5", "geo_temporalCoherence.h5"):
                p = os.path.join(geo, name)
                if os.path.isfile(p):
                    candidates.append(p)
        if not candidates:
            QMessageBox.information(self, "查看结果", "未找到 velocity 或 coherence 等 HDF5 产品。请先运行相应步骤。")
            return
        dlg = ProductViewerDialog(self, initial_path=candidates[0], candidate_paths=candidates)
        dlg.exec()

    def _status_text(self, status: str) -> str:
        return {"pending": "待运行", "running": "运行中", "success": "成功", "fail": "失败"}.get(status, status)

    def _update_step_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._step_status):
            self._step_status[index] = status
            item = self._table.item(index, 2)
            if item:
                item.setText(self._status_text(status))
                apply_status_style(item, status)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._run_one_btn.setEnabled(enabled)
        self._run_from_btn.setEnabled(enabled)
        self._run_all_btn.setEnabled(enabled)
        self._loading_spinner.setVisible(not enabled)
        for i in range(self._table.rowCount()):
            for col in (3, 4, 5):
                w = self._table.cellWidget(i, col)
                if isinstance(w, QPushButton):
                    w.setEnabled(enabled)

    @Slot()
    def _on_run_current_step(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "运行", "请先选中一行步骤。")
            return
        self._run_single_step(row)

    def _run_single_step(self, index: int) -> None:
        if index < 0 or index >= len(self._steps):
            return
        if self._single_step_worker and self._single_step_worker.isRunning():
            return
        step = self._steps[index]
        step_id = step.get("id", "")
        self._set_buttons_enabled(False)
        self._update_step_status(index, STATUS_RUNNING)
        self._log_edit.clear()
        self._progress_bar.setValue(0)
        self._log_edit.appendPlainText(f"正在运行: {step.get('name', step_id)} …")

        self._single_step_index = index
        self._single_step_worker = MintPySingleStepWorker(self._work_dir, step_id, self)
        self._single_step_worker.progress_updated.connect(self._on_single_step_progress)
        self._single_step_worker.step_finished.connect(self._on_single_step_finished)
        self._single_step_worker.start()

    def _on_single_step_progress(self, pct: float, msg: str) -> None:
        self._progress_bar.setValue(int(pct))
        if msg:
            self._log_edit.appendPlainText(msg)

    def _on_single_step_finished(self, success: bool, error_message: str) -> None:
        idx = self._single_step_index
        if self._single_step_worker:
            self._single_step_worker.deleteLater()
            self._single_step_worker = None
        self._single_step_index = -1
        self._set_buttons_enabled(True)

        if 0 <= idx < len(self._step_status):
            self._update_step_status(idx, STATUS_SUCCESS if success else STATUS_FAIL)
            self._save_step_state()
        if success:
            self._progress_bar.setValue(100)
            self._log_edit.appendPlainText("步骤完成。")
        else:
            self._progress_bar.setValue(0)
            self._log_edit.appendPlainText("")
            self._log_edit.appendPlainText("失败原因：")
            self._log_edit.appendPlainText(error_message or "执行失败")
            QMessageBox.warning(self, "步骤失败", _truncate_error_for_popup(error_message or "执行失败"))

    @Slot()
    def _on_run_from_step(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "从本步运行", "请先选中起始步骤。")
            return
        self._run_steps_from(row)

    @Slot()
    def _on_run_all(self) -> None:
        self._run_steps_from(0)

    def _run_steps_from(self, from_index: int) -> None:
        if from_index < 0 or from_index >= len(self._steps):
            return
        self._set_buttons_enabled(False)
        for i in range(from_index, len(self._steps)):
            self._update_step_status(i, STATUS_PENDING)
        self._log_edit.clear()
        self._progress_bar.setValue(0)

        self._running_from_index = from_index
        step_ids = [s.get("id", "") for s in self._steps]
        self._worker = MintPyStepRunnerWorker(
            self._work_dir, from_index, step_ids, self
        )
        self._worker.progress_updated.connect(self._on_worker_progress)
        self._worker.all_finished.connect(self._on_worker_all_finished)
        self._worker.start()

    def _on_worker_progress(self, pct: float, msg: str) -> None:
        self._progress_bar.setValue(int(pct))
        self._log_edit.appendPlainText(msg)
        m = re.match(r"步骤\s+(\d+)/\d+", msg.strip())
        if m and self._worker:
            one_based = int(m.group(1))
            cur_index = self._running_from_index + one_based - 1
            if 0 <= cur_index < len(self._step_status):
                for i in range(self._running_from_index, cur_index):
                    self._update_step_status(i, STATUS_SUCCESS)
                self._update_step_status(cur_index, STATUS_RUNNING)

    def _on_worker_all_finished(self, success: bool, error_message: str) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._set_buttons_enabled(True)
        self._progress_bar.setValue(100 if success else 0)
        if not success:
            self._log_edit.appendPlainText("")
            self._log_edit.appendPlainText("失败原因：")
            self._log_edit.appendPlainText(error_message or "执行失败")
            QMessageBox.warning(
                self, "执行结束", _truncate_error_for_popup(error_message or "执行失败")
            )
        else:
            self._log_edit.appendPlainText("全部步骤完成。")
            for i in range(self._running_from_index, len(self._steps)):
                self._update_step_status(i, STATUS_SUCCESS)
            self._save_step_state()
            QMessageBox.information(self, "执行结束", "全部步骤已完成。")

    def set_work_dir(self, work_dir: str) -> None:
        self._work_dir = os.path.abspath(work_dir)
        self._work_dir_label.setText(self._work_dir)
        self._load_pipeline()

    def get_work_dir(self) -> str:
        return self._work_dir
