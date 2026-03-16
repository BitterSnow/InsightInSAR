"""
数据导入对话框：配置 InSARTaskRequest。
优先用 isce2-build 子进程执行 ISCE2（避免与 PySide6 同进程 DLL 冲突），
否则在同进程 QThread 中调用 run_s1_import_from_request。
支持将数据目录和参数保存到工程 .md 文件。
"""
from __future__ import annotations

import logging
import os
import json
import subprocess
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
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont


class _SubswathDetectWorker(QThread):
    """后台根据 bbox_snwe 与 SAFE 路径检测需处理的 subswath，并返回详细信息供日志展示。"""
    finished_with_swaths = Signal(list)  # [1, 2] 或 []
    finished_with_details = Signal(list, object)  # (swaths, details_dict)

    def __init__(self, zip_or_safe_path: str, bbox_snwe: list[float], parent=None):
        super().__init__(parent)
        self._path = zip_or_safe_path
        self._bbox_snwe = bbox_snwe

    def run(self) -> None:
        try:
            from backend.services.s1_processing_service import resolve_safe_paths
            safe_list = resolve_safe_paths(self._path)
            logging.debug(
                "根据处理范围自动填充 Swath: 路径=%s, resolve_safe_paths 返回 %d 项",
                self._path,
                len(safe_list),
            )
            if not safe_list:
                logging.warning(
                    "根据处理范围自动填充 Swath: 未解析到任何 SAFE（路径=%s），请确认选择的是 .zip 或含 .SAFE 的目录。",
                    self._path,
                )
                self.finished_with_swaths.emit([])
                self.finished_with_details.emit([], {})
                return
            try:
                from backend.scripts.subswath_detector import detect_subswaths_with_details
                details = detect_subswaths_with_details(safe_list[0], bbox_snwe=self._bbox_snwe)
                swaths = details.get("swaths") or []
            except Exception as e:
                logging.exception(
                    "根据处理范围自动填充 Swath: detect_subswaths_with_details 失败，已回退到 detect_subswaths。"
                )
                from backend.scripts.subswath_detector import detect_subswaths
                swaths = detect_subswaths(safe_list[0], bbox_snwe=self._bbox_snwe)
                s, n, w, e = self._bbox_snwe
                details = {
                    "swaths": swaths,
                    "date": "",
                    "input_nwse": (n, w, s, e),
                    "swath_footprints_nwse": {},
                    "intersection": {},
                }
            self.finished_with_swaths.emit(swaths)
            self.finished_with_details.emit(swaths, details)
        except Exception:
            logging.exception("根据处理范围自动填充 Swath: 检测失败（SAFE 未解析或依赖缺失）。")
            self.finished_with_swaths.emit([])
            self.finished_with_details.emit([], {})


def _path_field_with_browse(
    line: QLineEdit,
    browse_caption: str,
    is_file: bool = False,
) -> QWidget:
    """返回「输入框 + 浏览按钮」的横向组合，用于表单行左侧对齐。"""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    h.addWidget(line, 1)
    btn = QPushButton("浏览…")
    if is_file:
        btn.clicked.connect(lambda: _browse_file(line, browse_caption))
    else:
        btn.clicked.connect(lambda: _browse_dir(line, browse_caption))
    h.addWidget(btn)
    return w


def _browse_dir(edit: QLineEdit, caption: str) -> None:
    path = QFileDialog.getExistingDirectory(None, caption)
    if path:
        edit.setText(path)


def _browse_file(edit: QLineEdit, caption: str) -> None:
    path, _ = QFileDialog.getOpenFileName(None, caption, "", "ZIP (*.zip);;所有文件 (*.*)")
    if path:
        edit.setText(path)


def _set_extent_2decimals(dlg: "S1ImportDialog", workspace: str) -> None:
    """解析工作区字符串 N,S,W,E，填入处理范围四格并格式化为 2 位小数。"""
    def set_blank() -> None:
        dlg.extent_w.setText("")
        dlg.extent_n.setText("")
        dlg.extent_s.setText("")
        dlg.extent_e.setText("")

    if not workspace:
        set_blank()
        return
    parts = [p.strip() for p in workspace.split(",")]
    if len(parts) != 4:
        set_blank()
        return
    try:
        n, s, w, e = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
        dlg.extent_w.setText(f"{w:.2f}")
        dlg.extent_n.setText(f"{n:.2f}")
        dlg.extent_s.setText(f"{s:.2f}")
        dlg.extent_e.setText(f"{e:.2f}")
    except (ValueError, TypeError):
        set_blank()


