"""
Stack 流程界面：从 work_dir 读取 pipeline.json，展示步骤列表（序号、中文名、状态），
支持「运行」当前步、「从本步运行」、全部运行。QThread + 本机 Python 子进程执行，进度与日志实时更新。
步骤状态持久化到 work_dir/pipeline_state.json；支持打开日志目录、清理本步输出、编辑参数、查看结果。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List

PIPELINE_STATE_FILE = "pipeline_state.json"

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
    QSizePolicy,
    QApplication,
    QStyle,
    QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import QSize

from desktop.app import icons as app_icons

from desktop.app.styles import (
    FLOW_BTN_RUN_ALL,
    FLOW_BTN_RUN_ALL_HOVER,
    FLOW_BTN_RUN_CURRENT,
    FLOW_BTN_RUN_CURRENT_HOVER,
    FLOW_BTN_RUN_FROM,
    FLOW_BTN_RUN_FROM_HOVER,
    FLOW_BTN_NAV,
    FLOW_BTN_NAV_HOVER,
    StatusColumnDelegate,
    apply_status_style,
    flow_button_stylesheet,
)


# 步骤状态
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAIL = "fail"

# 弹窗中错误内容最大字符数，超出则截断并提示查看下方日志
MAX_POPUP_ERROR_CHARS = 600


def _truncate_error_for_popup(msg: str) -> str:
    """截断过长错误信息，弹窗只显示摘要，完整内容在日志区。"""
    if not msg or len(msg) <= MAX_POPUP_ERROR_CHARS:
        return msg
    return msg[:MAX_POPUP_ERROR_CHARS].rstrip() + "\n…\n（完整内容见下方日志）"


class StackSingleStepWorker(QThread):
    """后台执行单步，避免主线程阻塞；进度与日志通过 signal 回传。"""
    progress_updated = Signal(float, str)
    step_finished = Signal(bool, str)  # success, error_message

    def __init__(self, work_dir: str, step_id: str, parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self._step_id = step_id

    def run(self) -> None:
        try:
            from backend.services.stack_processing_service import run_stack_step

            def progress_cb(pct: float, msg: str) -> None:
                self.progress_updated.emit(pct, msg)

            result = run_stack_step(
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


class StackJobMonitorWorker(QThread):
    """轮询 WSL 后台 Stack 任务与 stack_step.log，界面关闭后重新打开时恢复监控。"""

    log_appended = Signal(str)
    job_finished = Signal(bool, str, int)  # success, error_message, step_index

    def __init__(self, work_dir: str, step_index: int, step_id: str = "", parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self._step_index = step_index
        self._step_id = step_id
        self._stop = False
        self._log_offset = 0

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        from backend.services.stack_processing_service import (
            probe_stack_job,
            parse_step_log_result,
            read_stack_log_from_offset,
        )

        try:
            _, self._log_offset = read_stack_log_from_offset(self._work_dir, 0)
        except Exception:
            self._log_offset = 0

        while not self._stop:
            chunk, self._log_offset = read_stack_log_from_offset(self._work_dir, self._log_offset)
            if chunk:
                self.log_appended.emit(chunk.rstrip("\n"))

            probe = probe_stack_job(self._work_dir)
            if probe.get("is_running"):
                self.msleep(2000)
                continue

            step_id = self._step_id or probe.get("step_id") or ""
            if not step_id and isinstance(probe.get("active"), dict):
                step_id = probe["active"].get("step_id") or ""
            result = parse_step_log_result(self._work_dir, step_id) if step_id else None
            if result and result.get("finished"):
                if result.get("success"):
                    self.job_finished.emit(True, "completed", self._step_index)
                else:
                    self.job_finished.emit(
                        False,
                        f"步骤 {step_id} 返回码 {result.get('returncode')}",
                        self._step_index,
                    )
                return

            # active 记录存在但进程已结束且日志尚无完整块
            if probe.get("active"):
                self.job_finished.emit(
                    False,
                    "后台任务已结束，但未在日志中找到完成记录，请查看 stack_step.log。",
                    self._step_index,
                )
                return
            # 进程已结束且无 active：仅释放界面
            self.job_finished.emit(False, "", self._step_index)
            return


class StackStepRunnerWorker(QThread):
    """后台执行从某步起至结束；本机 subprocess 调用 SentinelWrapper，带 progress 回调。"""
    progress_updated = Signal(float, str)
    step_finished = Signal(int, bool)  # step_index, success
    all_finished = Signal(bool, str)   # success, error_message

    def __init__(self, work_dir: str, from_step_index: int, parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self._from_step_index = from_step_index

    def run(self) -> None:
        try:
            from backend.services.stack_processing_service import run_stack_steps

            def progress_cb(pct: float, msg: str) -> None:
                self.progress_updated.emit(pct, msg)

            result = run_stack_steps(
                self._work_dir,
                self._from_step_index,
                progress_callback=progress_cb,
            )
            if result.get("success"):
                self.all_finished.emit(True, "")
            else:
                self.all_finished.emit(False, result.get("error_message", "执行失败"))
        except Exception as e:
            self.progress_updated.emit(0.0, f"错误: {e}")
            self.all_finished.emit(False, str(e))


class StackFlowWidget(QWidget):
    """流程步骤列表 + 进度 + 日志；运行/从本步运行/全部运行。"""

    # 从 Stack 进入时间序列：主窗口连接此信号并打开 MintPy 配置对话框（预填 stack_work_dir）
    request_open_mintpy_config = Signal(str)  # stack_work_dir
    # 打开 Stack 配置对话框（重新初始化 / 补全 pipeline.json）
    request_stack_flow_config = Signal(str)  # work_dir

    def __init__(self, work_dir: str, parent=None):
        super().__init__(parent)
        self._work_dir = os.path.abspath(work_dir)
        self._pipeline: Dict[str, Any] | None = None
        self._steps: List[Dict[str, Any]] = []
        self._step_status: List[str] = []  # pending/running/success/fail
        self._worker: StackStepRunnerWorker | None = None
        self._single_step_worker: StackSingleStepWorker | None = None
        self._monitor_worker: StackJobMonitorWorker | None = None
        self._monitor_step_index = -1
        self._running_from_index = 0
        self._single_step_index = -1  # 当前单步运行对应的表格行，用于结束后更新状态
        self._step_durations: List[float | None] = []  # 每步耗时（秒），用于表格「耗时」列
        self._row_progress_bars: List[QProgressBar] = []  # 每行进度条（进度列）
        self._step_start_time: float | None = None  # 当前运行步开始时间
        self._build_ui()
        self._load_pipeline()

    def get_work_dir(self) -> str:
        return self._work_dir

    def reload_from_disk(self) -> None:
        """重新读取 pipeline.json（例如在工作目录完成初始化后刷新当前页）。"""
        self._load_pipeline()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 顶部栏：标题 + 状态标签 + 输出路径（文件夹/复制）
        top_bar = QHBoxLayout()
        title = QLabel("Stack 流程")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self._status_tag = QLabel("待运行")
        self._status_tag.setStyleSheet("padding: 2px 8px;")  # 颜色由 qt-material 主题决定
        top_bar.addWidget(title)
        top_bar.addWidget(self._status_tag)
        top_bar.addStretch()
        self._work_dir_label = QLabel(self._work_dir)
        self._work_dir_label.setWordWrap(False)
        top_bar.addWidget(self._work_dir_label, 1)
        self._open_work_dir_btn = QPushButton("打开目录")
        self._open_work_dir_btn.setToolTip("打开工作目录")
        self._open_work_dir_btn.setFixedHeight(28)
        self._open_work_dir_btn.clicked.connect(self._on_open_log_dir)
        top_bar.addWidget(self._open_work_dir_btn)
        self._copy_path_btn = QPushButton("复制路径")
        self._copy_path_btn.setToolTip("复制路径")
        self._copy_path_btn.setFixedHeight(28)
        self._copy_path_btn.clicked.connect(lambda: self._copy_to_clipboard(self._work_dir))
        top_bar.addWidget(self._copy_path_btn)
        self._stack_init_btn = QPushButton("初始化流程…")
        self._stack_init_btn.setToolTip("打开 Stack 流程配置并执行初始化，生成 pipeline.json")
        self._stack_init_btn.setFixedHeight(28)
        self._stack_init_btn.clicked.connect(self._on_request_stack_config)
        self._stack_init_btn.setVisible(False)
        top_bar.addWidget(self._stack_init_btn)
        layout.addLayout(top_bar)

        # 处理进度区：紧凑布局，按钮缩小以突出下方步骤控制区
        progress_grp = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(progress_grp)
        progress_layout.setSpacing(6)
        self._progress_summary_label = QLabel("已完成 0/0 个步骤")
        progress_layout.addWidget(self._progress_summary_label)
        progress_bar_row = QHBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setMinimumHeight(8)
        progress_bar_row.addWidget(self._progress_bar, 1)
        self._progress_pct_label = QLabel("0%")
        self._progress_pct_label.setMinimumWidth(36)
        progress_bar_row.addWidget(self._progress_pct_label)
        progress_layout.addLayout(progress_bar_row)
        btn_layout = QHBoxLayout()
        self._run_one_btn = QPushButton("▶ 运行当前步")
        self._run_one_btn.setFixedHeight(26)
        self._run_one_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_RUN_CURRENT, FLOW_BTN_RUN_CURRENT_HOVER))
        self._run_one_btn.clicked.connect(self._on_run_current_step)
        self._run_from_btn = QPushButton("从本步运行")
        self._run_from_btn.setFixedHeight(26)
        self._run_from_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_RUN_FROM, FLOW_BTN_RUN_FROM_HOVER))
        self._run_from_btn.clicked.connect(self._on_run_from_step)
        self._run_all_btn = QPushButton("全线运行")
        self._run_all_btn.setFixedHeight(26)
        self._run_all_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_RUN_ALL, FLOW_BTN_RUN_ALL_HOVER))
        self._run_all_btn.clicked.connect(self._on_run_all)
        btn_layout.addWidget(self._run_one_btn)
        btn_layout.addWidget(self._run_from_btn)
        btn_layout.addWidget(self._run_all_btn)
        self._loading_spinner = QProgressBar()
        self._loading_spinner.setRange(0, 0)
        self._loading_spinner.setFixedSize(22, 22)
        self._loading_spinner.setVisible(False)
        self._loading_spinner.setStyleSheet("QProgressBar { border: none; background: transparent; }")
        btn_layout.addWidget(self._loading_spinner)
        btn_layout.addStretch()
        self._mintpy_btn = QPushButton("进入时间序列 →")
        self._mintpy_btn.setToolTip("打开时间序列分析配置，工作目录预填为当前 Stack 下的 mintpy")
        self._mintpy_btn.setFixedHeight(26)
        self._mintpy_btn.setStyleSheet(flow_button_stylesheet(FLOW_BTN_NAV, FLOW_BTN_NAV_HOVER))
        self._mintpy_btn.clicked.connect(self._on_enter_mintpy)
        btn_layout.addWidget(self._mintpy_btn)
        progress_layout.addLayout(btn_layout)
        layout.addWidget(progress_grp)

        # 步骤控制区（核心）：表格占主要空间，设最小高度并参与拉伸
        self._table = QTableWidget()
        self._table.setMinimumHeight(280)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["序号", "步骤", "状态", "耗时", "进度", "操作"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)   # 序号
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)             # 步骤：占剩余空间
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)   # 状态
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)   # 耗时
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 100)                                              # 进度
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 165)                                             # 操作：运行、目录、清理 三钮，留足宽度
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 状态列：保持自定义颜色/加粗，不被主题的选中态覆盖
        self._table.setItemDelegateForColumn(2, StatusColumnDelegate(self._table))
        # 单步运行期间锁定选中行，避免点击/焦点切换导致“跳行”
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)

        # 执行日志：淡框与其他区域区分，标题弱化
        self._log_frame = QFrame()
        self._log_frame.setObjectName("logFrame")
        self._log_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._log_frame.setStyleSheet("""
            QFrame#logFrame {
                background: transparent;
                border: none;
            }
        """)
        log_frame_layout = QVBoxLayout(self._log_frame)
        log_frame_layout.setContentsMargins(0, 0, 0, 0)
        self._log_header_btn = QPushButton("▾ 执行日志")
        self._log_header_btn.setCheckable(True)
        self._log_header_btn.setChecked(True)
        self._log_header_btn.setFixedHeight(24)
        self._log_header_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 2px 6px;
                font-size: 11px;
                color: #64748b;
                background: transparent;
                border: none;
                border-bottom: 1px solid rgba(100, 116, 139, 0.3);
            }
            QPushButton:hover { color: #94a3b8; }
            QPushButton:checked { color: #94a3b8; }
        """)
        self._log_header_btn.clicked.connect(self._on_toggle_log)
        log_frame_layout.addWidget(self._log_header_btn)
        self._log_content_widget = QWidget()
        self._log_content_widget.setObjectName("logContentBox")
        self._log_content_widget.setStyleSheet("""
            QWidget#logContentBox {
                background-color: rgba(15, 23, 42, 0.6);
                border: 1px solid rgba(148, 163, 184, 0.22);
                border-radius: 4px;
            }
        """)
        log_content_layout = QVBoxLayout(self._log_content_widget)
        log_content_layout.setContentsMargins(8, 6, 8, 8)
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMinimumHeight(80)
        self._log_edit.setPlaceholderText("执行日志…")
        log_content_layout.addWidget(self._log_edit)
        log_footer = QHBoxLayout()
        self._log_path_label = QLabel("")
        self._log_path_label.setWordWrap(True)
        log_footer.addWidget(self._log_path_label, 1)
        self._copy_log_path_btn = QPushButton("复制")
        self._copy_log_path_btn.setToolTip("复制日志路径")
        self._copy_log_path_btn.setFixedHeight(26)
        self._copy_log_path_btn.clicked.connect(self._on_copy_log_path)
        log_footer.addWidget(self._copy_log_path_btn)
        self._open_log_dir_btn = QPushButton("打开日志目录")
        self._open_log_dir_btn.setFixedHeight(26)
        self._open_log_dir_btn.clicked.connect(self._on_open_log_dir)
        log_footer.addWidget(self._open_log_dir_btn)
        log_content_layout.addLayout(log_footer)
        log_frame_layout.addWidget(self._log_content_widget)

        # 步骤表与执行日志用纵向 QSplitter，可拖拽调整日志区高度
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.addWidget(self._table)
        self._main_splitter.addWidget(self._log_frame)
        self._table.setMinimumHeight(200)
        self._log_frame.setMinimumHeight(120)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 0)
        layout.addWidget(self._main_splitter, 1)

    def _load_pipeline(self) -> None:
        """从 work_dir 读取 pipeline.json 并刷新表格。"""
        path = os.path.join(self._work_dir, "pipeline.json")
        if not os.path.isfile(path):
            self._pipeline = None
            self._steps = []
            self._step_status = []
            self._step_durations = []
            self._table.setRowCount(0)
            self._log_edit.setPlainText("未找到 pipeline.json，请先在此工作目录执行「初始化流程」。")
            self._update_progress_summary()
            self._apply_pipeline_dependent_controls()
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                self._pipeline = json.load(f)
        except Exception as e:
            self._pipeline = None
            self._steps = []
            self._step_status = []
            self._step_durations = []
            self._table.setRowCount(0)
            self._log_edit.setPlainText(f"读取 pipeline.json 失败: {e}")
            self._update_progress_summary()
            self._apply_pipeline_dependent_controls()
            return
        self._steps = self._pipeline.get("steps") or []
        self._step_status = [STATUS_PENDING] * len(self._steps)
        self._step_durations = [None] * len(self._steps)
        self._load_step_state()
        self._fill_table()
        self._update_log_path_label()
        self._update_progress_summary()
        self._apply_pipeline_dependent_controls()
        self._try_resume_active_job()

    def closeEvent(self, event) -> None:
        self._stop_job_monitor()
        super().closeEvent(event)

    def _load_step_state(self) -> None:
        """从 work_dir/pipeline_state.json 合并步骤状态。"""
        path = os.path.join(self._work_dir, PIPELINE_STATE_FILE)
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            states = data.get("steps") or {}
            for i, step in enumerate(self._steps):
                step_id = step.get("id", "")
                st = states.get(step_id)
                if step_id and st in (STATUS_SUCCESS, STATUS_FAIL, STATUS_RUNNING):
                    self._step_status[i] = st
        except Exception:
            pass

    def _save_step_state(self, *, active: dict | None = None, clear_active: bool = False) -> None:
        """将步骤状态写入 pipeline_state.json；可附带 active 后台任务信息。"""
        path = os.path.join(self._work_dir.replace("/", os.sep), PIPELINE_STATE_FILE)
        existing: dict = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        try:
            states = {}
            for i, step in enumerate(self._steps):
                if i < len(self._step_status):
                    states[step.get("id", "")] = self._step_status[i]
            data: dict = {"steps": states}
            if clear_active:
                pass
            elif active is not None:
                data["active"] = active
            elif isinstance(existing.get("active"), dict):
                data["active"] = existing["active"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _build_active_record(self, step_index: int, mode: str) -> dict:
        step = self._steps[step_index] if 0 <= step_index < len(self._steps) else {}
        return {
            "step_id": step.get("id", ""),
            "step_index": step_index,
            "mode": mode,
            "from_index": self._running_from_index if mode == "batch" else step_index,
            "started_at": time.time(),
        }

    def _is_background_job_running(self) -> bool:
        if self._single_step_worker and self._single_step_worker.isRunning():
            return True
        if self._worker and self._worker.isRunning():
            return True
        try:
            from backend.services.stack_processing_service import probe_stack_job

            wsl_running = bool(probe_stack_job(self._work_dir).get("is_running"))
        except Exception:
            wsl_running = False
        if not wsl_running and self._monitor_worker and self._monitor_worker.isRunning():
            self._stop_job_monitor()
        return wsl_running

    def _try_resume_active_job(self) -> None:
        """重新打开界面时：若 WSL 内仍有 Stack 任务在跑，恢复状态与日志监控。"""
        if self._monitor_worker and self._monitor_worker.isRunning():
            return
        try:
            from backend.services.stack_processing_service import (
                probe_stack_job,
                parse_step_log_result,
                read_stack_log_tail,
            )
        except Exception:
            return

        probe = probe_stack_job(self._work_dir)
        active = probe.get("active")
        step_id = probe.get("step_id") or (active or {}).get("step_id") or ""
        step_index = probe.get("step_index")
        if step_index is None and step_id:
            for i, step in enumerate(self._steps):
                if step.get("id") == step_id:
                    step_index = i
                    break
        if step_index is None:
            for i, st in enumerate(self._step_status):
                if st == STATUS_RUNNING:
                    step_index = i
                    if not step_id and i < len(self._steps):
                        step_id = self._steps[i].get("id", "")
                    break
        step_index = int(step_index if step_index is not None else -1)

        if not probe.get("is_running"):
            self._finalize_idle_background_state(probe, step_id, step_index)
            return

        if probe.get("is_running"):
            if 0 <= step_index < len(self._step_status):
                if probe.get("mode") == "batch":
                    from_index = int(probe.get("from_index") or step_index)
                    self._running_from_index = from_index
                    for i in range(from_index, step_index):
                        if self._step_status[i] != STATUS_SUCCESS:
                            self._update_step_status(i, STATUS_SUCCESS)
                self._update_step_status(step_index, STATUS_RUNNING)
                self._monitor_step_index = step_index
                self._single_step_index = step_index if probe.get("mode") == "single" else -1
                if step_index < len(self._row_progress_bars):
                    self._row_progress_bars[step_index].setRange(0, 0)  # 不确定进度
                    self._row_progress_bars[step_index].setVisible(True)
            self._log_edit.setPlainText(read_stack_log_tail(self._work_dir))
            self._log_edit.appendPlainText("\n[已恢复监控后台任务，完成后将自动更新状态]")
            self._set_buttons_enabled(False)
            self._update_status_tag(True)
            self._attach_job_monitor(step_index, step_id)
            if not active and 0 <= step_index:
                mode = probe.get("mode") or "single"
                if mode == "batch":
                    self._running_from_index = int(probe.get("from_index") or step_index)
                self._save_step_state(active=self._build_active_record(step_index, mode))
            return

    def _stop_job_monitor(self) -> None:
        if self._monitor_worker and self._monitor_worker.isRunning():
            self._monitor_worker.stop()
            self._monitor_worker.wait(3000)
        if self._monitor_worker:
            self._monitor_worker.deleteLater()
            self._monitor_worker = None
        self._monitor_step_index = -1

    def _finalize_idle_background_state(
        self, probe: dict, step_id: str, step_index: int
    ) -> None:
        """无 WSL 进程时：清理 active、复位「运行中」步骤，恢复可操作按钮。"""
        from backend.services.stack_processing_service import parse_step_log_result

        active = probe.get("active")
        if active and step_id:
            result = parse_step_log_result(self._work_dir, step_id)
            if result and result.get("finished") and 0 <= step_index < len(self._step_status):
                self._update_step_status(
                    step_index,
                    STATUS_SUCCESS if result.get("success") else STATUS_FAIL,
                )
        for i, st in enumerate(self._step_status):
            if st == STATUS_RUNNING:
                self._update_step_status(i, STATUS_PENDING)
                if i < len(self._row_progress_bars):
                    self._row_progress_bars[i].setRange(0, 100)
                    self._row_progress_bars[i].setValue(0)
                    self._row_progress_bars[i].setVisible(False)
        self._stop_job_monitor()
        self._save_step_state(clear_active=True)
        self._update_status_tag(False)
        self._set_buttons_enabled(True)
        self._apply_pipeline_dependent_controls()

    def _attach_job_monitor(self, step_index: int, step_id: str = "") -> None:
        if self._monitor_worker and self._monitor_worker.isRunning():
            return
        self._monitor_worker = StackJobMonitorWorker(self._work_dir, step_index, step_id, self)
        self._monitor_worker.log_appended.connect(self._on_monitor_log)
        self._monitor_worker.job_finished.connect(self._on_monitor_finished)
        self._monitor_worker.start()

    def _on_monitor_log(self, chunk: str) -> None:
        if chunk:
            self._log_edit.appendPlainText(chunk)

    def _on_monitor_finished(self, success: bool, error_message: str, step_index: int) -> None:
        if self._monitor_worker:
            self._monitor_worker.deleteLater()
            self._monitor_worker = None
        self._monitor_step_index = -1
        self._single_step_index = -1
        self._set_buttons_enabled(True)
        self._update_status_tag(False)
        if 0 <= step_index < len(self._row_progress_bars):
            self._row_progress_bars[step_index].setRange(0, 100)
            self._row_progress_bars[step_index].setValue(100 if success else 0)
            self._row_progress_bars[step_index].setVisible(success and error_message == "completed")
        if error_message == "completed" and 0 <= step_index < len(self._step_status):
            self._update_step_status(step_index, STATUS_SUCCESS)
            self._log_edit.appendPlainText("后台步骤已完成。")
            self._progress_bar.setValue(100)
            self._progress_pct_label.setText("100%")
        elif error_message and error_message != "completed" and 0 <= step_index < len(self._step_status):
            self._update_step_status(step_index, STATUS_FAIL)
            self._log_edit.appendPlainText(error_message)
            QMessageBox.warning(self, "步骤失败", _truncate_error_for_popup(error_message))
        self._save_step_state(clear_active=True)
        self._update_progress_summary()
        self._apply_pipeline_dependent_controls()

    def _update_log_path_label(self) -> None:
        log_path = os.path.join(self._work_dir, "stack_step.log")
        self._log_path_label.setText(log_path)
        self._log_path_label.setToolTip(log_path)

    def _update_progress_summary(self) -> None:
        n = len(self._steps)
        done = sum(1 for s in self._step_status if s == STATUS_SUCCESS)
        pct = int(100 * done / n) if n else 0
        self._progress_summary_label.setText(f"已完成 {done}/{n} 个步骤")
        self._progress_bar.setValue(pct)
        self._progress_pct_label.setText(f"{pct}%")

    def _update_status_tag(self, running: bool) -> None:
        if running:
            self._status_tag.setText("处理中")
            self._status_tag.setProperty("class", "warning")
        else:
            self._status_tag.setText("待运行")
            self._status_tag.setProperty("class", "")
        self._status_tag.style().unpolish(self._status_tag)
        self._status_tag.style().polish(self._status_tag)

    @Slot()
    def _on_toggle_log(self) -> None:
        visible = self._log_header_btn.isChecked()
        self._log_content_widget.setVisible(visible)
        self._log_header_btn.setText("▾ 执行日志" if visible else "▸ 执行日志")

    def _on_copy_log_path(self) -> None:
        log_path = os.path.join(self._work_dir, "stack_step.log")
        self._copy_to_clipboard(log_path)

    def _copy_to_clipboard(self, text: str) -> None:
        app = QApplication.instance()
        if app and app.clipboard():
            app.clipboard().setText(text or "")

    @Slot()
    def _on_open_log_dir(self) -> None:
        """在资源管理器中打开工作目录。"""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        path = self._work_dir.replace("/", os.sep)
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif os.path.dirname(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _on_clean_step(self, index: int) -> None:
        """清理本步骤数据：删除本步输出目录，本步进度清零，总体进度对应调整。"""
        if index < 0 or index >= len(self._steps):
            return
        step = self._steps[index]
        step_id = step.get("id", "")
        try:
            from backend.services.stack_processing_service import get_stack_step_output_dirs
            dirs = get_stack_step_output_dirs(step_id)
        except Exception:
            dirs = []
        if not dirs:
            QMessageBox.information(
                self,
                "清理本步骤数据",
                "当前步骤无预定义输出目录可清理，或请手动删除工作目录下对应文件夹后重跑。",
            )
            return
        msg = f"将删除以下目录，清理后本步骤进度清零、可重新运行：\n" + "\n".join(os.path.join(self._work_dir, d) for d in dirs)
        if QMessageBox.question(self, "确认清理", msg, QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Ok:
            return
        try:
            from backend.services.stack_processing_service import clear_stack_step_output
            clear_stack_step_output(self._work_dir, step_id)
            self._step_status[index] = STATUS_PENDING
            self._step_durations[index] = None
            if self._table.item(index, 2):
                self._table.item(index, 2).setText(self._status_text(STATUS_PENDING))
            if self._table.item(index, 3):
                self._table.item(index, 3).setText(self._format_duration(None))
            if index < len(self._row_progress_bars):
                self._row_progress_bars[index].setValue(0)
                self._row_progress_bars[index].setVisible(False)
            self._update_progress_summary()
            self._save_step_state()
            QMessageBox.information(self, "清理完成", "本步骤数据已清理，进度已清零，总体进度已更新。")
        except Exception as e:
            QMessageBox.warning(self, "清理失败", str(e))

    def _on_edit_step_params(self, index: int) -> None:
        """用系统默认程序打开本步 config 文件。"""
        if index < 0 or index >= len(self._steps):
            return
        step = self._steps[index]
        commands = step.get("commands") or []
        config_path = None
        for line in commands:
            line = (line or "").strip()
            if "-c" in line:
                parts = line.split()
                for j, p in enumerate(parts):
                    if p == "-c" and j + 1 < len(parts):
                        config_path = parts[j + 1]
                        break
            if config_path:
                break
        if not config_path:
            QMessageBox.information(self, "参数", "本步无 config 路径。")
            return
        config_path = self._normalize_config_path(config_path)
        if not config_path:
            return
        if not os.path.isfile(config_path):
            QMessageBox.warning(self, "参数", f"文件不存在：{config_path}")
            return
        try:
            import subprocess
            if os.name == "nt":
                os.startfile(config_path)
            else:
                subprocess.run(["xdg-open", config_path], check=False)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _normalize_config_path(self, raw_path: str) -> str | None:
        """
        将 pipeline.json 中的 config 路径规范化为本机可访问路径：
        - 相对路径：相对 work_dir 拼接
        - WSL /mnt/<drive>/...：转换为 Windows <Drive>:\\...
        其它 Linux 路径无法在 Windows 直接打开，会给出提示。
        """
        p = (raw_path or "").strip()
        if not p:
            QMessageBox.information(self, "参数", "本步无 config 路径。")
            return None

        # 相对路径：相对 work_dir 拼接
        if not (p.startswith("/") or re.match(r"^[a-zA-Z]:[\\/]", p)):
            base = (self._work_dir or "").strip()
            if base:
                p = os.path.join(base.replace("/", os.sep), p.replace("/", os.sep))
            else:
                p = p.replace("/", os.sep)

        # WSL /mnt/<drive>/... -> Windows <Drive>:\...
        win = self._wsl_mnt_to_windows(p)
        if win is None:
            QMessageBox.information(
                self,
                "参数",
                f"该 config 路径为 Linux/WSL 形式，Windows 无法直接打开：\n{raw_path}\n\n"
                "请在 Windows 路径下运行流程（work_dir 形如 D:\\...），或将该目录导出/映射到 Windows 后再打开。",
            )
            return None
        return win

    def _wsl_mnt_to_windows(self, path: str) -> str | None:
        """将 /mnt/d/... 转为 D:\\...；若为其它 Linux 路径则返回 None。"""
        s = (path or "").strip().replace("\\", "/")
        # 已是 Windows
        if re.match(r"^[a-zA-Z]:/", s):
            return s.replace("/", os.sep)
        m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", s)
        if m:
            drive = m.group(1).upper()
            rest = m.group(2).replace("/", os.sep)
            return f"{drive}:{os.sep}{rest}"
        if s.startswith("/"):
            return None
        return path

    def _on_view_step_result(self, index: int) -> None:
        """打开本步产出结果查看器。"""
        if index < 0 or index >= len(self._steps):
            return
        from .product_viewer import open_product_viewer
        step = self._steps[index]
        step_id = step.get("id", "")
        open_product_viewer(self._work_dir, step_id, parent=self)

    def _fill_table(self) -> None:
        self._row_progress_bars.clear()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["序号", "步骤", "状态", "耗时", "进度", "操作"])
        self._table.setRowCount(len(self._steps))
        for i, step in enumerate(self._steps):
            self._table.setItem(i, 0, QTableWidgetItem(f"{i + 1:02d}"))
            self._table.setItem(i, 1, QTableWidgetItem(step.get("name", step.get("id", ""))))
            status_item = QTableWidgetItem(self._status_text(self._step_status[i]))
            apply_status_style(status_item, self._step_status[i])
            self._table.setItem(i, 2, status_item)
            # 耗时
            dur = self._step_durations[i] if i < len(self._step_durations) else None
            self._table.setItem(i, 3, QTableWidgetItem(self._format_duration(dur)))
            # 进度（仅运行中显示）
            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setValue(0)
            pbar.setTextVisible(True)
            pbar.setMaximumHeight(20)
            pbar.setVisible(False)
            self._row_progress_bars.append(pbar)
            self._table.setCellWidget(i, 4, pbar)
            # 操作：运行、打开输出目录、清理（已移除查看结果、编辑 config）
            op_widget = QWidget()
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(4, 0, 4, 0)
            op_layout.setSpacing(2)
            run_btn = self._make_icon_btn(app_icons.icon_play(), "运行本步")
            run_btn.clicked.connect(lambda checked=False, idx=i: self._run_single_step(idx))
            op_layout.addWidget(run_btn)
            dir_btn = self._make_icon_btn(app_icons.icon_folder_open(), "打开本步输出目录")
            dir_btn.clicked.connect(lambda checked=False, idx=i: self._on_open_step_dir(idx))
            op_layout.addWidget(dir_btn)
            clean_btn = self._make_icon_btn(app_icons.icon_refresh(), "清理本步骤数据（进度清零）")
            clean_btn.clicked.connect(lambda checked=False, idx=i: self._on_clean_step(idx))
            op_layout.addWidget(clean_btn)
            op_layout.addStretch()
            op_widget.setMinimumWidth(28 * 3 + 2 * 2 + 8)
            self._table.setCellWidget(i, 5, op_widget)
        self._table.resizeRowsToContents()

    def _make_icon_btn(self, icon: QIcon, tooltip: str) -> QPushButton:
        """创建统一风格的小图标按钮（用于表格操作列），固定尺寸 + 悬停/按下微交互。"""
        b = QPushButton()
        b.setIcon(icon)
        b.setIconSize(QSize(14, 14))
        b.setToolTip(tooltip)
        b.setFixedSize(28, 26)
        b.setStyleSheet("""
            QPushButton { border: none; background: transparent; border-radius: 4px; }
            QPushButton:hover { background-color: rgba(0, 0, 0, 0.08); }
            QPushButton:pressed { background-color: rgba(0, 0, 0, 0.12); }
        """)
        return b

    def _status_text(self, status: str) -> str:
        return {"pending": "待运行", "running": "运行中", "success": "已完成", "fail": "失败"}.get(status, status)

    def _format_duration(self, seconds: float | None) -> str:
        if seconds is None:
            return "—"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s" if m else f"{s}s"

    def _on_open_step_dir(self, index: int) -> None:
        """打开本步输出目录（第一个输出目录或工作目录）。"""
        if index < 0 or index >= len(self._steps):
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        step = self._steps[index]
        step_id = step.get("id", "")
        try:
            from backend.services.stack_processing_service import get_stack_step_output_dirs
            dirs = get_stack_step_output_dirs(step_id)
            if dirs:
                path = os.path.join(self._work_dir, dirs[0].replace("/", os.sep))
            else:
                path = self._work_dir
        except Exception:
            path = self._work_dir
        path = path.replace("/", os.sep)
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._work_dir))

    def _update_step_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._step_status):
            self._step_status[index] = status
            item = self._table.item(index, 2)
            if item:
                item.setText(self._status_text(status))
                apply_status_style(item, status)
            if index < len(self._row_progress_bars):
                self._row_progress_bars[index].setRange(0, 100)
                self._row_progress_bars[index].setVisible(status == STATUS_RUNNING)
                if status != STATUS_RUNNING:
                    self._row_progress_bars[index].setValue(0)
            self._update_progress_summary()

    def _apply_pipeline_dependent_controls(self) -> None:
        """无有效步骤时禁用运行与时间序列入口，并显示「初始化流程」。"""
        ok = len(self._steps) > 0
        self._stack_init_btn.setVisible(not ok)
        idle = not self._is_background_job_running()
        self._run_one_btn.setEnabled(idle and ok)
        self._run_from_btn.setEnabled(idle and ok)
        self._run_all_btn.setEnabled(idle and ok)
        self._mintpy_btn.setEnabled(idle and ok)
        self._stack_init_btn.setEnabled(idle)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        ok = len(self._steps) > 0
        self._run_one_btn.setEnabled(enabled and ok)
        self._run_from_btn.setEnabled(enabled and ok)
        self._run_all_btn.setEnabled(enabled and ok)
        self._mintpy_btn.setEnabled(enabled and ok)
        if self._stack_init_btn.isVisible():
            self._stack_init_btn.setEnabled(enabled)
        # 关闭顶部小型加载动画，避免视觉闪烁干扰；仅通过按钮禁用状态和整体进度条体现运行中状态
        self._loading_spinner.setVisible(False)
        for i in range(self._table.rowCount()):
            w = self._table.cellWidget(i, 5)
            if w is not None:
                for c in w.findChildren(QPushButton):
                    c.setEnabled(enabled)

    @Slot()
    def _on_enter_mintpy(self) -> None:
        """进入时间序列：通知主窗口打开 MintPy 配置对话框（预填当前 Stack 工作目录）。"""
        self.request_open_mintpy_config.emit(self._work_dir)

    @Slot()
    def _on_request_stack_config(self) -> None:
        self.request_stack_flow_config.emit(self._work_dir)

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
        if self._is_background_job_running():
            QMessageBox.information(
                self,
                "运行",
                "检测到该工作目录仍有 Stack 步骤在后台运行，请等待完成或先重新打开本页恢复监控。",
            )
            self._try_resume_active_job()
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
        self._update_status_tag(True)
        self._save_step_state(active=self._build_active_record(index, "single"))
        self._log_edit.clear()
        self._progress_bar.setValue(0)
        self._progress_pct_label.setText("0%")
        self._log_edit.appendPlainText(f"正在运行: {step.get('name', step_id)} …")
        self._step_start_time = time.time()
        self._single_step_worker = StackSingleStepWorker(self._work_dir, step_id, self)
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

    def _on_single_step_progress(self, pct: float, msg: str) -> None:
        self._progress_bar.setValue(int(pct))
        self._progress_pct_label.setText(f"{int(pct)}%")
        if 0 <= self._single_step_index < len(self._row_progress_bars):
            self._row_progress_bars[self._single_step_index].setValue(int(pct))
            self._row_progress_bars[self._single_step_index].setVisible(True)
        if msg:
            self._log_edit.appendPlainText(msg)

    def _on_table_selection_changed(self) -> None:
        """单步运行期间锁定当前选中行。"""
        if self._single_step_worker and self._single_step_worker.isRunning() and self._single_step_index >= 0:
            if self._table.currentRow() != self._single_step_index:
                self._enforce_running_row_selection()

    def _on_single_step_finished(self, success: bool, error_message: str) -> None:
        idx = self._single_step_index
        if self._single_step_worker:
            self._single_step_worker.deleteLater()
            self._single_step_worker = None
        self._single_step_index = -1
        self._set_buttons_enabled(True)
        self._update_status_tag(False)

        if idx >= 0 and idx < len(self._step_durations) and self._step_start_time is not None:
            self._step_durations[idx] = time.time() - self._step_start_time
            if self._table.item(idx, 3):
                self._table.item(idx, 3).setText(self._format_duration(self._step_durations[idx]))
        self._step_start_time = None

        if idx < 0 or idx >= len(self._step_status):
            return
        if success:
            self._update_step_status(idx, STATUS_SUCCESS)
            self._progress_bar.setValue(100)
            self._progress_pct_label.setText("100%")
            self._log_edit.appendPlainText("步骤完成。")
            self._save_step_state(clear_active=True)
            # 单步成功后再自动跳到下一行
            next_row = min(idx + 1, self._table.rowCount() - 1)
            if next_row != idx and next_row >= 0:
                self._table.setCurrentCell(next_row, 0)
                self._table.selectRow(next_row)
        else:
            self._update_step_status(idx, STATUS_FAIL)
            self._save_step_state(clear_active=True)
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
        # 从未完成的第一步开始，跳过已成功的步骤
        from_index = 0
        for i in range(len(self._steps)):
            if self._step_status[i] != STATUS_SUCCESS:
                from_index = i
                break
        else:
            QMessageBox.information(self, "全线运行", "全部步骤已完成，无需重新运行。")
            return
        self._run_steps_from(from_index)

    def _run_steps_from(self, from_index: int) -> None:
        if from_index < 0 or from_index >= len(self._steps):
            return
        if self._is_background_job_running():
            QMessageBox.information(
                self,
                "运行",
                "检测到该工作目录仍有 Stack 步骤在后台运行，请等待完成或先重新打开本页恢复监控。",
            )
            self._try_resume_active_job()
            return
        self._set_buttons_enabled(False)
        self._update_status_tag(True)
        self._running_from_index = from_index
        self._save_step_state(active=self._build_active_record(from_index, "batch"))
        # 只将未完成的步骤设为待运行，不覆盖已成功的状态
        for i in range(from_index, len(self._steps)):
            if self._step_status[i] != STATUS_SUCCESS:
                self._update_step_status(i, STATUS_PENDING)
        self._log_edit.clear()
        self._progress_bar.setValue(0)
        self._progress_pct_label.setText("0%")

        self._worker = StackStepRunnerWorker(self._work_dir, from_index, self)
        self._worker.progress_updated.connect(self._on_worker_progress)
        self._worker.all_finished.connect(self._on_worker_all_finished)
        self._worker.start()

    def _on_worker_progress(self, pct: float, msg: str) -> None:
        self._progress_bar.setValue(int(pct))
        self._progress_pct_label.setText(f"{int(pct)}%")
        self._log_edit.appendPlainText(msg)
        # 解析 "步骤 3/10: 名称" 得到实际步骤下标（1-based -> 0-based），支持「已完成，跳过」
        m = re.match(r"步骤\s+(\d+)/\d+", msg.strip())
        if m and self._worker:
            one_based = int(m.group(1))
            cur_index = one_based - 1
            if 0 <= cur_index < len(self._step_status):
                if "跳过" in msg:
                    self._update_step_status(cur_index, STATUS_SUCCESS)
                    self._save_step_state()
                else:
                    for i in range(self._running_from_index, cur_index):
                        self._update_step_status(i, STATUS_SUCCESS)
                    self._update_step_status(cur_index, STATUS_RUNNING)
                    self._save_step_state(active=self._build_active_record(cur_index, "batch"))
                if cur_index < len(self._row_progress_bars) and "跳过" not in msg:
                    self._row_progress_bars[cur_index].setValue(int(pct))
                    self._row_progress_bars[cur_index].setVisible(True)

    def _on_worker_all_finished(self, success: bool, error_message: str) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._set_buttons_enabled(True)
        self._update_status_tag(False)
        self._progress_bar.setValue(100 if success else 0)
        self._progress_pct_label.setText("100%" if success else "0%")
        if not success:
            self._log_edit.appendPlainText("")
            self._log_edit.appendPlainText("失败原因：")
            self._log_edit.appendPlainText(error_message or "执行失败")
            self._save_step_state(clear_active=True)
            QMessageBox.warning(
                self, "执行结束", _truncate_error_for_popup(error_message or "执行失败")
            )
        else:
            self._log_edit.appendPlainText("全部步骤完成。")
            for i in range(self._running_from_index, len(self._steps)):
                self._update_step_status(i, STATUS_SUCCESS)
            self._save_step_state(clear_active=True)
            QMessageBox.information(self, "执行结束", "全部步骤已完成。")

    def set_work_dir(self, work_dir: str) -> None:
        """切换工作目录并重新加载 pipeline。"""
        self._work_dir = os.path.abspath(work_dir)
        self._work_dir_label.setText(self._work_dir)
        self._load_pipeline()

    def get_work_dir(self) -> str:
        return self._work_dir
