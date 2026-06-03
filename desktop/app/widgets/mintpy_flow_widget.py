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
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont

from desktop.app.styles import (
    FLOW_BTN_RUN_ALL,
    FLOW_BTN_RUN_ALL_HOVER,
    FLOW_BTN_RUN_CURRENT,
    FLOW_BTN_RUN_CURRENT_HOVER,
    FLOW_BTN_RUN_FROM,
    FLOW_BTN_RUN_FROM_HOVER,
    StatusColumnDelegate,
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
    step_completed = Signal(int, bool)  # step_index, success
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

            def step_done_cb(step_index: int, _step_id: str, success: bool) -> None:
                self.step_completed.emit(step_index, success)

            result = run_mintpy_steps(
                self._work_dir,
                self._from_step_index,
                step_ids=self._step_ids,
                progress_callback=progress_cb,
                step_completed_callback=step_done_cb,
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
        # work_dir should be Windows path in Desktop; normalize accidental WSL style to Windows path
        self._work_dir = self._normalize_work_dir(work_dir)
        self._steps: List[Dict[str, Any]] = []
        self._step_status: List[str] = []
        self._worker: MintPyStepRunnerWorker | None = None
        self._single_step_worker: MintPySingleStepWorker | None = None
        self._running_from_index = 0
        self._single_step_index = -1
        self._init_worker: QThread | None = None
        self._build_ui()

        # Auto-initialize if smallbaselineApp.cfg doesn't exist
        cfg_path = os.path.join(self._work_dir, "smallbaselineApp.cfg")
        if not os.path.isfile(cfg_path):
            self._auto_init()
        else:
            self._load_pipeline()

    def _normalize_work_dir(self, work_dir: str) -> str:
        wd = (work_dir or "").strip()
        # If a WSL path is passed in on Windows, os.path.abspath will produce "D:\\mnt\\d\\..."
        # Convert it back to a real Windows path first.
        try:
            if wd.startswith("/mnt/"):
                from backend.services import wsl_runner

                wd = wsl_runner.wsl_path_to_windows(wd)
        except Exception:
            pass
        return os.path.abspath(wd) if wd else wd

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
        self._table.setHorizontalHeaderLabels(["序号", "步骤", "状态", "运行", "相关参数", "查看结果"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 状态列：保持自定义颜色/加粗，不被主题的选中态覆盖
        self._table.setItemDelegateForColumn(2, StatusColumnDelegate(self._table))
        # 单步运行期间锁定选中行，避免点击/焦点切换导致“跳行”
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
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
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _auto_init(self) -> None:
        """自动初始化 MintPy 工作目录（当 smallbaselineApp.cfg 不存在时）。"""
        self._log_edit.setPlainText("正在自动初始化 MintPy 工作目录…")
        self._progress_bar.setValue(5)

        # 推导 stack_work_dir：如果 work_dir 名为 "mintpy"，取上级目录
        stack_dir = None
        parent = os.path.dirname(self._work_dir)
        if os.path.basename(self._work_dir).lower() == "mintpy" and parent:
            stack_dir = parent

        from .mintpy_quick_setup_dialog import MintPyInitWorker
        self._init_worker = MintPyInitWorker(
            self._work_dir, stack_dir, stack_dir, self
        )
        self._init_worker.finished_with_result.connect(self._on_auto_init_finished)
        self._init_worker.start()

    def _on_auto_init_finished(self, result: dict) -> None:
        if self._init_worker:
            self._init_worker.deleteLater()
            self._init_worker = None
        if result.get("success"):
            self._progress_bar.setValue(100)
            self._log_edit.setPlainText("初始化完成，正在加载步骤…")
            self._load_pipeline()
        else:
            err = result.get("error_message", "未知错误")
            self._progress_bar.setValue(0)
            self._log_edit.setPlainText(f"自动初始化失败: {err}")

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
        """从 mintpy_step_state.json / 日志 / 输出文件恢复步骤状态。"""
        try:
            from backend.services.mintpy_processing_service import resolve_mintpy_step_states

            step_ids = [s.get("id", "") for s in self._steps]
            states = resolve_mintpy_step_states(self._work_dir, step_ids)
        except Exception:
            states = {}
        for i, step in enumerate(self._steps):
            step_id = step.get("id", "")
            if step_id and states.get(step_id) in (STATUS_SUCCESS, STATUS_FAIL):
                self._step_status[i] = states[step_id]

    def _save_step_state(self) -> None:
        """将当前步骤状态写入 work_dir/mintpy_step_state.json。"""
        try:
            from backend.services.mintpy_processing_service import save_mintpy_step_states_batch

            states = {}
            for i, step in enumerate(self._steps):
                if i < len(self._step_status):
                    states[step.get("id", "")] = self._step_status[i]
            save_mintpy_step_states_batch(self._work_dir, states)
        except Exception:
            pass

    def _update_log_path_label(self) -> None:
        state_path = os.path.join(self._work_dir, MINTPY_STATE_FILE)
        hint = ""
        if os.path.isfile(state_path):
            hint = f" | 状态文件: {MINTPY_STATE_FILE}"
        self._log_path_label.setText(f"工作目录: {self._work_dir}{hint}")
        self._log_path_label.setToolTip(
            f"{self._work_dir}\n状态: {state_path}\n（与 Stack 的 pipeline_state.json 类似，文件名为 mintpy_step_state.json）"
        )

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
            cfg_btn = QPushButton("相关参数")
            cfg_btn.setToolTip("查看并编辑该步骤相关参数")
            cfg_btn.clicked.connect(lambda checked=False, idx=i: self._on_open_step_config(idx))
            self._table.setCellWidget(i, 4, cfg_btn)
            view_btn = QPushButton("查看结果")
            view_btn.setToolTip("查看该步骤的输出结果")
            view_btn.clicked.connect(lambda checked=False, idx=i: self._on_view_mintpy_result(idx))
            self._table.setCellWidget(i, 5, view_btn)
        self._table.resizeRowsToContents()

    def _on_open_step_config(self, step_index: int) -> None:
        """打开对应步骤的参数配置面板。"""
        step = self._steps[step_index] if step_index < len(self._steps) else {}
        step_id = step.get("id", "")
        cfg_path = os.path.join(self._work_dir, "smallbaselineApp.cfg")
        if not os.path.isfile(cfg_path):
            QMessageBox.warning(self, "配置", "未找到 smallbaselineApp.cfg，请先初始化工作目录。")
            return
        from .mintpy_param_panel import MintPyParamPanel

        dlg = MintPyParamPanel(self._work_dir, self, focus_step=step_id)
        dlg.config_saved.connect(lambda _path: self._log_edit.appendPlainText("配置已更新"))
        dlg.show()

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
        # 先锁定运行行，避免后续禁用按钮导致焦点跳转把选中行带跑
        self._single_step_index = index
        self._enforce_running_row_selection()
        step = self._steps[index]
        step_id = step.get("id", "")
        self._set_buttons_enabled(False)
        # 让 Qt 完成可能的焦点转移后，再强制拉回一次（下一帧）
        QTimer.singleShot(0, self._enforce_running_row_selection)
        self._update_step_status(index, STATUS_RUNNING)
        self._log_edit.clear()
        self._progress_bar.setValue(0)
        self._log_edit.appendPlainText(f"正在运行: {step.get('name', step_id)} …")
        self._single_step_worker = MintPySingleStepWorker(self._work_dir, step_id, self)
        self._single_step_worker.progress_updated.connect(self._on_single_step_progress)
        self._single_step_worker.step_finished.connect(self._on_single_step_finished)
        self._single_step_worker.start()

    def _enforce_running_row_selection(self) -> None:
        """强制将选中行保持在正在运行的单步行上。"""
        idx = self._single_step_index
        if idx < 0 or idx >= self._table.rowCount():
            return
        self._table.blockSignals(True)
        try:
            self._table.setCurrentCell(idx, 0)
            self._table.selectRow(idx)
            self._table.setFocus()
        finally:
            self._table.blockSignals(False)

    def _on_table_selection_changed(self) -> None:
        """单步运行期间锁定当前选中行。"""
        if self._single_step_worker and self._single_step_worker.isRunning() and self._single_step_index >= 0:
            if self._table.currentRow() != self._single_step_index:
                self._enforce_running_row_selection()

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
            log_file = os.path.join(self._work_dir, "mintpy_step.log")
            self._log_edit.appendPlainText(f"详细日志: {log_file}")
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
        # 从未完成的步骤开始，已完成的跳过
        first_incomplete = 0
        for i in range(len(self._steps)):
            if self._step_status[i] != STATUS_SUCCESS:
                first_incomplete = i
                break
        else:
            first_incomplete = len(self._steps)
        if first_incomplete >= len(self._steps):
            QMessageBox.information(self, "全部运行", "所有步骤已完成，无需再运行。")
            return
        self._run_steps_from(first_incomplete)

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
        self._worker.step_completed.connect(self._on_worker_step_completed)
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

    def _on_worker_step_completed(self, step_index: int, success: bool) -> None:
        """每步完成后更新表格状态并立即持久化到 mintpy_step_state.json。"""
        if 0 <= step_index < len(self._step_status):
            self._update_step_status(step_index, STATUS_SUCCESS if success else STATUS_FAIL)
            self._save_step_state()

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
            self._log_edit.appendPlainText(f"详细日志: {os.path.join(self._work_dir, 'mintpy_step.log')}")
            QMessageBox.information(self, "执行结束", "全部步骤已完成。")

    def set_work_dir(self, work_dir: str) -> None:
        self._work_dir = self._normalize_work_dir(work_dir)
        self._work_dir_label.setText(self._work_dir)
        self._load_pipeline()

    def get_work_dir(self) -> str:
        return self._work_dir