def _get_isce2_subprocess_bat():
    """若存在 isce2-build、ISCE2 packages 与 subprocess.bat，返回 (bat_path, root)；否则 (None, None)。"""
    root = os.environ.get("INSAR_PROJECT_ROOT") or str(Path(__file__).resolve().parents[2])
    packages = os.path.join(root, "lib", "isce2-main", "install", "packages")
    bat = os.path.join(root, "scripts", "run_s1_import_subprocess.bat")
    for conda_python in [
        r"D:\env\miniconda3\envs\isce2-build\python.exe",
        r"C:\ProgramData\Anaconda3\envs\isce2-build\python.exe",
    ]:
        if os.path.isfile(conda_python) and os.path.isdir(packages) and os.path.isfile(bat):
            return bat, root
    return None, None


class S1ImportWorker(QThread):
    """在后台线程执行 S1 导入：优先 isce2-build 子进程，否则同进程调用。"""
    progress_updated = Signal(float, str)
    finished_with_result = Signal(dict)

    def __init__(self, request_dict: dict, parent=None):
        super().__init__(parent)
        self._request_dict = request_dict

    def run(self):
        bat_path, root = _get_isce2_subprocess_bat()
        if bat_path and root:
            self._run_subprocess_bat(bat_path, root)
        else:
            self._run_in_process()

    def _run_subprocess_bat(self, bat_path: str, cwd: str) -> None:
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                f.write(json.dumps(self._request_dict) + "\n")
                req_file = f.name
            try:
                proc = subprocess.Popen(
                    ["cmd", "/c", bat_path, req_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                for line in proc.stdout:
                    line = line.rstrip("\n\r")
                    if line.startswith("PROGRESS\t"):
                        parts = line.split("\t", 2)
                        if len(parts) >= 3:
                            try:
                                pct = float(parts[1])
                                self.progress_updated.emit(pct, parts[2])
                            except ValueError:
                                pass
                    elif line.startswith("RESULT\t"):
                        try:
                            result = json.loads(line[7:])
                            self.finished_with_result.emit(result)
                        except json.JSONDecodeError:
                            self.finished_with_result.emit({"success": False, "error_message": "Invalid result line"})
                        return
                proc.wait()
                if proc.returncode != 0:
                    self.finished_with_result.emit({"success": False, "error_message": f"Subprocess exited with {proc.returncode}. Ensure isce2-build env and ISCE2 packages are correct (see docs/windows-phase4.md)."})
            finally:
                try:
                    os.unlink(req_file)
                except OSError:
                    pass
        except Exception as e:
            self.progress_updated.emit(0.0, f"错误: {e}")
            self.finished_with_result.emit({"success": False, "slc_vrt_paths": [], "metadata": {}, "error_message": str(e)})

    def _run_in_process(self) -> None:
        try:
            from shared_models import InSARTaskRequest
            from backend.services.s1_processing_service import run_s1_import_from_request
            request = InSARTaskRequest.model_validate(self._request_dict)

            def progress_cb(pct: float, msg: str) -> None:
                self.progress_updated.emit(pct, msg)

            result = run_s1_import_from_request(request, progress_callback=progress_cb)
            self.finished_with_result.emit(result)
        except Exception as e:
            err_msg = str(e)
            self.progress_updated.emit(0.0, f"错误: {err_msg}")
            if "DLL load failed" in err_msg or "StdOEL" in err_msg or "ISCE2 not available" in err_msg:
                err_msg = (
                    "无法加载 ISCE2。若使用 WSL 模式，请设置 INSAR_USE_WSL=1 并确保 WSL 内已配置 ISCE2（见 docs/wsl_ubuntu24_isce2_setup.md）；"
                    "否则请确保已安装 isce2-build 环境或使用脚本启动桌面。"
                )
            self.finished_with_result.emit({
                "success": False,
                "slc_vrt_paths": [],
                "metadata": {},
                "error_message": err_msg,
            })


class S1ImportDialog(QDialog):
    """数据导入配置与执行对话框。"""

    def __init__(
        self,
        parent=None,
        default_project_path: str | None = None,
        project_node: dict | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("数据导入")
        self.setMinimumSize(560, 520)
        self.setModal(False)
        self._default_project_path = default_project_path or ""
        self._project_node = project_node
        self._worker: S1ImportWorker | None = None
        self._build_ui()
        self._prefill_from_project()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(12)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        title = QLabel("数据导入")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("选择 SAFE 数据、轨道、DEM 等，直接在本机执行 ISCE2 导入。")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        scroll_layout.addWidget(header)

        grp = QGroupBox("路径与参数")
        grp_layout = QFormLayout(grp)
        grp_layout.setHorizontalSpacing(12)
        grp_layout.setVerticalSpacing(10)
        grp_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        # 统一标签列宽，使所有输入框左侧对齐
        grp_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.zip_edit = QLineEdit()
        self.zip_edit.setPlaceholderText("SAFE 数据所在目录（解压后的 .SAFE 或含 .SAFE 的目录）")
        grp_layout.addRow("SAFE 目录:", _path_field_with_browse(self.zip_edit, "选择 SAFE 目录"))
        self.orbit_edit = QLineEdit()
        self.orbit_edit.setPlaceholderText("轨道 EOF 文件所在目录")
        grp_layout.addRow("轨道目录:", _path_field_with_browse(self.orbit_edit, "选择轨道目录"))
        self.dem_edit = QLineEdit()
        self.dem_edit.setPlaceholderText("DEM 文件路径（WGS84）")
        browse_dem = QPushButton("浏览…")
        def browse_dem_file():
            path, _ = QFileDialog.getOpenFileName(None, "选择 DEM 文件", "", "DEM/GeoTIFF (*.tif *.tiff *.dem);;所有文件 (*.*)")
            if path:
                self.dem_edit.setText(path)
        browse_dem.clicked.connect(browse_dem_file)
        dem_make_btn = QPushButton("DEM制作")
        dem_make_btn.setToolTip("在 WSL 内调用 ISCE2 dem.py 拼接 SRTM DEM")
        dem_make_btn.clicked.connect(self._on_dem_make)
        dem_row = QWidget()
        dem_h = QHBoxLayout(dem_row)
        dem_h.setContentsMargins(0, 0, 0, 0)
        dem_h.setSpacing(8)
        dem_h.addWidget(self.dem_edit, 1)
        dem_h.addWidget(browse_dem)
        dem_h.addWidget(dem_make_btn)
        grp_layout.addRow("DEM:", dem_row)
        self.aux_edit = QLineEdit()
        self.aux_edit.setPlaceholderText("Aux 产品目录（cal/noise 等）")
        grp_layout.addRow("Aux 目录:", _path_field_with_browse(self.aux_edit, "选择 Aux 目录"))

        _extent_style = "background-color: #f1f5f9; color: #475569; min-width: 52px;"
        self.extent_w = QLineEdit()
        self.extent_w.setReadOnly(True)
        self.extent_w.setPlaceholderText("-")
        self.extent_w.setStyleSheet(_extent_style)
        self.extent_n = QLineEdit()
        self.extent_n.setReadOnly(True)
        self.extent_n.setPlaceholderText("-")
        self.extent_n.setStyleSheet(_extent_style)
        self.extent_s = QLineEdit()
        self.extent_s.setReadOnly(True)
        self.extent_s.setPlaceholderText("-")
        self.extent_s.setStyleSheet(_extent_style)
        self.extent_e = QLineEdit()
        self.extent_e.setReadOnly(True)
        self.extent_e.setPlaceholderText("-")
        self.extent_e.setStyleSheet(_extent_style)
        extent_row = QHBoxLayout()
        extent_row.setSpacing(8)
        extent_row.addWidget(QLabel("W:"))
        extent_row.addWidget(self.extent_w)
        ns_stack = QVBoxLayout()
        n_row = QHBoxLayout()
        n_row.addWidget(QLabel("N:"))
        n_row.addWidget(self.extent_n)
        ns_stack.addLayout(n_row)
        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("S:"))
        s_row.addWidget(self.extent_s)
        ns_stack.addLayout(s_row)
        ns_widget = QWidget()
        ns_widget.setLayout(ns_stack)
        extent_row.addWidget(ns_widget)
        extent_row.addWidget(QLabel("E:"))
        extent_row.addWidget(self.extent_e)
        extent_row.addStretch()
        extent_widget = QWidget()
        extent_widget.setLayout(extent_row)
        grp_layout.addRow("处理范围:", extent_widget)

        self.swath_edit = QLineEdit()
        self.swath_edit.setText("1 2 3")
        self.swath_edit.setPlaceholderText("由处理范围自动填充或手动输入，如 1 2 3")
        self.pol_combo = QComboBox()
        self.pol_combo.addItems(["vv", "vh"])
        self.auto_swath_btn = QPushButton("根据处理范围自动填充")
        self.auto_swath_btn.setToolTip("根据上方处理范围（N/S/W/E）与 SAFE 数据自动检测需处理的 Swath，并填入本栏")
        self.auto_swath_btn.clicked.connect(self._on_auto_fill_swaths)
        swath_row = QHBoxLayout()
        swath_row.setSpacing(8)
        swath_row.addWidget(self.swath_edit)
        swath_row.addWidget(self.auto_swath_btn)
        swath_row.addWidget(QLabel("极化"))
        swath_row.addWidget(self.pol_combo)
        swath_row.addStretch()
        swath_widget = QWidget()
        swath_widget.setLayout(swath_row)
        grp_layout.addRow("Swaths:", swath_widget)
        scroll_layout.addWidget(grp)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        scroll_layout.addWidget(QLabel("进度"))
        scroll_layout.addWidget(self.progress_bar)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(120)
        self.log_edit.setPlaceholderText("执行日志…")
        scroll_layout.addWidget(QLabel("日志"))
        scroll_layout.addWidget(self.log_edit)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_to_project_btn = QPushButton("保存到工程")
        self.save_to_project_btn.clicked.connect(self._on_save_to_project)
        self.save_to_project_btn.setVisible(bool(self._project_node))
        btn_layout.addWidget(self.save_to_project_btn)
        self.start_btn = QPushButton("开始导入")
        self.start_btn.clicked.connect(self._on_start)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _prefill_from_project(self) -> None:
        """根据工程 .md 中已定义的各类文件路径预填表单，无需再次选择文件。"""
        if not self._project_node:
            return
        from ..project_file import find_project_path, load_project_md_full

        pdir = self._project_node.get("projectPath") or ""
        pid = self._project_node.get("id") or ""
        if not pdir or not pid:
            return
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            return
        data = load_project_md_full(project_path)
        if not data:
            return
        workspace = (data.get("工作区") or "").strip()
        _set_extent_2decimals(self, workspace)
        self.zip_edit.setText((data.get("SAFE ZIP路径") or "").strip())
        self.orbit_edit.setText((data.get("轨道目录") or "").strip())
        self.dem_edit.setText((data.get("DEM路径") or "").strip())
        self.aux_edit.setText((data.get("Aux目录") or "").strip())
        if (data.get("Swaths") or "").strip():
            self.swath_edit.setText((data.get("Swaths") or "").strip())
        if (data.get("极化") or "").strip():
            idx = self.pol_combo.findText((data.get("极化") or "").strip())
            if idx >= 0:
                self.pol_combo.setCurrentIndex(idx)

    def _on_dem_make(self) -> None:
        """打开 DEM 制作面板，预填处理范围与 SAFE 路径（用于根据 Swath 更新 DEM 范围）。"""
        def _parse_float(text: str) -> float | None:
            t = (text or "").strip().replace("—", "").strip()
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                return None
        extent_s = _parse_float(self.extent_s.text())
        extent_n = _parse_float(self.extent_n.text())
        extent_w = _parse_float(self.extent_w.text())
        extent_e = _parse_float(self.extent_e.text())
        safe_path = self.zip_edit.text().strip()
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

    def _on_dem_make_succeeded(self, dem_path: str) -> None:
        """DEM 制作成功后：同步到数据导入界面的 DEM 输入框，并写入当前工程文件。"""
        self.dem_edit.setText(dem_path)
        if not self._project_node:
            return
        from ..project_file import (
            find_project_path,
            load_project_md_full,
            write_project,
            REQUIRED_SECTIONS,
        )
        pdir = self._project_node.get("projectPath") or ""
        pid = self._project_node.get("id") or ""
        if not pdir or not pid:
            return
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            return
        data = load_project_md_full(project_path)
        if not data or set(REQUIRED_SECTIONS) - set(data.keys()):
            return
        data["DEM路径"] = dem_path
        try:
            write_project(project_path, data)
        except Exception:
            pass

    def _on_save_to_project(self) -> None:
        """将当前数据目录和参数写入工程 .md 文件。"""
        if not self._project_node:
            return
        from ..project_file import (
            find_project_path,
            load_project_md_full,
            write_project,
            REQUIRED_SECTIONS,
        )
        pdir = self._project_node.get("projectPath") or ""
        pid = self._project_node.get("id") or ""
        if not pdir or not pid:
            QMessageBox.warning(self, "保存失败", "缺少工程路径或 id。")
            return
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            QMessageBox.warning(self, "保存失败", "未找到该工程的项目文件。")
            return
        data = load_project_md_full(project_path)
        if not data or set(REQUIRED_SECTIONS) - set(data.keys()):
            QMessageBox.warning(self, "保存失败", "无法读取工程文件或格式不符。")
            return
        data["SAFE ZIP路径"] = self.zip_edit.text().strip()
        data["轨道目录"] = self.orbit_edit.text().strip()
        data["DEM路径"] = self.dem_edit.text().strip()
        data["Aux目录"] = self.aux_edit.text().strip()
        data["Swaths"] = self.swath_edit.text().strip() or "1 2 3"
        data["极化"] = self.pol_combo.currentText()
        try:
            write_project(project_path, data)
            QMessageBox.information(self, "保存成功", "数据目录和参数已保存到工程文件。")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _set_form_enabled(self, enabled: bool) -> None:
        self.zip_edit.setEnabled(enabled)
        self.orbit_edit.setEnabled(enabled)
        self.dem_edit.setEnabled(enabled)
        self.aux_edit.setEnabled(enabled)
        self.swath_edit.setEnabled(enabled)
        self.pol_combo.setEnabled(enabled)
        if hasattr(self, "auto_swath_btn"):
            self.auto_swath_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        if hasattr(self, "save_to_project_btn"):
            self.save_to_project_btn.setEnabled(enabled)

    def _get_bbox_snwe_from_extent(self) -> list[float] | None:
        """从处理范围四格读取 N,S,W,E，返回 [South, North, West, East] 或 None。"""
        try:
            n = float(self.extent_n.text().strip())
            s = float(self.extent_s.text().strip())
            w = float(self.extent_w.text().strip())
            e = float(self.extent_e.text().strip())
            return [s, n, w, e]
        except (ValueError, TypeError):
            return None

    def _on_auto_fill_swaths(self) -> None:
        """根据处理范围与 SAFE 路径检测需处理的 subswath，并填入 Swaths，同时保存到工程 .md 文件。"""
        zip_path = self.zip_edit.text().strip()
        bbox = self._get_bbox_snwe_from_extent()
        if not zip_path:
            QMessageBox.warning(self, "自动填充 Swaths", "请先填写 SAFE 目录。")
            return
        if not bbox or len(bbox) != 4:
            QMessageBox.warning(self, "自动填充 Swaths", "请先确保处理范围（N/S/W/E）四格已填写有效数字。")
            return
        self.auto_swath_btn.setEnabled(False)
        self.log_edit.appendPlainText("正在根据处理范围检测 subswath…")
        worker = _SubswathDetectWorker(zip_path, bbox, self)
        worker.finished_with_details.connect(self._on_auto_fill_swaths_done)
        worker.start()

    def _save_swaths_to_project(self, swaths_str: str) -> None:
        """将 Swaths 保存到工程文件。"""
        if not self._project_node:
            return
        from ..project_file import (
            find_project_path,
            load_project_md_full,
            write_project,
            REQUIRED_SECTIONS,
        )
        pdir = self._project_node.get("projectPath") or ""
        pid = self._project_node.get("id") or ""
        if not pdir or not pid:
            return
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            return
        data = load_project_md_full(project_path)
        if not data or set(REQUIRED_SECTIONS) - set(data.keys()):
            return
        data["Swaths"] = swaths_str
        try:
            write_project(project_path, data)
        except Exception:
            pass

    @Slot(list, object)
    def _on_auto_fill_swaths_done(self, swaths: list, details: dict) -> None:
        self.auto_swath_btn.setEnabled(True)
        # 先输出详细信息到日志栏（再输出“已填充”或“未检测到”）
        self._append_swath_detect_log(swaths, details)
        if swaths:
            swaths_str = " ".join(map(str, swaths))
            self.swath_edit.setText(swaths_str)
            self.log_edit.appendPlainText(f"已根据处理范围自动填充 Swaths: {swaths}")
            self._save_swaths_to_project(swaths_str)
        else:
            self.log_edit.appendPlainText("未检测到与处理范围相交的 subswath，请检查范围或手动填写。")

    def _append_swath_detect_log(self, swaths: list, details: dict) -> None:
        """根据检测结果向日志栏追加详细信息（日期、影像范围、输入范围、判定）。"""
        def nwse_str(tup) -> str:
            if not tup or len(tup) != 4:
                return ""
            n, w, s, e = tup
            return f"N={n:.4f} W={w:.4f} S={s:.4f} E={e:.4f}"

        if not details:
            self.log_edit.appendPlainText(
                "（未获取到影像范围详情，可能因 SAFE 未解析或检测依赖缺失，如 geopandas/shapely）"
            )
            return

        date_str = (details.get("date") or "").strip()
        input_nwse = details.get("input_nwse")
        footprints_nwse = details.get("swath_footprints_nwse") or {}
        intersection = details.get("intersection") or {}

        for sid in sorted(footprints_nwse.keys()):
            fp = footprints_nwse[sid]
            if date_str:
                self.log_edit.appendPlainText(
                    f"{date_str} 的影像 Swath {sid} 空间范围为 {nwse_str(fp)}"
                )
            else:
                self.log_edit.appendPlainText(
                    f"影像 Swath {sid} 空间范围为 {nwse_str(fp)}"
                )
        if input_nwse:
            self.log_edit.appendPlainText(f"输入范围为 {nwse_str(input_nwse)}")
        if intersection:
            covered = [s for s in sorted(intersection.keys()) if intersection[s]]
            if not covered:
                self.log_edit.appendPlainText("判定：与监测范围不存在交集。")
            else:
                swath_list_str = "、".join(map(str, sorted(covered)))
                self.log_edit.appendPlainText(
                    f"判定：Swath {swath_list_str} 覆盖监测范围。"
                )

    def _on_start(self) -> None:
        zip_path = self.zip_edit.text().strip()
        orbit_dir = self.orbit_edit.text().strip()
        dem_path = self.dem_edit.text().strip()
        aux_dir = self.aux_edit.text().strip()
        if not zip_path or not orbit_dir or not dem_path or not aux_dir:
            QMessageBox.warning(self, "参数不完整", "请填写 SAFE 目录、轨道目录、DEM、Aux 目录。")
            return
        swaths = self.swath_edit.text().strip()
        if not swaths:
            QMessageBox.warning(
                self,
                "参数不完整",
                "请先点击「根据处理范围自动填充」按钮计算要处理的 Swaths，或手动输入 Swaths 编号。"
            )
            return
        pol = self.pol_combo.currentText()
        # 处理范围四坐标传入 ISCE 作为 bbox，避免处理范围过大消耗过多资源
        bbox_snwe = self._get_bbox_snwe_from_extent()
        # 有工程时，新数据统一放在工程 .md 的「项目完整路径」下的 processing/s1_import
        output_dir = None
        if self._project_node:
            pdir = (self._project_node.get("projectPath") or "").strip().replace("/", os.sep)
            if pdir:
                output_dir = os.path.join(pdir, "processing", "s1_import")
        request_dict = {
            "zip_path": zip_path,
            "orbit_dir": orbit_dir,
            "dem_path": dem_path,
            "aux_dir": aux_dir,
            "target_shp_path": None,
            "bbox_snwe": bbox_snwe if (bbox_snwe and len(bbox_snwe) == 4) else None,
            "swaths": swaths,
            "polarization": pol,
            "output_dir": output_dir,
        }
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self._set_form_enabled(False)
        self._worker = S1ImportWorker(request_dict, self)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.finished_with_result.connect(self._on_finished)
        self._worker.start()

    @Slot(float, str)
    def _on_progress(self, pct: float, msg: str) -> None:
        self.progress_bar.setValue(int(pct))
        self.log_edit.appendPlainText(f"[{int(pct)}%] {msg}")

    @Slot(dict)
    def _on_finished(self, result: dict) -> None:
        self._set_form_enabled(True)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        success = result.get("success", False)
        if success:
            paths = result.get("slc_vrt_paths", [])
            self.log_edit.appendPlainText("完成。输出：" + (", ".join(paths) if paths else "(无)"))
            # 导入成功后，更新工程 .md 文件添加 Step1_import 步骤
            self._add_step_to_project("Step1_import")
            QMessageBox.information(self, "导入完成", "数据导入已成功完成。")
        else:
            err = result.get("error_message", "未知错误")
            if "StdOEL" in err or "DLL load failed" in err:
                err = err + "\n\n建议：若曾用 Anaconda 的 isce2-build 编译 ISCE2，请保留该环境；脚本已优先使用 Anaconda。否则请用当前 Miniconda3 的 isce2-build 重新编译 ISCE2（见 docs/windows-phase3.md）。"
            self.log_edit.appendPlainText(f"失败：{err}")
            QMessageBox.critical(self, "导入失败", err)
    
    def _add_step_to_project(self, step_name: str) -> None:
        """将处理步骤添加到工程 .md 文件，并通知主窗口刷新树形结构。"""
        if not self._project_node:
            self.log_edit.appendPlainText("[调试] 无工程节点，跳过步骤添加")
            return
        from ..project_file import (
            find_project_path,
            load_project_md_full,
            write_project,
            REQUIRED_SECTIONS,
        )
        pdir = self._project_node.get("projectPath") or ""
        pid = self._project_node.get("id") or ""
        if not pdir or not pid:
            self.log_edit.appendPlainText(f"[调试] 工程路径或 ID 无效：pdir={pdir}, pid={pid}")
            return
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            self.log_edit.appendPlainText(f"[调试] 未找到项目文件：{pdir}, {pid}")
            return
        data = load_project_md_full(project_path)
        if not data or set(REQUIRED_SECTIONS) - set(data.keys()):
            self.log_edit.appendPlainText(f"[调试] 项目文件数据无效：{data is not None}")
            return
        # 读取已有步骤，避免重复添加
        existing_steps_str = data.get("处理步骤", "").strip()
        existing_steps = [s.strip() for s in existing_steps_str.replace(",", " ").split() if s.strip()]
        if step_name not in existing_steps:
            existing_steps.append(step_name)
            data["处理步骤"] = " ".join(existing_steps)
            try:
                write_project(project_path, data)
                self.log_edit.appendPlainText(f"[调试] 步骤已保存：{step_name}, 文件：{project_path}")
                # 通知主窗口刷新树形结构（如果主窗口提供了回调）
                if hasattr(self, "_on_step_added_callback"):
                    self._on_step_added_callback(self._project_node)
                    self.log_edit.appendPlainText("[调试] 已触发树形结构刷新回调")
                else:
                    self.log_edit.appendPlainText("[调试] 未找到回调函数")
            except Exception as e:
                self.log_edit.appendPlainText(f"[调试] 保存步骤失败：{e}")
        else:
            self.log_edit.appendPlainText(f"[调试] 步骤已存在，跳过：{step_name}")
