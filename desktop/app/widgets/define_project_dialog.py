"""
定义新工程对话框。与 Web 端 DefineProjectModal 交互逻辑一致：
工程名称、雷达数据类型、项目路径（须 Windows 绝对路径）；桌面端用 QFileDialog 获取完整路径。
"""
from __future__ import annotations

import re
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

from ..icons import icon_open_folder, icon_new_folder, icon_cancel

# 与 Web 端一致
RADAR_TYPES = [("Sentinel-1", "Sentinel-1")]


def is_windows_absolute_path(path: str) -> bool:
    """是否为 Windows 绝对路径（盘符 + 冒号 + 反斜杠/斜杠）。"""
    s = path.strip().replace("\\", "/")
    return bool(re.match(r"^[a-zA-Z]:/", s))


class DefineProjectDialog(QDialog):
    """定义新工程对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("定义新工程")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()
        self._errors: dict[str, str] = {}
        self._result: dict | None = None

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题区（与 Web 端 Header 一致）
        header = QFrame()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 12)
        title = QLabel("定义新工程")
        title.setObjectName("dialogTitle")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("配置工程参数以开始雷达数据处理")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # 工程名称
        layout.addWidget(QLabel("工程名称"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("请输入工程名称...")
        self.name_edit.setObjectName("nameEdit")
        layout.addWidget(self.name_edit)
        self.name_error = QLabel()
        self.name_error.setObjectName("errorLabel")
        self.name_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.name_error.setVisible(False)
        layout.addWidget(self.name_error)

        # 雷达数据类型
        layout.addWidget(QLabel("雷达数据类型"))
        self.radar_combo = QComboBox()
        self.radar_combo.setPlaceholderText("选择雷达数据类型...")
        self.radar_combo.addItem("选择雷达数据类型...", "")
        for value, label in RADAR_TYPES:
            self.radar_combo.addItem(label, value)
        self.radar_combo.setCurrentIndex(0)
        layout.addWidget(self.radar_combo)
        self.radar_error = QLabel()
        self.radar_error.setObjectName("radarErrorLabel")
        self.radar_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.radar_error.setVisible(False)
        layout.addWidget(self.radar_error)

        # 项目路径（桌面端可原生选择文件夹，获得完整路径）
        layout.addWidget(QLabel("项目路径"))
        path_hint = QLabel("须为 Windows 绝对路径（如 D:\\文件夹\\项目名）。可使用「选择文件夹」获取完整路径。")
        path_hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        path_hint.setWordWrap(True)
        layout.addWidget(path_hint)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("D:\\文件夹\\项目名（须为 Windows 绝对路径）")
        self.path_edit.setObjectName("pathEdit")
        path_row.addWidget(self.path_edit)
        self.browse_btn = QPushButton(icon_open_folder(), "选择文件夹")
        self.browse_btn.setObjectName("browseBtn")
        self.browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)
        self.path_error = QLabel()
        self.path_error.setObjectName("pathErrorLabel")
        self.path_error.setStyleSheet("color: #f87171; font-size: 12px;")
        self.path_error.setVisible(False)
        layout.addWidget(self.path_error)

        # 底部按钮
        layout.addSpacing(8)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton(icon_cancel(), "取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.create_btn = QPushButton(icon_new_folder(), "新建工程")
        self.create_btn.setObjectName("primaryButton")
        self.create_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.create_btn)
        layout.addLayout(btn_layout)

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目所在文件夹")
        if path:
            self.path_edit.setText(path)
            self._clear_error("projectPath")

    def _clear_error(self, field: str):
        self._errors.pop(field, None)
        self.name_error.setVisible(False)
        self.radar_error.setVisible(False)
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

    def _on_submit(self):
        if not self._validate():
            return
        self.create_btn.setEnabled(False)
        self.create_btn.setText("创建中…")
        try:
            from ..project_store import create_project_local
            node = create_project_local(
                name=self.name_edit.text().strip(),
                radar_type=self.radar_combo.currentData(),
                project_path=self.path_edit.text().strip(),
            )
            self._result = {
                "id": node["id"],
                "name": node["name"],
                "radar_type": node["radarType"],
                "project_path": node["projectPath"],
            }
            self.accept()
        except Exception as e:
            msg = str(e)
            if "绝对路径" in msg or "项目路径" in msg:
                self._errors["projectPath"] = msg
                self._show_errors()
            else:
                QMessageBox.critical(self, "新建工程失败", msg)
        finally:
            self.create_btn.setEnabled(True)
            self.create_btn.setText("新建工程")

    def get_result(self) -> dict | None:
        """创建成功后返回 { id, name, radar_type, project_path }。"""
        return getattr(self, "_result", None)
