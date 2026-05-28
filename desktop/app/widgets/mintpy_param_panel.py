"""
MintPy 参数配置面板：分层展示 smallbaselineApp.cfg 参数。

提供三标签页：
- 快速配置：核心参数（默认展开的分组）
- 高级设置：全部参数
- 原始文件：直接编辑配置文件
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QWidget,
    QScrollArea,
    QFrame,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QLineEdit,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from .mintpy_param_groups import PARAM_GROUPS, ParamGroup, ParamMeta, get_group_for_step
from .mintpy_param_widgets import ParamWidgetResult, create_param_widget


class MintPyParamPanel(QDialog):
    """MintPy 参数配置面板"""

    config_saved = Signal(str)  # 配置文件路径

    def __init__(
        self,
        work_dir: str,
        parent=None,
        focus_step: str | None = None,
    ):
        super().__init__(parent)
        self._work_dir = work_dir
        self._focus_step = focus_step
        self._cfg_path = os.path.join(work_dir, "smallbaselineApp.cfg")
        self._param_widgets: Dict[str, ParamWidgetResult] = {}
        self._group_boxes: Dict[str, QGroupBox] = {}  # group_id -> GroupBox (advanced tab)
        self._config_dict: Dict[str, str] = {}
        self._original_content: str = ""

        self.setWindowTitle("MintPy 参数配置")
        self.setMinimumSize(720, 520)
        self.resize(800, 600)
        self.setModal(False)

        self._load_config()
        self._build_ui()
        self._apply_values()

    # -----------------------------------------------------------------------
    # Config I/O
    # -----------------------------------------------------------------------
    def _load_config(self) -> None:
        """加载配置文件到字典"""
        if not os.path.isfile(self._cfg_path):
            return
        try:
            with open(self._cfg_path, "r", encoding="utf-8", errors="replace") as f:
                self._original_content = f.read()
            for line in self._original_content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                # Remove inline comment
                val = val.split("#")[0].strip()
                self._config_dict[key.strip()] = val.strip()
        except Exception as e:
            logging.exception("加载配置文件失败: %s", self._cfg_path)

    def _read_raw_config(self) -> str:
        if not os.path.isfile(self._cfg_path):
            return "# 配置文件不存在"
        try:
            with open(self._cfg_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return "# 无法读取配置文件"

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QFrame()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("MintPy 参数配置")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        subtitle = QLabel(f"配置文件: {self._cfg_path}")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 11px;")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # Main content: TabWidget
        self._tab_widget = QTabWidget()

        # Tab 1: Quick config (core groups only)
        quick_scroll = QScrollArea()
        quick_scroll.setWidgetResizable(True)
        quick_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        quick_widget = QWidget()
        self._quick_layout = QVBoxLayout(quick_widget)
        self._quick_layout.setSpacing(12)
        self._build_param_form(
            [g for g in PARAM_GROUPS if g.default_expanded],
            self._quick_layout,
        )
        self._quick_layout.addStretch()
        quick_scroll.setWidget(quick_widget)
        self._tab_widget.addTab(quick_scroll, "快速配置")

        # Tab 2: Advanced (all groups)
        self._advanced_scroll = QScrollArea()
        self._advanced_scroll.setWidgetResizable(True)
        self._advanced_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        advanced_widget = QWidget()
        self._advanced_layout = QVBoxLayout(advanced_widget)
        self._advanced_layout.setSpacing(12)
        self._build_param_form(PARAM_GROUPS, self._advanced_layout, record_groups=True)
        self._advanced_layout.addStretch()
        self._advanced_scroll.setWidget(advanced_widget)
        self._tab_widget.addTab(self._advanced_scroll, "高级设置")

        # Tab 3: Raw file editor
        raw_widget = QWidget()
        raw_layout = QVBoxLayout(raw_widget)
        self._raw_edit = QPlainTextEdit()
        self._raw_edit.setPlainText(self._original_content or self._read_raw_config())
        self._raw_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._raw_edit.setStyleSheet(
            "QPlainTextEdit { font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; }"
        )
        raw_layout.addWidget(self._raw_edit)

        raw_btn_layout = QHBoxLayout()
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self._on_reload_raw)
        raw_btn_layout.addWidget(reload_btn)
        raw_btn_layout.addStretch()
        raw_layout.addLayout(raw_btn_layout)

        self._tab_widget.addTab(raw_widget, "原始文件")

        layout.addWidget(self._tab_widget, 1)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        validate_btn = QPushButton("验证参数")
        validate_btn.clicked.connect(self._on_validate)
        btn_layout.addWidget(validate_btn)

        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Focus to step if provided
        if self._focus_step:
            self._focus_to_step(self._focus_step)

    def _build_param_form(self, groups: List[ParamGroup], layout: QVBoxLayout, record_groups: bool = False) -> None:
        for group in groups:
            params_to_show = group.params
            if not params_to_show:
                continue

            grp_box = QGroupBox(group.zh_name)
            grp_box.setToolTip(group.zh_desc)
            grp_layout = QFormLayout(grp_box)
            grp_layout.setSpacing(10)
            grp_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

            for param in params_to_show:
                result = create_param_widget(param, self)
                self._param_widgets[param.key] = result

                label = QLabel(param.zh_name)
                label.setToolTip(param.zh_desc)
                result.label_widget = label

                grp_layout.addRow(label, result.widget)

            layout.addWidget(grp_box)
            if record_groups:
                self._group_boxes[group.group_id] = grp_box

    def _apply_values(self) -> None:
        for key, result in self._param_widgets.items():
            val = self._config_dict.get(key, "")
            if val:
                result.set_value(val)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------
    def _on_validate(self) -> None:
        errors: List[str] = []
        for key, result in self._param_widgets.items():
            ok, msg = result.validate()
            if not ok:
                errors.append(msg)

        if errors:
            QMessageBox.warning(self, "参数验证失败", "\n".join(errors[:10]))
        else:
            QMessageBox.information(self, "验证通过", "所有参数值有效")

    def _on_save(self) -> None:
        # If on raw file tab, save raw content
        if self._tab_widget.currentIndex() == 2:
            raw_content = self._raw_edit.toPlainText()
            self._save_raw_config(raw_content)
            self.config_saved.emit(self._cfg_path)
            QMessageBox.information(self, "保存成功", f"配置已保存到:\n{self._cfg_path}")
            self.accept()
            return

        # Collect values from widgets
        new_values: Dict[str, str] = {}
        for key, result in self._param_widgets.items():
            new_values[key] = result.get_value()

        # Validate
        errors: List[str] = []
        for key, result in self._param_widgets.items():
            ok, msg = result.validate()
            if not ok:
                errors.append(msg)

        if errors:
            reply = QMessageBox.question(
                self,
                "参数验证警告",
                f"以下参数可能有问题:\n{chr(10).join(errors[:5])}\n\n是否仍要保存?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._save_merged_config(new_values)
        self.config_saved.emit(self._cfg_path)
        QMessageBox.information(self, "保存成功", f"配置已保存到:\n{self._cfg_path}")
        self.accept()

    def _save_merged_config(self, new_values: Dict[str, str]) -> None:
        """合并保存配置（保留原有注释和结构）"""
        lines: List[str] = []
        if os.path.isfile(self._cfg_path):
            with open(self._cfg_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        written_keys: set[str] = set()
        out_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                out_lines.append(line)
                continue
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in new_values:
                new_val = new_values[key]
                # Preserve inline comment if any
                comment_part = ""
                if "#" in line:
                    comment_idx = line.find("#", line.find("="))
                    if comment_idx > 0:
                        comment_part = "  " + line[comment_idx:].rstrip()
                out_lines.append(f"{key} = {new_val}{comment_part}\n")
                written_keys.add(key)
            else:
                out_lines.append(line)

        # Append new keys not in original file
        for key, val in new_values.items():
            if key not in written_keys:
                out_lines.append(f"{key} = {val}\n")

        with open(self._cfg_path, "w", encoding="utf-8") as f:
            f.writelines(out_lines)

    def _save_raw_config(self, content: str) -> None:
        with open(self._cfg_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _on_reload_raw(self) -> None:
        self._raw_edit.setPlainText(self._read_raw_config())

    def _focus_to_step(self, step_id: str) -> None:
        """定位到对应步骤的参数分组并滚动高亮。"""
        groups = get_group_for_step(step_id)
        if not groups:
            return
        self._tab_widget.setCurrentIndex(1)  # Switch to advanced tab
        target_group = groups[0]
        grp_box = self._group_boxes.get(target_group.group_id)
        if not grp_box:
            return
        # Highlight the group box
        grp_box.setStyleSheet("QGroupBox { border: 2px solid #3b82f6; border-radius: 6px; }")
        # Scroll to make it visible
        self._advanced_scroll.ensureWidgetVisible(grp_box, 50, 50)