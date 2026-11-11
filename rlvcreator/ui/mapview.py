"""Simple vector map of the GPS track (no internet connection required)."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

Pt = Tuple[float, float]


def _merc(lat: float, lon: float) -> Pt:
    x = math.radians(lon)
    lat = max(-85.0, min(85.0, lat))
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


class MapView(QWidget):
    seekRequested = Signal(int)  # output second

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.source: List[Pt] = []
        self.route: List[Pt] = []  # projected output points (1 per second)
        self.sel: Optional[Tuple[int, int]] = None  # output seconds
        self.pos: Optional[Pt] = None
        self.start: Optional[Pt] = None
        self._bounds = (0.0, 0.0, 1.0, 1.0)
        self.zoom = 1.0
        self.center: Optional[Pt] = None
        self._drag: Optional[Tuple[QPointF, Pt]] = None
        self._moved = False
        self.setToolTip("Click the route to jump there  ·  Wheel: zoom  ·  Drag: pan  ·  Double-click: fit")

    def set_tracks(self, source_latlon: List[Pt], route_latlon: List[Pt], refit: bool = False) -> None:
        self.source = [_merc(a, b) for a, b in source_latlon]
        self.route = [_merc(a, b) for a, b in route_latlon]
        pts = self.source or self.route
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            self._bounds = (min(xs), min(ys), max(xs), max(ys))
        if refit or self.center is None:
            self.fit()
        self.update()

    def set_position(self, lat: Optional[float], lon: Optional[float]) -> None:
        self.pos = _merc(lat, lon) if lat is not None and lon is not None else None
        self.update()

    def set_selection(self, sel: Optional[Tuple[int, int]]) -> None:
        self.sel = sel
        self.update()

    def fit(self) -> None:
        x0, y0, x1, y1 = self._bounds
        self.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.zoom = 1.0
        self.update()

    def _scale(self) -> float:
        x0, y0, x1, y1 = self._bounds
        w = max(1e-9, x1 - x0)
        h = max(1e-9, y1 - y0)
        return min((self.width() - 30) / w, (self.height() - 30) / h) * self.zoom

    def _to_screen(self, p: Pt) -> QPointF:
        s = self._scale()
        cx, cy = self.center or (0.0, 0.0)
        return QPointF(self.width() / 2 + (p[0] - cx) * s, self.height() / 2 - (p[1] - cy) * s)

    def _from_screen(self, q: QPointF) -> Pt:
        s = self._scale()
        cx, cy = self.center or (0.0, 0.0)
        return cx + (q.x() - self.width() / 2) / s, cy - (q.y() - self.height() / 2) / s

    def _path(self, pts: List[Pt]) -> QPainterPath:
        path = QPainterPath()
        for i, p in enumerate(pts):
            q = self._to_screen(p)
            path.moveTo(q) if i == 0 else path.lineTo(q)
        return path

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(236, 240, 232))
        if not self.source and not self.route:
            p.setPen(QColor(120, 120, 120))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, "No GPS data")
            return
        # removed parts are visible in grey under the route
        p.setPen(QPen(QColor(170, 170, 170), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(self._path(self.source))
        if self.route:
            p.setPen(QPen(QColor(30, 100, 220), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            # draw kept route as separate pieces so cut jumps are not drawn as lines
            piece: List[Pt] = [self.route[0]]
            limit = self._jump_limit()
            for a, b in zip(self.route, self.route[1:]):
                if abs(a[0] - b[0]) + abs(a[1] - b[1]) > limit:
                    p.drawPath(self._path(piece))
                    piece = []
                piece.append(b)
            p.drawPath(self._path(piece))
            if self.sel:
                a, b = self.sel
                seg = self.route[max(0, a):min(len(self.route), b + 1)]
                if len(seg) >= 2:
                    p.setPen(QPen(QColor(230, 50, 50), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    p.drawPath(self._path(seg))
            s = self._to_screen(self.route[0])
            e = self._to_screen(self.route[-1])
            p.setPen(QPen(Qt.white, 2))
            p.setBrush(QColor(40, 170, 60))
            p.drawEllipse(s, 6, 6)
            p.setBrush(QColor(20, 20, 20))
            p.drawEllipse(e, 6, 6)
        if self.pos:
            q = self._to_screen(self.pos)
            p.setPen(QPen(Qt.white, 2.5))
            p.setBrush(QColor(240, 60, 40))
            p.drawEllipse(q, 8, 8)
        p.setPen(QColor(90, 90, 90))
        p.drawText(QRectF(6, self.height() - 20, self.width() - 12, 16), Qt.AlignLeft,
                   "● start   ● end   blue: film   grey: cut away")

    def _jump_limit(self) -> float:
        # ~ 60 m in mercator units at this latitude is far more than 1 s of travel by bike/car
        if not self.route:
            return 1.0
        lat = math.degrees(2 * math.atan(math.exp(self.route[0][1])) - math.pi / 2)
        return 150.0 / (6378137.0 * max(0.1, math.cos(math.radians(lat))))

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.LeftButton and self.center:
            self._drag = (ev.position(), self.center)
            self._moved = False

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._drag:
            start, c = self._drag
            d = ev.position() - start
            if abs(d.x()) + abs(d.y()) > 3:
                self._moved = True
            s = self._scale()
            self.center = (c[0] - d.x() / s, c[1] + d.y() / s)
            self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._drag and not self._moved and self.route:
            m = self._from_screen(ev.position())
            best = min(range(len(self.route)),
                       key=lambda i: (self.route[i][0] - m[0]) ** 2 + (self.route[i][1] - m[1]) ** 2)
            q = self._to_screen(self.route[best])
            if (q - ev.position()).manhattanLength() < 40:
                self.seekRequested.emit(best)
        self._drag = None

    def mouseDoubleClickEvent(self, _ev: QMouseEvent) -> None:
        self.fit()

    def wheelEvent(self, ev: QWheelEvent) -> None:
        if not self.center:
            return
        before = self._from_screen(ev.position())
        self.zoom = max(0.5, min(400.0, self.zoom * (1.25 if ev.angleDelta().y() > 0 else 0.8)))
        after = self._from_screen(ev.position())
        self.center = (self.center[0] + before[0] - after[0], self.center[1] + before[1] - after[1])
        self.update()
