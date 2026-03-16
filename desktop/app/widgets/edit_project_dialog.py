"""
修改项目对话框。与新建工程同样式，预填当前项目信息，保存时同步更新 .md 文件。
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFrame,
    QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ..icons import icon_open_folder, icon_save, icon_cancel
from ..project_file import (
    WORKSPACE_SECTION,
    find_project_path,
    write_project,
    load_and_validate,
    validate_project_data,
    safe_md_filename,
)

RADAR_TYPES = [("Sentinel-1", "Sentinel-1")]


def is_windows_absolute_path(path: str) -> bool:
    s = path.strip().replace("\\", "/")
    return bool(re.match(r"^[a-zA-Z]:/", s))


class EditProjectDialog(QDialog):
    """修改项目对话框。预填项目信息，保存时更新 .md 文件。"""

    def __init__(self, parent=None, node: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("修改项目")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._node = node or {}
        self._md_data: dict[str, str] | None = None  # 从 .md 读出的完整数据（含建立时间）
        self._current_md_path: Path | None = None
        self._load_md_data()
        self._build_ui()
        self._errors: dict[str, str] = {}
        self._result: dict | None = None

    def _load_md_data(self) -> None:
        """根据 node 查找并读取工程文件（.yaml 或 .md），得到 建立时间 等。"""
        pid = self._node.get("id")
        pdir = self._node.get("projectPath")
        if not pid or not pdir:
            return
        self._current_md_path = find_project_path(Path(pdir), pid)
        if self._current_md_path:
            data, _ = load_and_validate(self._current_md_path)
            self._md_data = data

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题区（与新建工程一致）
        header = QFrame()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 12)
        title = QLabel("修改项目")
        title.setObjectName("dialogTitle")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("修改工程参数并保存到项目文件")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # 工程名称
        layout.addWidget(QLabel("工程名称"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("请输入工程名称...")
        self.name_edit.setText(self._node.get("name", ""))
        layout.addWidget(self.name_edit)
        self.name_error = QLabel()
        self.name_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.name_error.setVisible(False)
        layout.addWidget(self.name_error)

        # 雷达数据类型
        layout.addWidget(QLabel("雷达数据类型"))
        self.radar_combo = QComboBox()
        self.radar_combo.addItem("选择雷达数据类型...", "")
        for value, label in RADAR_TYPES:
            self.radar_combo.addItem(label, value)
        radar = self._node.get("radarType", "")
        idx = self.radar_combo.findData(radar)
        self.radar_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addWidget(self.radar_combo)
        self.radar_error = QLabel()
        self.radar_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.radar_error.setVisible(False)
        layout.addWidget(self.radar_error)

        # 项目路径
        layout.addWidget(QLabel("项目路径"))
        path_hint = QLabel("须为 Windows 绝对路径。可使用「选择文件夹」获取完整路径。")
        path_hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        path_hint.setWordWrap(True)
        layout.addWidget(path_hint)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("D:\\文件夹\\项目名")
        self.path_edit.setText(self._node.get("projectPath", ""))
        path_row.addWidget(self.path_edit)
        self.browse_btn = QPushButton(icon_open_folder(), "选择文件夹")
        self.browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)
        self.path_error = QLabel()
        self.path_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.path_error.setVisible(False)
        layout.addWidget(self.path_error)

        # 底部按钮
        layout.addSpacing(8)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton(icon_cancel(), "取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton(icon_save(), "保存工程")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目所在文件夹")
        if path:
            self.path_edit.setText(path)
            self._errors.pop("projectPath", None)
            self.path_error.setVisible(False)

    def _show_errors(self):
        self.name_error.setText(self._errors.get("name", ""))
        self.name_error.setVisible(bool(self._errors.get("name")))
        self.radar_error.setText(self._errors.get("radarType", ""))
        self.radar_error.setVisible(bool(self._errors.get("radarType")))
        self.path_error.setText(self._errors.get("projectPath", ""))
        self.path_error.setVisible(bool(self._errors.get("projectPath")))

    def _validate(self) -> bool:
        self._errors.clear()
        name = self.name_edit.text().strip()
        if not name:
            self._errors["name"] = "请输入工程名称"
        radar = self.radar_combo.currentData() if self.radar_combo.currentData() else ""
        if not radar:
            self._errors["radarType"] = "请选择雷达数据类型"
        path = self.path_edit.text().strip()
        if not path:
            self._errors["projectPath"] = "请指定项目路径"
        elif not is_windows_absolute_path(path):
            self._errors["projectPath"] = "请指定 Windows 绝对路径（例如：D:\\文件夹\\项目名）"
        self._show_errors()
        return len(self._errors) == 0

    def _on_save(self):
        if not self._validate():
            return
        name = self.name_edit.text().strip()
        radar = self.radar_combo.currentData()
        project_path = self.path_edit.text().strip()
        project_id = self._node.get("id", "")
        # 建立时间：沿用原 .md 中的，若无则用占位
        created_at = ""
        if self._md_data and "建立时间" in self._md_data:
            created_at = self._md_data["建立时间"].strip()
        if not created_at:
            created_at = "未知"

        data = {
            "项目名称": name,
            "项目id": project_id,
            "雷达数据类型": radar,
            "建立时间": created_at,
            "项目完整路径": project_path,
        }
        if self._md_data and WORKSPACE_SECTION in self._md_data:
            data[WORKSPACE_SECTION] = self._md_data[WORKSPACE_SECTION]
        ok, err = validate_project_data(data)
        if not ok:
            self._errors["projectPath"] = err
            self._show_errors()
            return

        self.save_btn.setEnabled(False)
        self.save_btn.setText("保存中…")
        try:
            new_dir = Path(project_path)
            new_file = new_dir / f"{safe_md_filename(name)}.yaml"
            write_project(new_file, data)
            # 若路径或名称变更，删除旧文件（避免同一项目多文件）
            if self._current_md_path and self._current_md_path.resolve() != new_file.resolve():
                try:
                    self._current_md_path.unlink()
                except OSError:
                    pass
            self._result = {
                "id": project_id,
                "name": name,
                "radarType": radar,
                "projectPath": project_path,
                "children": self._node.get("children", []),
            }
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
        finally:
            self.save_btn.setEnabled(True)
            self.save_btn.setText("保存工程")

    def get_result(self) -> dict | None:
        """保存成功后返回更新后的节点（id, name, radarType, projectPath, children）。"""
        return self._result
