"""
桌面端样式：与 Web 端 globals.css 深色主题一致；
流程界面按钮与状态列配色、微交互由本模块常量与辅助函数提供。
"""
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTableWidgetItem

# 与 frontend/app/globals.css @theme 对应
BACKGROUND = "#020617"
FOREGROUND = "#f8fafc"
CARD = "#0f172a"
MUTED = "#1e293b"
MUTED_FOREGROUND = "#94a3b8"
BORDER = "#334155"
PRIMARY_BUTTON = "#2563eb"
PRIMARY_BUTTON_HOVER = "#1d4ed8"

MAIN_STYLESHEET = f"""
    QWidget {{
        background-color: {BACKGROUND};
        color: {FOREGROUND};
    }}
    QMainWindow {{
        background-color: {BACKGROUND};
    }}
    QLabel {{
        color: {FOREGROUND};
    }}
    QLineEdit, QComboBox {{
        background-color: {CARD};
        color: {FOREGROUND};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 20px;
    }}
    QLineEdit:focus, QComboBox:focus {{
        border-color: #3b82f6;
    }}
    QPushButton {{
        background-color: {MUTED};
        color: {FOREGROUND};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 12px;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: #334155;
    }}
    QPushButton#primaryButton {{
        background-color: {PRIMARY_BUTTON};
        border-color: {PRIMARY_BUTTON};
        color: white;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {PRIMARY_BUTTON_HOVER};
    }}
    QPushButton#browseBtn {{
        background-color: {MUTED};
    }}
    QFrame#headerFrame {{
        background-color: {CARD};
        border-bottom: 1px solid {BORDER};
    }}
    QFrame#sidebarFrame {{
        background-color: {CARD};
        border-right: 1px solid {BORDER};
    }}
    QListWidget, QTreeWidget {{
        background-color: transparent;
        color: {FOREGROUND};
        border: none;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {MUTED};
    }}
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QDialog {{
        background-color: {CARD};
        color: {FOREGROUND};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
"""

# ---------- 流程界面：按钮配色（主色 / 悬停加深约 10%） ----------
FLOW_BTN_RUN_ALL = "#0066CC"           # 全线运行 / 全部运行（核心）
FLOW_BTN_RUN_ALL_HOVER = "#0055AA"
FLOW_BTN_RUN_CURRENT = "#0099CC"       # 运行当前步（辅助）
FLOW_BTN_RUN_CURRENT_HOVER = "#0088B3"
FLOW_BTN_RUN_FROM = "#4CAF50"          # 从本步运行（安全）
FLOW_BTN_RUN_FROM_HOVER = "#45A049"
FLOW_BTN_NAV = "#2196F3"               # 进入时间序列（导航）
FLOW_BTN_NAV_HOVER = "#1E88E5"

# 状态列：背景色 / 字体色
STATUS_SUCCESS_BG = "#E8F5E8"
STATUS_SUCCESS_FG = "#2E7D32"
STATUS_PENDING_BG = "#EEEEEE"
STATUS_PENDING_FG = "#666666"
STATUS_FAIL_BG = "#FFEBEE"
STATUS_FAIL_FG = "#C62828"
STATUS_RUNNING_BG = "#E3F2FD"
STATUS_RUNNING_FG = "#1565C0"


def flow_button_stylesheet(bg: str, hover_bg: str, text_color: str = "white") -> str:
    """流程按钮样式：主色、悬停加深、按下略暗、禁用灰；紧凑尺寸不突兀。"""
    return f"""
        QPushButton {{
            background-color: {bg}; color: {text_color}; border: none;
            border-radius: 4px; padding: 4px 10px; min-height: 0;
            font-size: 12px;
        }}
        QPushButton:hover {{ background-color: {hover_bg}; }}
        QPushButton:pressed {{ background-color: {hover_bg}; padding-top: 5px; padding-bottom: 3px; }}
        QPushButton:disabled {{ background-color: #9E9E9E; color: #E0E0E0; }}
    """


def apply_status_style(item: QTableWidgetItem, status: str) -> None:
    """根据步骤状态设置表格单元格背景色与字体色。"""
    if status == "success":
        item.setBackground(QBrush(QColor(STATUS_SUCCESS_BG)))
        item.setForeground(QBrush(QColor(STATUS_SUCCESS_FG)))
    elif status == "pending":
        item.setBackground(QBrush(QColor(STATUS_PENDING_BG)))
        item.setForeground(QBrush(QColor(STATUS_PENDING_FG)))
    elif status == "fail":
        item.setBackground(QBrush(QColor(STATUS_FAIL_BG)))
        item.setForeground(QBrush(QColor(STATUS_FAIL_FG)))
    elif status == "running":
        item.setBackground(QBrush(QColor(STATUS_RUNNING_BG)))
        item.setForeground(QBrush(QColor(STATUS_RUNNING_FG)))
    else:
        item.setBackground(QBrush(QColor(STATUS_PENDING_BG)))
        item.setForeground(QBrush(QColor(STATUS_PENDING_FG)))
