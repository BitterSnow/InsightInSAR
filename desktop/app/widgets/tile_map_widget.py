"""
二维瓦片地图：使用开源免费影像/底图服务，QGraphicsView + 瓦片加载，低占用。
支持显示工作区红色虚线框 (N,S,W,E)。
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QLabel,
)
from PySide6.QtCore import Qt, QRectF, QUrl, QPointF, QSize, Slot, Signal
from PySide6.QtGui import QPixmap, QPen, QPainter, QWheelEvent, QMouseEvent
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

TILE_SIZE = 256
# Bing 卫星图（Aerial）：使用 QuadKey，瓦片为 JPEG。商用需遵守 Bing Maps 条款并可能需要 API Key。
# 子域 ecn.t0~t3 做简单负载分散
BING_AERIAL_URL = "https://ecn.t{s}.tiles.virtualearth.net/tiles/a{quadkey}.jpeg?g=1"
MAX_ZOOM = 19
MIN_ZOOM = 1
DEFAULT_ZOOM = 6
DEFAULT_CENTER_LAT = 35.0
DEFAULT_CENTER_LON = 105.0
CACHE_MAX_TILES = 256
PAN_STEP_PX = 80
ZOOM_STEP = 1


def _lon_lat_to_tile(lon_deg: float, lat_deg: float, zoom: int) -> tuple[float, float]:
    """Web Mercator: 经度纬度 -> 瓦片坐标 (x, y)，可为小数。"""
    n = 2.0 ** zoom
    lat_rad = math.radians(lat_deg)
    x = (lon_deg + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _tile_to_scene(tx: float, ty: float) -> tuple[float, float]:
    """瓦片坐标 -> 场景坐标（像素）。"""
    return tx * TILE_SIZE, ty * TILE_SIZE


def _lon_lat_to_scene(lon_deg: float, lat_deg: float, zoom: int) -> tuple[float, float]:
    """经度纬度 -> 场景坐标。"""
    tx, ty = _lon_lat_to_tile(lon_deg, lat_deg, zoom)
    return _tile_to_scene(tx, ty)


def _scene_size(zoom: int) -> float:
    """当前 zoom 下场景边长（像素）。"""
    return (2 ** zoom) * TILE_SIZE


def _scene_to_lon_lat(sx: float, sy: float, zoom: int) -> tuple[float, float]:
    """场景坐标 (像素) -> 经度纬度 (Web Mercator 逆变换)。"""
    n = 2.0 ** zoom
    tx = sx / TILE_SIZE
    ty = sy / TILE_SIZE
    lon_deg = tx / n * 360.0 - 180.0
    # y: lat_rad = atan(sinh(pi * (1 - 2*ty/n)))
    t = math.pi * (1.0 - 2.0 * ty / n)
    lat_rad = math.atan(math.sinh(t))
    lat_deg = math.degrees(lat_rad)
    return lon_deg, lat_deg


def _tile_to_quadkey(z: int, x: int, y: int) -> str:
    """Bing 瓦片索引：将 (z, x, y) 转为 QuadKey 字符串。"""
    q = []
    for i in range(z):
        mask = 1 << (z - 1 - i)
        y_bit = 1 if (y & mask) else 0
        x_bit = 1 if (x & mask) else 0
        q.append(str(2 * y_bit + x_bit))
    return "".join(q)


class TileMapWidget(QGraphicsView):
    """
    瓦片地图：可设置中心与缩放，可选显示工作区 bbox (N,S,W,E)。
    鼠标移动时发射 coord_updated(lon, lat)。
    """
    coord_updated = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._zoom = DEFAULT_ZOOM
        self._center_lat = DEFAULT_CENTER_LAT
        self._center_lon = DEFAULT_CENTER_LON
        self._bbox: Optional[tuple[float, float, float, float]] = None  # (N, S, W, E)
        self._tile_cache: dict[tuple[int, int, int], QGraphicsPixmapItem] = {}
        self._cache_order: list[tuple[int, int, int]] = []
        self._bbox_rect_item: Optional[QGraphicsRectItem] = None
        self._network = QNetworkAccessManager(self)
        self._pending: dict[QNetworkReply, tuple[int, int, int]] = {}

        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMinimumSize(400, 300)

        self._update_scene_rect()
        cx, cy = self._scene_center()
        self.centerOn(QPointF(cx, cy))
        self._load_tiles_for_view()

    def _scene_center(self) -> tuple[float, float]:
        cx, cy = _lon_lat_to_scene(self._center_lon, self._center_lat, self._zoom)
        return cx, cy

    def _update_scene_rect(self) -> None:
        size = _scene_size(self._zoom)
        self.scene().setSceneRect(0, 0, size, size)

    def _tile_url(self, z: int, x: int, y: int) -> str:
        quadkey = _tile_to_quadkey(z, x, y)
        s = (x + y) % 4
        return BING_AERIAL_URL.format(s=s, quadkey=quadkey)

    def _load_tile(self, z: int, tx: int, ty: int) -> None:
        key = (z, tx, ty)
        if key in self._tile_cache:
            return
        url = QUrl(self._tile_url(z, tx, ty))
        req = QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", b"InSAR-Desktop/1.0")
        reply = self._network.get(req)
        self._pending[reply] = key
        reply.finished.connect(self._on_tile_loaded)

    @Slot()
    def _on_tile_loaded(self) -> None:
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return
        key = self._pending.pop(reply, None)
        reply.deleteLater()
        if key is None:
            return
        z, tx, ty = key
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return
        data = reply.readAll()
        pix = QPixmap()
        if not pix.loadFromData(data.data()):
            return
        sx, sy = _tile_to_scene(tx, ty)
        item = self.scene().addPixmap(pix)
        item.setPos(sx, sy)
        item.setZValue(-1)
        self._tile_cache[key] = item
        self._cache_order.append(key)
        while len(self._cache_order) > CACHE_MAX_TILES:
            old = self._cache_order.pop(0)
            if old in self._tile_cache:
                self.scene().removeItem(self._tile_cache[old])
                del self._tile_cache[old]

    def _load_tiles_for_view(self) -> None:
        """根据当前视图范围加载可见瓦片。"""
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        z = self._zoom
        n = 2 ** z
        t_min_x = max(0, int(r.left() / TILE_SIZE))
        t_max_x = min(n - 1, int(r.right() / TILE_SIZE) + 1)
        t_min_y = max(0, int(r.top() / TILE_SIZE))
        t_max_y = min(n - 1, int(r.bottom() / TILE_SIZE) + 1)
        for ty in range(t_min_y, t_max_y + 1):
            for tx in range(t_min_x, t_max_x + 1):
                self._load_tile(z, tx, ty)

    def _draw_bbox(self) -> None:
        if self._bbox_rect_item is not None:
            self.scene().removeItem(self._bbox_rect_item)
            self._bbox_rect_item = None
        if self._bbox is None:
            return
        n, s, w, e = self._bbox
        x1, y1 = _lon_lat_to_scene(w, n, self._zoom)
        x2, y2 = _lon_lat_to_scene(e, s, self._zoom)
        rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        self._bbox_rect_item = self.scene().addRect(rect, QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine))
        self._bbox_rect_item.setZValue(10)

    def set_bbox(self, n_s_w_e: Optional[tuple[float, float, float, float]]) -> None:
        """设置工作区四至 (N, S, W, E)，None 则清除。重新定义工作区后调用以刷新红色框与视图。"""
        self._bbox = n_s_w_e
        self._draw_bbox()
        if n_s_w_e is not None:
            n, s, w, e = n_s_w_e
            x1, y1 = _lon_lat_to_scene(w, n, self._zoom)
            x2, y2 = _lon_lat_to_scene(e, s, self._zoom)
            rect = QRectF(x1, y1, x2 - x1, y2 - y1)
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self._load_tiles_for_view()
        self.viewport().update()

    def set_center_and_zoom(self, lat: float, lon: float, zoom: Optional[int] = None) -> None:
        """设置中心点与可选缩放。"""
        self._center_lat = lat
        self._center_lon = lon
        if zoom is not None:
            self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self._update_scene_rect()
        cx, cy = self._scene_center()
        self.centerOn(QPointF(cx, cy))
        self._load_tiles_for_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._load_tiles_for_view()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_tiles_for_view()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._load_tiles_for_view()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """鼠标滚轮：向上放大、向下缩小，以光标位置为中心。"""
        pos = event.position()
        scene_pos = self.mapToScene(int(pos.x()), int(pos.y()))
        delta = event.angleDelta().y()
        if delta > 0:
            if self._zoom >= MAX_ZOOM:
                return
            self._zoom += ZOOM_STEP
            self._update_scene_rect()
            self._draw_bbox()
            # 缩放后使光标下的场景点仍保持在光标下
            new_sx = scene_pos.x() * 2
            new_sy = scene_pos.y() * 2
            self.centerOn(QPointF(new_sx, new_sy))
        else:
            if self._zoom <= MIN_ZOOM:
                return
            self._zoom -= ZOOM_STEP
            self._update_scene_rect()
            self._draw_bbox()
            new_sx = scene_pos.x() / 2
            new_sy = scene_pos.y() / 2
            self.centerOn(QPointF(new_sx, new_sy))
        self._load_tiles_for_view()
        event.accept()

    def pan_up(self) -> None:
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - PAN_STEP_PX)
        self._load_tiles_for_view()

    def pan_down(self) -> None:
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + PAN_STEP_PX)
        self._load_tiles_for_view()

    def pan_left(self) -> None:
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - PAN_STEP_PX)
        self._load_tiles_for_view()

    def pan_right(self) -> None:
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + PAN_STEP_PX)
        self._load_tiles_for_view()

    def zoom_in(self) -> None:
        if self._zoom >= MAX_ZOOM:
            return
        self._zoom += ZOOM_STEP
        self._update_scene_rect()
        self._draw_bbox()
        cx, cy = self._scene_center()
        self.centerOn(QPointF(cx, cy))
        self._load_tiles_for_view()

    def zoom_out(self) -> None:
        if self._zoom <= MIN_ZOOM:
            return
        self._zoom -= ZOOM_STEP
        self._update_scene_rect()
        self._draw_bbox()
        cx, cy = self._scene_center()
        self.centerOn(QPointF(cx, cy))
        self._load_tiles_for_view()

    def home(self) -> None:
        """回到项目所在区域：有工作区则 fit 到 bbox，否则回到默认中心与缩放。"""
        if self._bbox is not None:
            n, s, w, e = self._bbox
            x1, y1 = _lon_lat_to_scene(w, n, self._zoom)
            x2, y2 = _lon_lat_to_scene(e, s, self._zoom)
            rect = QRectF(x1, y1, x2 - x1, y2 - y1)
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.set_center_and_zoom(DEFAULT_CENTER_LAT, DEFAULT_CENTER_LON, DEFAULT_ZOOM)
        self._load_tiles_for_view()

    def scene_to_lon_lat(self, sx: float, sy: float) -> tuple[float, float]:
        """场景坐标 -> (lon, lat)。"""
        return _scene_to_lon_lat(sx, sy, self._zoom)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        pt = event.position()
        scene_pt = self.mapToScene(int(pt.x()), int(pt.y()))
        sx, sy = scene_pt.x(), scene_pt.y()
        size = _scene_size(self._zoom)
        if 0 <= sx <= size and 0 <= sy <= size:
            lon, lat = self.scene_to_lon_lat(sx, sy)
            self.coord_updated.emit(lon, lat)
        else:
            self.coord_updated.emit(float("nan"), float("nan"))

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.coord_updated.emit(float("nan"), float("nan"))


# 地图控制按钮统一样式：图标居中、无多余边框
MAP_CTRL_ICON_SIZE = 26
MAP_CTRL_BTN_STYLE = """
    QPushButton {
        min-width: 40px;
        min-height: 40px;
        max-width: 40px;
        max-height: 40px;
        padding: 0;
        border: 1px solid #334155;
        border-radius: 8px;
        background-color: #0f172a;
        color: #f8fafc;
        font-size: 22px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #1e293b;
        border-color: #475569;
    }
    QPushButton:pressed {
        background-color: #334155;
    }
