"""
使用 QStyle 标准图标，供菜单与按钮使用；
流程界面优先使用 Material Design Icons（qtawesome）统一矢量风格。
qtawesome 延迟到首次使用流程图标时再导入，避免与启动时 sys.path 冲突。
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QStyle
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPolygonF
from PySide6.QtCore import QSize, QPointF, QRectF

# 延迟导入：首次 _mdi_icon 时再 import qtawesome，避免早期导入失败
_HAS_QTA: bool | None = None
_qta_module = None


def _ensure_qtawesome():
    """首次调用时尝试导入 qtawesome，并缓存结果。"""
    global _HAS_QTA, _qta_module
    if _HAS_QTA is not None:
        return _HAS_QTA
    try:
        import qtawesome as qta
        _qta_module = qta
        _HAS_QTA = True
        return True
    except ImportError:
        _HAS_QTA = False
        return False


def _style() -> QStyle:
    return QApplication.style()


_FLOW_ICON_SIZE = 28


def _painted_flow_icon(name: str, color_hex: str) -> QIcon | None:
    """用 QPainter 绘制流程图标（不依赖 qtawesome），蓝/黄/紫扁平风格。"""
    try:
        from PySide6.QtCore import Qt
        pm = QPixmap(_FLOW_ICON_SIZE, _FLOW_ICON_SIZE)
        pm.fill(Qt.GlobalColor.transparent)
        color = QColor(color_hex)
        if not color.isValid():
            return None
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        margin = 4
        r = QRectF(margin, margin, _FLOW_ICON_SIZE - 2 * margin, _FLOW_ICON_SIZE - 2 * margin)
        if name == "play":
            cx, cy = r.center().x(), r.center().y()
            h = r.height() * 0.5
            pts = [QPointF(cx - h * 0.4, cy - h), QPointF(cx - h * 0.4, cy + h), QPointF(cx + h * 0.6, cy)]
            p.drawPolygon(QPolygonF(pts))
        elif name == "folder-open":
            p.drawRoundedRect(r.adjusted(0, r.height() * 0.15, 0, 0), 2, 2)
            lid = QRectF(r.x(), r.y(), r.width() * 0.85, r.height() * 0.35)
            p.drawRoundedRect(lid, 2, 2)
        elif name == "refresh":
            cx, cy = r.center().x(), r.center().y()
            rad = min(r.width(), r.height()) * 0.4
            p.setPen(QPen(color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(int(cx - rad), int(cy - rad), int(2 * rad), int(2 * rad), 60 * 16, 270 * 16)
            from math import cos, sin, pi
            a = pi * (60 + 270) / 180
            x1, y1 = cx + rad * cos(a), cy - rad * sin(a)
            a2 = a + pi * 0.6
            dx, dy = 6 * cos(a2), -6 * sin(a2)
            pts = [QPointF(x1, y1), QPointF(x1 + dx, y1 + dy), QPointF(x1 + dx * 0.5, y1 + dy * 0.5)]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(QPolygonF(pts))
        else:
            p.end()
            return None
        p.end()
        return QIcon(pm)
    except Exception:
        return None


def _mdi_icon(name: str, color: str | None = None, fallback: QIcon | None = None) -> QIcon:
    """优先 qtawesome；不可用时用自绘图标（蓝/黄/紫）；最后 fallback。"""
    if QApplication.instance() is not None and color:
        if _ensure_qtawesome() and _qta_module is not None:
            try:
                qta = _qta_module
                icon = qta.icon(f"mdi6.{name}", color=color)
                if not icon.isNull():
                    pm = icon.pixmap(QSize(_FLOW_ICON_SIZE, _FLOW_ICON_SIZE))
                    if not pm.isNull():
                        return QIcon(pm)
            except Exception:
                pass
        painted = _painted_flow_icon(name, color)
        if painted is not None:
            return painted
    return fallback or QIcon()


def icon_open_folder() -> QIcon:
    """打开文件夹 / 打开工程"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)


def icon_new_folder() -> QIcon:
    """新建工程"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)


def icon_edit() -> QIcon:
    """修改项目 / 编辑"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)


def icon_save() -> QIcon:
    """保存工程"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)


def icon_cancel() -> QIcon:
    """取消"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)


def icon_workspace() -> QIcon:
    """定义工作区"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)


def icon_home() -> QIcon:
    """地图回到项目区域"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon)


def icon_data_import() -> QIcon:
    """数据导入"""
    return _style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)


# ---------- 流程操作区：Material Icons + 附图配色（蓝/黄/紫）----------
# 与附图一致：play_arrow 蓝、folder_open 黄、refresh 紫，扁平清晰
_FLOW_PLAY_COLOR = "#2196F3"      # 蓝 - 运行本步
_FLOW_FOLDER_COLOR = "#FDD835"    # 黄 - 打开目录
_FLOW_REFRESH_COLOR = "#9C27B0"   # 紫 - 清理/重置

def icon_play() -> QIcon:
    """运行本步（Material: play 三角形，蓝色）。"""
    return _mdi_icon("play", color=_FLOW_PLAY_COLOR, fallback=_style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))


def icon_pause() -> QIcon:
    """暂停（Material: pause，蓝色）。"""
    try:
        fallback = _style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
    except AttributeError:
        fallback = QIcon()
    return _mdi_icon("pause", color=_FLOW_PLAY_COLOR, fallback=fallback)


def icon_folder_open() -> QIcon:
    """打开本步输出目录（Material: folder-open，黄色）。"""
    return _mdi_icon("folder-open", color=_FLOW_FOLDER_COLOR, fallback=_style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))


def icon_refresh() -> QIcon:
    """清理本步骤数据（Material: refresh，紫色）。"""
    return _mdi_icon("refresh", color=_FLOW_REFRESH_COLOR, fallback=_style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))


# ---------- 工程右键菜单：Stack / 时间序列 ----------
_MENU_ICON_COLOR = "#94a3b8"


def icon_stack_flow() -> QIcon:
    """打开 Stack 流程（层级/流水线）。"""
    return _mdi_icon("layers-outline", color=_MENU_ICON_COLOR, fallback=_style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))


def icon_mintpy_flow() -> QIcon:
    """打开时间序列分析（时序/图表）。"""
    return _mdi_icon("chart-timeline-variant", color=_MENU_ICON_COLOR, fallback=_style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))


def icon_mintpy_config() -> QIcon:
    """时间序列初始化/配置（设置）。"""
    return _mdi_icon("cog-outline", color=_MENU_ICON_COLOR, fallback=_style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
