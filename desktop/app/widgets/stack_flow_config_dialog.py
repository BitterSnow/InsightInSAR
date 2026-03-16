"""
Stack 流程配置对话框：填写 StackConfigRequest，执行「初始化流程」生成 configs + run_files + pipeline.json。
成功后可选打开流程界面。仅用 Python 子进程，不依赖 bash。
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QFrame,
    QWidget,
    QFormLayout,
    QSpinBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont


def _path_field_with_browse(line: QLineEdit, caption: str, is_file: bool = False) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    h.addWidget(line, 1)
    btn = QPushButton("浏览…")
    if is_file:
        btn.clicked.connect(lambda: _browse_file(line, caption))
    else:
        btn.clicked.connect(lambda: _browse_dir(line, caption))
    h.addWidget(btn)
    return w


def _browse_dir(edit: QLineEdit, caption: str) -> None:
    path = QFileDialog.getExistingDirectory(None, caption)
    if path:
        edit.setText(path)


def _browse_file(edit: QLineEdit, caption: str) -> None:
    path, _ = QFileDialog.getOpenFileName(None, caption, "", "DEM/GeoTIFF (*.tif *.tiff *.dem *.wgs84);;所有文件 (*.*)")
    if path:
        edit.setText(path)


def _bbox_to_two_decimals(n: float, s: float, w: float, e: float) -> tuple[str, str, str, str]:
    """将范围四至格式化为保留两位小数的字符串。"""
    return (f"{s:.2f}", f"{n:.2f}", f"{w:.2f}", f"{e:.2f}")


class StackSwathDetectWorker(QThread):
    """根据 SLC 目录与工作范围（SNWE）自动检测 Swath。"""
    finished_with_swaths = Signal(list)

    def __init__(self, slc_dir: str, bbox_snwe: list[float], parent=None):
        super().__init__(parent)
        self._slc_dir = slc_dir
        self._bbox_snwe = bbox_snwe

    def run(self) -> None:
        try:
            from backend.services.s1_processing_service import resolve_safe_paths
            from backend.scripts.subswath_detector import detect_subswaths
            safe_list = resolve_safe_paths(self._slc_dir)
            if not safe_list:
                self.finished_with_swaths.emit([])
                return
            swaths = detect_subswaths(safe_list[0], bbox_snwe=self._bbox_snwe)
            self.finished_with_swaths.emit(swaths)
        except Exception:
            self.finished_with_swaths.emit([])


class StackInitWorker(QThread):
    """后台执行 Stack 初始化（stackSentinel.py + 解析 run_xx → pipeline.json）。"""
    progress_updated = Signal(float, str)
    finished_with_result = Signal(dict)

    def __init__(self, request_dict: dict, parent=None):
        super().__init__(parent)
        self._request_dict = request_dict

    def run(self) -> None:
        try:
            from shared_models import StackConfigRequest
            from backend.services.stack_processing_service import stack_init as do_stack_init
            request = StackConfigRequest.model_validate(self._request_dict)

            def progress_cb(pct: float, msg: str) -> None:
                self.progress_updated.emit(pct, msg)

            result = do_stack_init(request, progress_callback=progress_cb)
            self.finished_with_result.emit(result)
        except Exception as e:
            self.progress_updated.emit(0.0, f"错误: {e}")
            self.finished_with_result.emit({"success": False, "error_message": str(e), "pipeline": None})


class StackFlowConfigDialog(QDialog):
    """Stack 流程配置：工作目录、SLC、DEM、轨道、Aux、bbox、参考日期等；初始化流程。"""

    # work_dir 初始化成功后，父窗口可打开流程界面
    init_succeeded = Signal(str)  # work_dir

    def __init__(self, parent=None, default_project_path: str | None = None, project_node: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Stack 流程配置")
        self.setMinimumSize(620, 420)
        self.resize(640, 560)
        self.setModal(False)
        self._default_project_path = default_project_path or ""
        self._project_node = project_node  # 用于从工程文件预填、初始化成功后写回
        self._worker: StackInitWorker | None = None
        self._swath_worker: StackSwathDetectWorker | None = None
        self._build_ui()
        self._prefill_from_project()
        self.open_flow_btn.setEnabled(bool(self.work_dir_edit.text().strip()))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(0, 0, 8, 0)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        title = QLabel("Stack 流程配置")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("配置工作目录、SLC、DEM、轨道等，初始化后生成流程步骤（解压参考景、解压从景、合并 SLC 等），在流程界面内按步运行。")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        scroll_layout.addWidget(header)

        grp = QGroupBox("路径与参数")
        grp_layout = QFormLayout(grp)
        grp_layout.setHorizontalSpacing(12)
        grp_layout.setVerticalSpacing(10)
        grp_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.work_dir_edit = QLineEdit()
        self.work_dir_edit.setPlaceholderText("工程路径/processing/stack 或自定义目录")
        grp_layout.addRow("工作目录:", _path_field_with_browse(self.work_dir_edit, "选择工作目录"))

        self.slc_dir_edit = QLineEdit()
        self.slc_dir_edit.setPlaceholderText("Sentinel SLC zip 或 .SAFE 所在目录")
        grp_layout.addRow("SLC 目录:", _path_field_with_browse(self.slc_dir_edit, "选择 SLC 目录"))

        self.dem_edit = QLineEdit()
        self.dem_edit.setPlaceholderText("DEM 文件路径（WGS84）")
        dem_row = QHBoxLayout()
        dem_row.setContentsMargins(0, 0, 0, 0)
        dem_row.setSpacing(8)
        dem_row.addWidget(self.dem_edit, 1)
        browse_dem_btn = QPushButton("浏览…")
        browse_dem_btn.clicked.connect(lambda: _browse_file(self.dem_edit, "选择 DEM 文件"))
        dem_row.addWidget(browse_dem_btn)
        self.dem_make_btn = QPushButton("DEM制作")
        self.dem_make_btn.setToolTip("在 WSL 内调用 ISCE2 dem.py 拼接 SRTM DEM")
        self.dem_make_btn.clicked.connect(self._on_dem_make)
        dem_row.addWidget(self.dem_make_btn)
        dem_widget = QWidget()
        dem_widget.setLayout(dem_row)
        grp_layout.addRow("DEM:", dem_widget)

        self.orbit_edit = QLineEdit()
        self.orbit_edit.setPlaceholderText("轨道 EOF 目录")
        grp_layout.addRow("轨道目录:", _path_field_with_browse(self.orbit_edit, "选择轨道目录"))

        self.aux_edit = QLineEdit()
        self.aux_edit.setPlaceholderText("Aux 产品目录（cal/noise）")
        grp_layout.addRow("Aux 目录:", _path_field_with_browse(self.aux_edit, "选择 Aux 目录"))

        self.bbox_s = QLineEdit()
        self.bbox_s.setPlaceholderText("South")
        self.bbox_n = QLineEdit()
        self.bbox_n.setPlaceholderText("North")
        self.bbox_w = QLineEdit()
        self.bbox_w.setPlaceholderText("West")
        self.bbox_e = QLineEdit()
        self.bbox_e.setPlaceholderText("East")
        bbox_row = QHBoxLayout()
        bbox_row.setSpacing(8)
        bbox_row.addWidget(QLabel("S:"))
        bbox_row.addWidget(self.bbox_s)
        bbox_row.addWidget(QLabel("N:"))
        bbox_row.addWidget(self.bbox_n)
        bbox_row.addWidget(QLabel("W:"))
        bbox_row.addWidget(self.bbox_w)
        bbox_row.addWidget(QLabel("E:"))
        bbox_row.addWidget(self.bbox_e)
        for edit in (self.bbox_s, self.bbox_n, self.bbox_w, self.bbox_e):
            edit.editingFinished.connect(self._format_bbox_decimals)
        bbox_widget = QWidget()
        bbox_widget.setLayout(bbox_row)
        grp_layout.addRow("范围 (SNWE):", bbox_widget)

        self.reference_date_edit = QLineEdit()
        self.reference_date_edit.setPlaceholderText("YYYYMMDD，留空则首景")
        grp_layout.addRow("参考日期:", self.reference_date_edit)

        self.workflow_combo = QComboBox()
        self.workflow_combo.addItems(["interferogram", "slc", "correlation", "offset"])
        grp_layout.addRow("Workflow:", self.workflow_combo)

        self.swaths_edit = QLineEdit()
        self.swaths_edit.setPlaceholderText("根据工作范围自动计算 或 手动填写（如 1 2 3）")
        swath_row = QHBoxLayout()
        swath_row.addWidget(self.swaths_edit, 1)
        self.auto_swath_btn = QPushButton("根据工作范围自动计算")
        self.auto_swath_btn.setToolTip("需已填 SLC 目录与范围 S/N/W/E，按处理范围与 SAFE 数据自动检测 Swath")
        self.auto_swath_btn.clicked.connect(self._on_auto_fill_swaths)
        swath_row.addWidget(self.auto_swath_btn)
        grp_layout.addRow("Swaths:", swath_row)

        self.polarization_combo = QComboBox()
        self.polarization_combo.addItems(["vv", "vh"])
        grp_layout.addRow("极化:", self.polarization_combo)

        self.coregistration_combo = QComboBox()
        self.coregistration_combo.addItems(["NESD", "geometry"])
        grp_layout.addRow("配准:", self.coregistration_combo)

        self.num_connections_edit = QLineEdit()
        self.num_connections_edit.setText("1")
        grp_layout.addRow("连接数:", self.num_connections_edit)

        self.num_process_spin = QSpinBox()
        self.num_process_spin.setRange(1, 32)
        self.num_process_spin.setValue(1)
        grp_layout.addRow("并行数:", self.num_process_spin)

        scroll_layout.addWidget(grp)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        scroll_layout.addWidget(QLabel("进度"))
        scroll_layout.addWidget(self.progress_bar)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(100)
        self.log_edit.setPlaceholderText("初始化日志…")
        scroll_layout.addWidget(QLabel("日志"))
        scroll_layout.addWidget(self.log_edit)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.init_btn = QPushButton("初始化流程")
        self.init_btn.clicked.connect(self._on_init)
        self.open_flow_btn = QPushButton("打开流程界面")
        self.open_flow_btn.clicked.connect(self._on_open_flow)
        self.open_flow_btn.setEnabled(False)  # enabled when work_dir is set (on init success or when user types path)
        self.work_dir_edit.textChanged.connect(self._on_work_dir_changed)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.init_btn)
        btn_layout.addWidget(self.open_flow_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        self._last_work_dir: str | None = None

    def _prefill_from_project(self) -> None:
        """根据工程定义文件预填工作目录、处理范围、数据目录等。"""
        node = self._project_node
        if not node:
            if self._default_project_path:
                default_stack = os.path.join(self._default_project_path, "processing", "stack")
                if not self.work_dir_edit.text().strip():
                    self.work_dir_edit.setText(default_stack)
            return
        pdir = node.get("projectPath") or ""
        pid = node.get("id") or ""
        if not pdir or not pid:
            return
        try:
            from ..project_file import find_project_path, load_project_md_full
            proj_path = find_project_path(Path(pdir), pid)
            if not proj_path:
                if self._default_project_path:
                    self.work_dir_edit.setText(os.path.join(self._default_project_path, "processing", "stack"))
                return
            data = load_project_md_full(proj_path)
            if not data:
                return
            # 工作目录：优先 stack_work_dir，否则 工程路径/processing/stack
            work_dir = (data.get("stack_work_dir") or "").strip()
            if not work_dir:
                work_dir = os.path.join(pdir, "processing", "stack").replace("/", os.sep)
            self.work_dir_edit.setText(work_dir)
            # 处理范围：工作区 N,S,W,E，保留两位小数
            ws = data.get("workspace")
            if isinstance(ws, dict):
                try:
                    n, s, w, e = float(ws.get("n", 0)), float(ws.get("s", 0)), float(ws.get("w", 0)), float(ws.get("e", 0))
                    ss, nn, ww, ee = _bbox_to_two_decimals(n, s, w, e)
                    self.bbox_s.setText(ss)
                    self.bbox_n.setText(nn)
                    self.bbox_w.setText(ww)
                    self.bbox_e.setText(ee)
                except (TypeError, ValueError):
                    pass
            elif data.get("工作区"):
                parts = [p.strip() for p in str(data.get("工作区", "")).replace("，", ",").split(",")]
                if len(parts) >= 4:
                    try:
                        n, s, w, e = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
                        ss, nn, ww, ee = _bbox_to_two_decimals(n, s, w, e)
                        self.bbox_n.setText(nn)
                        self.bbox_s.setText(ss)
                        self.bbox_w.setText(ww)
                        self.bbox_e.setText(ee)
                    except ValueError:
                        self.bbox_n.setText(parts[0])
                        self.bbox_s.setText(parts[1])
                        self.bbox_w.setText(parts[2])
                        self.bbox_e.setText(parts[3])
            # 数据目录
            dd = data.get("data_dirs")
            if isinstance(dd, dict):
                if dd.get("safe_zip"):
                    self.slc_dir_edit.setText(str(dd["safe_zip"]).strip())
                if dd.get("orbit"):
                    self.orbit_edit.setText(str(dd["orbit"]).strip())
                if dd.get("dem"):
                    self.dem_edit.setText(str(dd["dem"]).strip())
                if dd.get("aux"):
                    self.aux_edit.setText(str(dd["aux"]).strip())
            else:
                for key, edit in [("SAFE ZIP 路径", self.slc_dir_edit), ("SAFE ZIP路径", self.slc_dir_edit), ("轨道目录", self.orbit_edit), ("DEM 路径", self.dem_edit), ("DEM路径", self.dem_edit), ("Aux 目录", self.aux_edit), ("Aux目录", self.aux_edit)]:
                    v = (data.get(key) or "").strip()
                    if v and not edit.text().strip():
                        edit.setText(v)
            # Swaths / 极化
            ip = data.get("import_params")
            if isinstance(ip, dict):
                if ip.get("swaths"):
                    self.swaths_edit.setText(str(ip["swaths"]).strip())
                if ip.get("polarization"):
                    idx = self.polarization_combo.findText(str(ip["polarization"]).strip())
                    if idx >= 0:
                        self.polarization_combo.setCurrentIndex(idx)
            else:
                if data.get("Swaths"):
                    self.swaths_edit.setText(str(data.get("Swaths", "1 2 3")).strip())
                if data.get("极化"):
                    idx = self.polarization_combo.findText(str(data.get("极化", "")).strip())
                    if idx >= 0:
                        self.polarization_combo.setCurrentIndex(idx)
            # Stack 初始化参数（若工程文件中已保存）
            si = data.get("stack_init")
            if isinstance(si, dict):
                if si.get("reference_date"):
                    self.reference_date_edit.setText(str(si["reference_date"]).strip())
                if si.get("workflow"):
                    idx = self.workflow_combo.findText(str(si["workflow"]).strip())
                    if idx >= 0:
                        self.workflow_combo.setCurrentIndex(idx)
                if si.get("coregistration"):
                    idx = self.coregistration_combo.findText(str(si["coregistration"]).strip())
                    if idx >= 0:
                        self.coregistration_combo.setCurrentIndex(idx)
                if si.get("num_connections"):
                    self.num_connections_edit.setText(str(si["num_connections"]).strip())
                if si.get("num_process") is not None:
                    self.num_process_spin.setValue(int(si["num_process"]))
        except Exception:
            if self._default_project_path:
                self.work_dir_edit.setText(os.path.join(self._default_project_path, "processing", "stack"))

    def _save_to_project(self) -> None:
        """将当前表单内容写入工程文件，供下次打开预填。"""
        node = self._project_node
        if not node:
            return
        pdir = node.get("projectPath") or ""
        pid = node.get("id") or ""
        if not pdir or not pid:
            return
        try:
            from ..project_file import find_project_path, load_project_md_full, write_project
            proj_path = find_project_path(Path(pdir), pid)
            if not proj_path:
                return
            data = load_project_md_full(proj_path)
            if not data:
                return
            work_dir = self.work_dir_edit.text().strip()
            if work_dir:
                data["stack_work_dir"] = work_dir
            data["data_dirs"] = {
                "safe_zip": self.slc_dir_edit.text().strip(),
                "orbit": self.orbit_edit.text().strip(),
                "dem": self.dem_edit.text().strip(),
                "aux": self.aux_edit.text().strip(),
            }
            try:
                n = float(self.bbox_n.text().strip())
                s = float(self.bbox_s.text().strip())
                w = float(self.bbox_w.text().strip())
                e = float(self.bbox_e.text().strip())
                n, s, w, e = round(n, 2), round(s, 2), round(w, 2), round(e, 2)
                data["workspace"] = {"n": n, "s": s, "w": w, "e": e}
                data["工作区"] = f"{n},{s},{w},{e}"
            except ValueError:
                pass
            swaths_val = self.swaths_edit.text().strip()
            data["import_params"] = {
                "swaths": swaths_val if swaths_val else "",
                "polarization": self.polarization_combo.currentText(),
            }
            data["stack_init"] = {
                "reference_date": self.reference_date_edit.text().strip(),
                "workflow": self.workflow_combo.currentText(),
                "coregistration": self.coregistration_combo.currentText(),
                "num_connections": self.num_connections_edit.text().strip() or "1",
                "num_process": self.num_process_spin.value(),
            }
            write_project(proj_path, data)
        except Exception:
            pass

    def _get_request_dict(self) -> dict | None:
        work_dir = self.work_dir_edit.text().strip()
        slc_dir = self.slc_dir_edit.text().strip()
        dem_path = self.dem_edit.text().strip()
        orbit_dir = self.orbit_edit.text().strip()
        aux_dir = self.aux_edit.text().strip()
        if not work_dir:
            QMessageBox.warning(self, "参数错误", "请填写工作目录。")
            return None
        if not slc_dir:
            QMessageBox.warning(self, "参数错误", "请填写 SLC 目录。")
            return None
        if not dem_path:
            QMessageBox.warning(self, "参数错误", "请填写 DEM 路径。")
            return None
        if not orbit_dir:
            QMessageBox.warning(self, "参数错误", "请填写轨道目录。")
            return None
        if not aux_dir:
            QMessageBox.warning(self, "参数错误", "请填写 Aux 目录。")
            return None

        # 必须先定义工作范围（S/N/W/E）
        try:
            s = self.bbox_s.text().strip()
            n = self.bbox_n.text().strip()
            w = self.bbox_w.text().strip()
            e = self.bbox_e.text().strip()
            if not all([s, n, w, e]):
                QMessageBox.warning(self, "参数错误", "请先定义工作范围（S、N、W、E 四格均须填写）。")
                return None
            bbox_snwe = [round(float(s), 2), round(float(n), 2), round(float(w), 2), round(float(e), 2)]
        except ValueError:
            QMessageBox.warning(self, "参数错误", "范围 S/N/W/E 须为数字。")
            return None

        swaths = self.swaths_edit.text().strip()
        if not swaths:
            QMessageBox.warning(
                self,
                "参数错误",
                "请填写 Swaths，或先定义工作范围与 SLC 目录后点击「根据工作范围自动计算」。",
            )
            return None

        return {
            "work_dir": work_dir,
            "slc_dir": slc_dir,
            "dem_path": dem_path,
            "orbit_dir": orbit_dir,
            "aux_dir": aux_dir,
            "bbox_snwe": bbox_snwe,
            "reference_date": self.reference_date_edit.text().strip() or None,
            "workflow": self.workflow_combo.currentText(),
            "swaths": self.swaths_edit.text().strip(),
            "polarization": self.polarization_combo.currentText(),
            "exclude_dates": None,
            "include_dates": None,
            "start_date": None,
            "stop_date": None,
            "coregistration": self.coregistration_combo.currentText(),
            "num_connections": self.num_connections_edit.text().strip() or "1",
            "num_process": self.num_process_spin.value(),
        }

    def _set_form_enabled(self, enabled: bool) -> None:
        self.work_dir_edit.setEnabled(enabled)
        self.slc_dir_edit.setEnabled(enabled)
        self.dem_edit.setEnabled(enabled)
        self.orbit_edit.setEnabled(enabled)
        self.aux_edit.setEnabled(enabled)
        self.bbox_s.setEnabled(enabled)
        self.bbox_n.setEnabled(enabled)
        self.bbox_w.setEnabled(enabled)
        self.bbox_e.setEnabled(enabled)
        self.reference_date_edit.setEnabled(enabled)
        self.workflow_combo.setEnabled(enabled)
        self.swaths_edit.setEnabled(enabled)
        self.polarization_combo.setEnabled(enabled)
        self.coregistration_combo.setEnabled(enabled)
        self.num_connections_edit.setEnabled(enabled)
        self.num_process_spin.setEnabled(enabled)
        self.init_btn.setEnabled(enabled)
        if hasattr(self, "auto_swath_btn"):
            self.auto_swath_btn.setEnabled(enabled)
        if hasattr(self, "dem_make_btn"):
            self.dem_make_btn.setEnabled(enabled)

    @Slot()
    def _format_bbox_decimals(self) -> None:
        """范围输入失焦时格式化为两位小数。"""
        edit = self.sender()
        if edit is None or edit not in (self.bbox_s, self.bbox_n, self.bbox_w, self.bbox_e):
            return
        t = edit.text().strip()
        if not t:
            return
        try:
            v = float(t)
            edit.setText(f"{v:.2f}")
        except ValueError:
            pass

    @Slot()
    def _on_auto_fill_swaths(self) -> None:
        """根据 SLC 目录与工作范围自动计算 Swaths。"""
        slc_dir = self.slc_dir_edit.text().strip()
        if not slc_dir:
            QMessageBox.warning(self, "自动计算 Swaths", "请先填写 SLC 目录。")
            return
        try:
            s = self.bbox_s.text().strip()
            n = self.bbox_n.text().strip()
            w = self.bbox_w.text().strip()
            e = self.bbox_e.text().strip()
            if not all([s, n, w, e]):
                QMessageBox.warning(self, "自动计算 Swaths", "请先定义工作范围（S、N、W、E 四格均须填写）。")
                return
            bbox_snwe = [float(s), float(n), float(w), float(e)]
        except ValueError:
            QMessageBox.warning(self, "自动计算 Swaths", "范围 S/N/W/E 须为有效数字。")
            return
        self.auto_swath_btn.setEnabled(False)
        self.log_edit.appendPlainText("正在根据工作范围检测 Swath…")
        self._swath_worker = StackSwathDetectWorker(slc_dir, bbox_snwe, self)
        self._swath_worker.finished_with_swaths.connect(self._on_auto_fill_swaths_done)
        self._swath_worker.start()

    def _on_auto_fill_swaths_done(self, swaths: list) -> None:
        if hasattr(self, "_swath_worker") and self._swath_worker:
            self._swath_worker.deleteLater()
            self._swath_worker = None
        self.auto_swath_btn.setEnabled(True)
        if swaths:
            self.swaths_edit.setText(" ".join(map(str, swaths)))
            self.log_edit.appendPlainText(f"已根据工作范围自动填充 Swaths: {swaths}")
        else:
            self.log_edit.appendPlainText("未检测到与工作范围相交的 subswath，请检查 SLC 目录与范围或手动填写。")
            QMessageBox.information(self, "自动计算 Swaths", "未检测到与工作范围相交的 subswath，请检查 SLC 目录与范围，或手动填写（如 1 2 3）。")

    def _on_dem_make(self) -> None:
        """打开 DEM 制作面板，预填工作范围（S/N/W/E）与 SLC 路径（用于根据 Swath 更新 DEM 范围）。"""
        def _parse_float(text: str):
            t = (text or "").strip().replace("—", "").strip()
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                return None
        extent_s = _parse_float(self.bbox_s.text())
        extent_n = _parse_float(self.bbox_n.text())
        extent_w = _parse_float(self.bbox_w.text())
        extent_e = _parse_float(self.bbox_e.text())
        safe_path = self.slc_dir_edit.text().strip()
        if safe_path and os.path.isdir(safe_path):
            try:
                from backend.services.s1_processing_service import resolve_safe_paths
                paths = resolve_safe_paths(safe_path)
                if paths:
                    safe_path = paths[0]
            except Exception:
                safe_path = ""
        from .dem_make_dialog import DemMakeDialog
        dlg = DemMakeDialog(
            self,
            extent_south=extent_s,
            extent_north=extent_n,
            extent_west=extent_w,
            extent_east=extent_e,
            safe_path=safe_path or None,
        )
        dlg.dem_succeeded.connect(self._on_dem_make_succeeded)
        dlg.show()

    @Slot(str)
    def _on_dem_make_succeeded(self, dem_path: str) -> None:
        """DEM 制作成功后：填入 DEM 输入框并保存到工程文件。"""
        self.dem_edit.setText(dem_path)
        self._save_to_project()

    def _on_init(self) -> None:
        req = self._get_request_dict()
        if not req:
            return
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self._set_form_enabled(False)
        self._worker = StackInitWorker(req, self)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.finished_with_result.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, pct: float, msg: str) -> None:
        self.progress_bar.setValue(int(pct))
        self.log_edit.appendPlainText(msg)

    def _on_work_dir_changed(self) -> None:
        self.open_flow_btn.setEnabled(bool(self.work_dir_edit.text().strip()))

    def _on_finished(self, result: dict) -> None:
        self._set_form_enabled(True)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if result.get("success"):
            self._last_work_dir = result.get("work_dir")
            self.open_flow_btn.setEnabled(True)
            self._save_to_project()
            self.init_succeeded.emit(self._last_work_dir or "")
            QMessageBox.information(self, "初始化完成", "流程清单已生成，可点击「打开流程界面」查看步骤并运行。")
        else:
            self.open_flow_btn.setEnabled(bool(self.work_dir_edit.text().strip()))
            err_msg = result.get("error_message", "未知错误")
            log_file = result.get("log_file")
            self.log_edit.appendPlainText("--- 错误详情 ---")
            self.log_edit.appendPlainText(err_msg)
            if log_file:
                self.log_edit.appendPlainText("")
                self.log_edit.appendPlainText(f"详细日志已保存到: {log_file}")
            msg = err_msg if len(err_msg) <= 500 else err_msg[:500] + "\n\n… 详细见下方日志"
            if log_file:
                msg += f"\n\n详细日志文件: {log_file}"
            QMessageBox.warning(self, "初始化失败", msg)

    def _on_open_flow(self) -> None:
        if self._last_work_dir:
            self.init_succeeded.emit(self._last_work_dir)
        else:
            work_dir = self.work_dir_edit.text().strip()
            if work_dir:
                self.init_succeeded.emit(work_dir)
            else:
                QMessageBox.warning(self, "打开流程", "请先指定工作目录并完成初始化，或选择已有 pipeline.json 的工作目录。")

    def get_work_dir(self) -> str | None:
        """返回当前工作目录（用于打开流程界面）。"""
        return self._last_work_dir or self.work_dir_edit.text().strip() or None