"""


# 叠加控件边距与按钮尺寸
MAP_CTRL_MARGIN = 12
MAP_CTRL_BTN_SIZE = 40
MAP_CTRL_SPACING = 6


class MapWithToolbar(QWidget):
    """地图铺满整个 Tab；Home/放大/缩小 叠加在地图右下角。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map = TileMapWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._map, 1)

        # 控制按钮叠加层：无左侧边框，避免黑边
        self._ctrl_frame = QFrame(self)
        self._ctrl_frame.setStyleSheet(
            "QFrame {"
            " background-color: rgba(15, 23, 42, 0.85);"
            " border-radius: 8px;"
            " border: 1px solid #334155;"
            " border-left: none;"
            "}"
        )
        ctrl_layout = QVBoxLayout(self._ctrl_frame)
        ctrl_layout.setContentsMargins(8, 8, 8, 8)
        ctrl_layout.setSpacing(MAP_CTRL_SPACING)

        btn_home = QPushButton("⌂")  # 房子符号，避免 SP_DirHomeIcon 在 Windows 上显示为文件夹
        btn_home.setToolTip("回到项目区域")
        btn_home.setStyleSheet(MAP_CTRL_BTN_STYLE)
        btn_home.clicked.connect(self._map.home)
        ctrl_layout.addWidget(btn_home)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setToolTip("放大")
        btn_zoom_in.setStyleSheet(MAP_CTRL_BTN_STYLE)
        btn_zoom_in.clicked.connect(self._map.zoom_in)
        ctrl_layout.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setToolTip("缩小")
        btn_zoom_out.setStyleSheet(MAP_CTRL_BTN_STYLE)
        btn_zoom_out.clicked.connect(self._map.zoom_out)
        ctrl_layout.addWidget(btn_zoom_out)

        w = MAP_CTRL_BTN_SIZE + 16
        h = 3 * MAP_CTRL_BTN_SIZE + 2 * MAP_CTRL_SPACING + 16
        self._ctrl_frame.setFixedSize(w, h)
        self._ctrl_frame.raise_()

        # 左下角经纬度标签（随鼠标动态更新）
        self._coord_label = QLabel("经度: —  纬度: —", self)
        self._coord_label.setStyleSheet(
            "QLabel {"
            " background-color: rgba(15, 23, 42, 0.85);"
            " color: #e2e8f0;"
            " padding: 6px 10px;"
            " border-radius: 6px;"
            " font-family: Consolas, monospace;"
            " font-size: 13px;"
            "}"
        )
        self._coord_label.adjustSize()
        self._coord_label.raise_()
        self._map.coord_updated.connect(self._on_coord_updated)

    def _on_coord_updated(self, lon: float, lat: float) -> None:
        if math.isnan(lon) or math.isnan(lat):
            self._coord_label.setText("经度: —  纬度: —")
        else:
            self._coord_label.setText(f"经度: {lon:.6f}  纬度: {lat:.6f}")
        self._coord_label.adjustSize()
        self._coord_label.setGeometry(
            MAP_CTRL_MARGIN,
            self.height() - self._coord_label.height() - MAP_CTRL_MARGIN,
            self._coord_label.width(),
            self._coord_label.height(),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = MAP_CTRL_BTN_SIZE + 16
        h = 3 * MAP_CTRL_BTN_SIZE + 2 * MAP_CTRL_SPACING + 16
        x = self.width() - w - MAP_CTRL_MARGIN
        y = self.height() - h - MAP_CTRL_MARGIN
        self._ctrl_frame.setGeometry(x, y, w, h)
        self._ctrl_frame.raise_()
        # 经纬度标签固定在左下角
        self._coord_label.adjustSize()
        self._coord_label.setGeometry(
            MAP_CTRL_MARGIN,
            self.height() - self._coord_label.height() - MAP_CTRL_MARGIN,
            self._coord_label.width(),
            self._coord_label.height(),
        )
        self._coord_label.raise_()

    @property
    def map_widget(self) -> TileMapWidget:
        return self._map

    def set_bbox(self, n_s_w_e: Optional[tuple[float, float, float, float]]) -> None:
        self._map.set_bbox(n_s_w_e)


def get_bbox_from_project(node: dict) -> Optional[tuple[float, float, float, float]]:
    """从工程 node 对应的 .md 中读取工作区，返回 (N,S,W,E) 或 None。"""
    from ..project_file import find_project_path, load_project_md_full, WORKSPACE_SECTION
    pid = node.get("id")
    pdir = node.get("projectPath")
    if not pid or not pdir:
        return None
    project_path = find_project_path(pdir, pid)
    if not project_path:
        return None
    data = load_project_md_full(project_path)
    if not data or WORKSPACE_SECTION not in data:
        return None
    raw = data[WORKSPACE_SECTION].strip()
    parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    if len(parts) < 4:
        return None
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except ValueError:
        return None
