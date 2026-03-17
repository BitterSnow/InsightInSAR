"""
桌面端样式：与 Web 端 globals.css 深色主题一致；
流程界面按钮与状态列配色、微交互由本模块常量与辅助函数提供。
"""
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QTableWidgetItem
from PySide6.QtCore import QModelIndex, Qt

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

# 状态列：深色主题「chip」风格（推荐）
# - 背景：深色轻染，避免浅底突兀
# - 文本：柔和语义色，运行中/失败加粗（由 apply_status_style 控制）
STATUS_PENDING_BG = "#0f172a"
STATUS_PENDING_FG = "#94a3b8"
STATUS_RUNNING_BG = "#0b1220"
STATUS_RUNNING_FG = "#60a5fa"
STATUS_SUCCESS_BG = "#071a12"
STATUS_SUCCESS_FG = "#34d399"
STATUS_FAIL_BG = "#1b0b0b"
STATUS_FAIL_FG = "#f87171"


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
    """根据步骤状态设置表格单元格背景色、字体色与字重（运行中/失败加粗）。"""
    font = item.font()
    if status == "success":
        item.setBackground(QBrush(QColor(STATUS_SUCCESS_BG)))
        item.setForeground(QBrush(QColor(STATUS_SUCCESS_FG)))
        font.setWeight(QFont.Weight.Normal)
    elif status == "pending":
        item.setBackground(QBrush(QColor(STATUS_PENDING_BG)))
        item.setForeground(QBrush(QColor(STATUS_PENDING_FG)))
        font.setWeight(QFont.Weight.Normal)
    elif status == "fail":
        item.setBackground(QBrush(QColor(STATUS_FAIL_BG)))
        item.setForeground(QBrush(QColor(STATUS_FAIL_FG)))
        font.setWeight(QFont.Weight.Bold)
    elif status == "running":
        item.setBackground(QBrush(QColor(STATUS_RUNNING_BG)))
        item.setForeground(QBrush(QColor(STATUS_RUNNING_FG)))
        font.setWeight(QFont.Weight.Bold)
    else:
        item.setBackground(QBrush(QColor(STATUS_PENDING_BG)))
        item.setForeground(QBrush(QColor(STATUS_PENDING_FG)))
        font.setWeight(QFont.Weight.Normal)
    item.setFont(font)


class StatusColumnDelegate(QStyledItemDelegate):
    """
    qt-material 主题会覆盖选中态的文字颜色（强制白色），导致状态列的自定义前景色/加粗看起来无效。
    该 delegate 只需用于状态列：强制选中/未选中都使用 ForegroundRole 的颜色绘制文本。
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        强制按 item 的 role 绘制（背景/前景/字体），绕过主题 QSS 对 item 的覆盖。
        只用于状态列，所以不追求复杂的 hover/selection 视觉，保证语义颜色稳定可读即可。
        """
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        font = index.data(Qt.ItemDataRole.FontRole)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""

        bg_brush = bg if isinstance(bg, QBrush) else (QBrush(bg) if isinstance(bg, QColor) else None)
        fg_brush = fg if isinstance(fg, QBrush) else (QBrush(fg) if isinstance(fg, QColor) else None)

        painter.save()

        # 背景：优先使用 BackgroundRole；没有则退回父类（避免出现透明导致可读性差）
        if bg_brush is not None:
            painter.fillRect(opt.rect, bg_brush)
        else:
            super().paint(painter, opt, index)
            painter.restore()
            return

        # 字体
        if isinstance(font, QFont):
            painter.setFont(font)
        else:
            painter.setFont(opt.font)

        # 文字颜色
        if fg_brush is not None:
            painter.setPen(fg_brush.color())
        else:
            painter.setPen(opt.palette.color(opt.palette.ColorRole.Text))

        # 文本：居中（状态列语义标签）
        painter.drawText(opt.rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignCenter, str(text))

        painter.restore()
