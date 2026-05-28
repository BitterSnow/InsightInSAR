"""
参数输入控件工厂：根据参数类型生成对应的 Qt 控件。
包含验证逻辑与信号绑定。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)
from PySide6.QtCore import Qt

from .mintpy_param_groups import ParamMeta


@dataclass
class ParamWidgetResult:
    """参数控件及其验证结果"""

    widget: QWidget
    get_value: Callable[[], str]
    set_value: Callable[[str], None]
    validate: Callable[[], tuple[bool, str]]
    param_meta: ParamMeta
    label_widget: QWidget | None = None


# "no" 值在保存到配置文件时需要原样写出
_NO_VALUE = "no"
_NONE_VALUE = "none"


def create_param_widget(meta: ParamMeta, parent: QWidget | None = None) -> ParamWidgetResult:
    """根据参数元数据创建输入控件"""
    creators = {
        "enum": _create_enum_widget,
        "yes_no_auto": _create_yes_no_auto_widget,
        "float": _create_numeric_widget,
        "int": _create_numeric_widget,
        "path": _create_path_widget,
        "text": _create_text_widget,
        "date_list": _create_text_widget,
        "bbox": _create_text_widget,
    }
    creator = creators.get(meta.type, _create_text_widget)
    return creator(meta, parent)


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------
def _create_enum_widget(meta: ParamMeta, parent: QWidget | None) -> ParamWidgetResult:
    w = QWidget(parent)
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    combo = QComboBox()
    if meta.valid_values:
        combo.addItems(meta.valid_values)
    combo.setToolTip(meta.zh_desc)
    combo.setMinimumWidth(120)

    # Set default selection
    if meta.default:
        idx = combo.findText(meta.default)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    layout.addWidget(combo, 1)
    if meta.unit:
        layout.addWidget(_unit_label(meta.unit))

    def get_value() -> str:
        return combo.currentText().strip()

    def set_value(v: str) -> None:
        if not v:
            return
        idx = combo.findText(v)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(v)

    def validate() -> tuple[bool, str]:
        val = combo.currentText().strip()
        if meta.valid_values and val not in meta.valid_values:
            return False, f"{meta.zh_name}: 请选择有效选项 ({', '.join(meta.valid_values)})"
        return True, ""

    return ParamWidgetResult(w, get_value, set_value, validate, meta)


# ---------------------------------------------------------------------------
# Yes / No
# ---------------------------------------------------------------------------
_YES_NO_VALUES = ["yes", "no"]


def _create_yes_no_auto_widget(meta: ParamMeta, parent: QWidget | None) -> ParamWidgetResult:
    w = QWidget(parent)
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    combo = QComboBox()
    combo.addItems(_YES_NO_VALUES)
    combo.setToolTip(meta.zh_desc)
    combo.setMinimumWidth(120)

    # Set default selection
    default_val = (meta.default or "no").lower()
    mapping = {"true": "yes", "false": "no", "1": "yes", "0": "no"}
    default_val = mapping.get(default_val, default_val)
    idx = combo.findText(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)

    layout.addWidget(combo, 1)
    if meta.unit:
        layout.addWidget(_unit_label(meta.unit))

    def get_value() -> str:
        return combo.currentText().strip()

    def set_value(v: str) -> None:
        v_lower = (v or "no").lower()
        mapping = {"true": "yes", "false": "no", "1": "yes", "0": "no"}
        v_lower = mapping.get(v_lower, v_lower)
        idx = combo.findText(v_lower)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def validate() -> tuple[bool, str]:
        val = combo.currentText().strip().lower()
        if val in _YES_NO_VALUES:
            return True, ""
        return False, f"{meta.zh_name}: 请选择 yes 或 no"

    return ParamWidgetResult(w, get_value, set_value, validate, meta)


# ---------------------------------------------------------------------------
# Float / Int (editable combo)
# ---------------------------------------------------------------------------
def _create_numeric_widget(meta: ParamMeta, parent: QWidget | None) -> ParamWidgetResult:
    w = QWidget(parent)
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    combo = QComboBox()
    combo.setEditable(True)
    combo.setToolTip(
        f"{meta.zh_desc}\n范围: {meta.min_val or '-'} ~ {meta.max_val or '-'} {meta.unit}"
        if meta.min_val is not None or meta.max_val is not None
        else meta.zh_desc
    )
    combo.setMinimumWidth(120)

    # Add auto option only if allow_auto
    if meta.allow_auto:
        combo.addItem("auto")

    # Set default value
    if meta.default:
        combo.setCurrentText(meta.default)

    layout.addWidget(combo, 1)
    if meta.unit:
        layout.addWidget(_unit_label(meta.unit))

    def get_value() -> str:
        return combo.currentText().strip()

    def set_value(v: str) -> None:
        if not v:
            combo.setEditText("")
            return
        idx = combo.findText(v)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(v)

    def validate() -> tuple[bool, str]:
        val = combo.currentText().strip()
        if val.lower() in ("auto", "none", "no"):
            return True, ""
        try:
            f = float(val)
        except ValueError:
            return False, f"{meta.zh_name}: 请输入有效数值"
        if meta.min_val is not None and f < meta.min_val:
            return False, f"{meta.zh_name}: 值不能小于 {meta.min_val}"
        if meta.max_val is not None and f > meta.max_val:
            return False, f"{meta.zh_name}: 值不能大于 {meta.max_val}"
        return True, ""

    return ParamWidgetResult(w, get_value, set_value, validate, meta)


# ---------------------------------------------------------------------------
# Path (text + browse button)
# ---------------------------------------------------------------------------
def _create_path_widget(meta: ParamMeta, parent: QWidget | None) -> ParamWidgetResult:
    w = QWidget(parent)
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    edit = QLineEdit()
    edit.setPlaceholderText("auto（自动查找）")
    edit.setToolTip(meta.zh_desc)

    browse_btn = QPushButton("浏览")
    browse_btn.setFixedWidth(56)

    def on_browse() -> None:
        if meta.path_type == "dir":
            path = QFileDialog.getExistingDirectory(w, f"选择{meta.zh_name}")
        else:
            filter_str = f"{meta.zh_name} ({meta.pattern});;所有文件 (*)" if meta.pattern else "所有文件 (*)"
            path, _ = QFileDialog.getOpenFileName(w, f"选择{meta.zh_name}", "", filter_str)
        if path:
            edit.setText(path)

    browse_btn.clicked.connect(on_browse)

    layout.addWidget(edit, 1)
    layout.addWidget(browse_btn)

    def get_value() -> str:
        return edit.text().strip() or "auto"

    def set_value(v: str) -> None:
        edit.setText(v if v and v.lower() != "auto" else "")

    def validate() -> tuple[bool, str]:
        val = edit.text().strip()
        if not val or val.lower() in ("auto", "none"):
            return True, ""
        return True, ""

    return ParamWidgetResult(w, get_value, set_value, validate, meta)


# ---------------------------------------------------------------------------
# Text / Date list / BBox
# ---------------------------------------------------------------------------
def _create_text_widget(meta: ParamMeta, parent: QWidget | None) -> ParamWidgetResult:
    w = QWidget(parent)
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    # Determine placeholder based on default value
    default_val = meta.default or ""
    if default_val.lower() in ("no", "none"):
        placeholder = "不限制"
    elif default_val.lower() == "auto" and meta.allow_auto:
        placeholder = "auto（自动）"
    elif default_val:
        placeholder = ""
    else:
        placeholder = "可选"

    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setToolTip(meta.zh_desc)
    edit.setMinimumWidth(120)

    # Pre-fill with default value (skip special values)
    if default_val and default_val.lower() not in ("no", "none", "auto"):
        edit.setText(default_val)

    layout.addWidget(edit, 1)
    if meta.unit:
        layout.addWidget(_unit_label(meta.unit))

    def get_value() -> str:
        text = edit.text().strip()
        if text:
            return text
        # If empty, return the default (which may be "no")
        return default_val if default_val else "no"

    def set_value(v: str) -> None:
        if not v or v.lower() in ("auto", "no", "none"):
            edit.setText("")
        else:
            edit.setText(v)

    def validate() -> tuple[bool, str]:
        return True, ""

    return ParamWidgetResult(w, get_value, set_value, validate, meta)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _unit_label(unit: str) -> QLabel:
    lbl = QLabel(unit)
    lbl.setStyleSheet("color: #64748b; font-size: 12px;")
    lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    return lbl
