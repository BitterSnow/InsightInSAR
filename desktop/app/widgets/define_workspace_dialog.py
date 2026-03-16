"""
定义工作区对话框：方式1 输入 N/S/W/E；方式2 上传 Shapefile 或 KML 自动填充四至。
保存时校验坐标并写入工程 .md 文件。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QMessageBox,
    QFileDialog,
    QGroupBox,
    QGridLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ..icons import icon_open_folder, icon_save, icon_cancel
from ..project_file import (
    WORKSPACE_SECTION,
    find_project_path,
    load_project_md_full,
    write_project,
    validate_workspace_coords,
)
from ..workspace_bbox import read_bbox_from_file


class DefineWorkspaceDialog(QDialog):
    """定义工作区：N/S/W/E 或从 Shapefile/KML 导入。"""

    def __init__(self, parent=None, node: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("定义工作区")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._node = node or {}
        self._saved_bbox: tuple[float, float, float, float] | None = None
        self._build_ui()
        self._load_current_workspace()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 12)
        title = QLabel("定义工作区")
        title.setObjectName("dialogTitle")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("输入四至坐标，或从 Shapefile/KML 文件导入")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # 方式1：N/S/W/E
        group1 = QGroupBox("方式 1：输入经纬度坐标")
        grid = QGridLayout()
        grid.addWidget(QLabel("北纬 (N)："), 0, 0)
        self.n_edit = QLineEdit()
        self.n_edit.setPlaceholderText("例如 31.5")
        grid.addWidget(self.n_edit, 0, 1)
        grid.addWidget(QLabel("南纬 (S)："), 1, 0)
        self.s_edit = QLineEdit()
        self.s_edit.setPlaceholderText("例如 30.0")
        grid.addWidget(self.s_edit, 1, 1)
        grid.addWidget(QLabel("西经 (W)："), 2, 0)
        self.w_edit = QLineEdit()
        self.w_edit.setPlaceholderText("例如 103.0")
        grid.addWidget(self.w_edit, 2, 1)
        grid.addWidget(QLabel("东经 (E)："), 3, 0)
        self.e_edit = QLineEdit()
        self.e_edit.setPlaceholderText("例如 104.0")
        grid.addWidget(self.e_edit, 3, 1)
        group1.setLayout(grid)
        layout.addWidget(group1)

        # 方式2：上传文件
        group2 = QGroupBox("方式 2：上传 Shapefile 或 KML")
        row = QHBoxLayout()
        self.file_btn = QPushButton(icon_open_folder(), "选择 Shapefile 或 KML 文件")
        self.file_btn.clicked.connect(self._on_select_file)
        row.addWidget(self.file_btn)
        self.file_label = QLabel("未选择文件")
        self.file_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        row.addWidget(self.file_label, 1)
        group2.setLayout(row)
        layout.addWidget(group2)

        self.coord_error = QLabel()
        self.coord_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.coord_error.setVisible(False)
        layout.addWidget(self.coord_error)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton(icon_cancel(), "取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton(icon_save(), "保存")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def _load_current_workspace(self) -> None:
        """从当前工程文件（.yaml / .md）读取已有工作区并填入。"""
        pid = self._node.get("id")
        pdir = self._node.get("projectPath")
        if not pid or not pdir:
            return
        project_path = find_project_path(pdir, pid)
        if not project_path:
            return
        data = load_project_md_full(project_path)
        if not data:
            return
        # 优先从 workspace 字典取（YAML）；否则从「工作区」字符串取
        ws = data.get("workspace")
        if isinstance(ws, dict) and all(k in ws for k in ("n", "s", "w", "e")):
            n, s, w, e = ws["n"], ws["s"], ws["w"], ws["e"]
            self.n_edit.setText(f"{float(n):.2f}")
            self.s_edit.setText(f"{float(s):.2f}")
            self.w_edit.setText(f"{float(w):.2f}")
            self.e_edit.setText(f"{float(e):.2f}")
            return
        raw = (data.get(WORKSPACE_SECTION) or "").strip()
        if not raw:
            return
        parts = [p.strip() for p in raw.replace("，", ",").split(",")]
        if len(parts) >= 4:
            self.n_edit.setText(parts[0])
            self.s_edit.setText(parts[1])
            self.w_edit.setText(parts[2])
            self.e_edit.setText(parts[3])

    def _on_select_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Shapefile 或 KML 文件",
            "",
            "Shapefile (*.shp);;KML (*.kml);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            n, s, w, e = read_bbox_from_file(path)
            self.n_edit.setText(f"{n}")
            self.s_edit.setText(f"{s}")
            self.w_edit.setText(f"{w}")
            self.e_edit.setText(f"{e}")
            self.file_label.setText(Path(path).name)
            self.coord_error.setVisible(False)
        except ValueError as e:
            self.file_label.setText("未选择文件")
            self.coord_error.setText(str(e))
            self.coord_error.setVisible(True)
            QMessageBox.warning(self, "读取文件失败", str(e))

    def _get_coords(self) -> tuple[float, float, float, float] | None:
        """从输入框解析 N,S,W,E，非法时返回 None 并显示错误。"""
        self.coord_error.setVisible(False)
        try:
            n = float(self.n_edit.text().strip())
            s = float(self.s_edit.text().strip())
            w = float(self.w_edit.text().strip())
            e = float(self.e_edit.text().strip())
        except ValueError:
            self.coord_error.setText("请输入有效的数字（北纬、南纬、西经、东经）")
            self.coord_error.setVisible(True)
            return None
        ok, err = validate_workspace_coords(n, s, w, e)
        if not ok:
            self.coord_error.setText(err)
            self.coord_error.setVisible(True)
            return None
        return (n, s, w, e)

    def _on_save(self) -> None:
        coords = self._get_coords()
        if coords is None:
            return
        n, s, w, e = coords
        pid = self._node.get("id")
        pdir = self._node.get("projectPath")
        if not pid or not pdir:
            QMessageBox.warning(self, "保存失败", "缺少项目信息")
            return
        project_path = find_project_path(pdir, pid)
        if not project_path:
            QMessageBox.warning(self, "保存失败", "未找到该工程的项目文件")
            return
        data = load_project_md_full(project_path)
        if not data:
            QMessageBox.warning(self, "保存失败", "无法读取工程文件")
            return
        # 同时写入兼容键「工作区」与 YAML 的 workspace 字典，否则 YAML 写入时仍会用旧的 data["workspace"]
        data[WORKSPACE_SECTION] = f"{n},{s},{w},{e}"
        data["workspace"] = {"n": round(n, 2), "s": round(s, 2), "w": round(w, 2), "e": round(e, 2)}
        try:
            write_project(project_path, data)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        self._saved_bbox = (n, s, w, e)
        self.accept()
