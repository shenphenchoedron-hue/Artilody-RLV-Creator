"""Timeline of the *edited* film with elevation profile, cut markers and selection."""

from __future__ import annotations

import bisect
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..project import FPS
from .common import fmt_frames

RULER_H = 22
STRIP_H = 58
EDGE_PX = 6
DRAG_PX = 4


class Timeline(QWidget):
    seekRequested = Signal(int)  # output frame
    selectionChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(170)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.total = 0
        self.playhead = 0
        self.joins: List[int] = []
        self.profile: List[float] = []  # elevation per output second
        self.sel_in: Optional[int] = None
        self.sel_out: Optional[int] = None
        self.view0 = 0.0  # first visible frame
        self.view1 = 1.0  # last visible frame
        self._drag: Optional[str] = None  # 'scrub' | 'select' | 'in' | 'out' | 'pan'
        self._drag_anchor = 0
        self._pan_anchor: Tuple[float, float, float] = (0, 0, 0)
        self._press_x = 0.0
        self.out_to_src: Optional[Callable[[int], int]] = None
        self._thumb_keys: List[int] = []
        self._thumbs: Dict[int, QImage] = {}
        self.setToolTip("Drag across the film strip to mark a part, then press Delete to cut it out\n"
                        "Click: move playhead  ·  Drag in the time ruler: scrub  ·  Drag the red edges to adjust\n"
                        "Mouse wheel: zoom  ·  Shift+wheel / middle-drag: scroll")

    # ------------------------------------------------------------- thumbs
    def clear_thumbs(self) -> None:
        self._thumb_keys = []
        self._thumbs = {}
        self.update()

    def add_thumb(self, src_frame: int, img: QImage) -> None:
        if src_frame not in self._thumbs:
            bisect.insort(self._thumb_keys, src_frame)
        self._thumbs[src_frame] = img
        self.update()

    def _thumb_for(self, src: int) -> Optional[QImage]:
        keys = self._thumb_keys
        if not keys:
            return None
        i = bisect.bisect_left(keys, src)
        cands = [k for k in (keys[i - 1] if i > 0 else None, keys[i] if i < len(keys) else None) if k is not None]
        return self._thumbs[min(cands, key=lambda k: abs(k - src))]

    # ---------------------------------------------------------------- model
    def set_data(self, total: int, joins: List[int], profile: List[float], keep_view: bool = False) -> None:
        old_total = self.total
        self.total = total
        self.joins = joins
        self.profile = profile
        if not keep_view or old_total == 0:
            self.view0, self.view1 = 0.0, float(max(1, total))
        elif self.view0 <= 0 and self.view1 >= old_total - 1:
            self.view0, self.view1 = 0.0, float(max(1, total))  # was showing everything: keep doing so
        else:
            span = self.view1 - self.view0
            self.view1 = min(float(max(1, total)), self.view0 + span)
            self.view0 = max(0.0, self.view1 - span)
        self.playhead = min(self.playhead, max(0, total - 1))
        self.update()

    def set_playhead(self, f: int) -> None:
        self.playhead = f
        # keep playhead visible when zoomed in
        span = self.view1 - self.view0
        if span < self.total and (f < self.view0 or f > self.view1):
            self.view0 = max(0.0, min(f - span * 0.1, self.total - span))
            self.view1 = self.view0 + span
        self.update()

    def set_selection(self, a: Optional[int], b: Optional[int]) -> None:
        self.sel_in, self.sel_out = a, b
        self.update()
        self.selectionChanged.emit()

    def selection(self) -> Optional[Tuple[int, int]]:
        if self.sel_in is None or self.sel_out is None:
            return None
        a, b = sorted((self.sel_in, self.sel_out))
        return (a, b) if b > a else None

    # ----------------------------------------------------------- geometry
    def _x(self, f: float) -> float:
        w = max(1, self.width() - 2)
        return 1 + (f - self.view0) / max(1e-9, self.view1 - self.view0) * w

    def _f(self, x: float) -> int:
        w = max(1, self.width() - 2)
        f = self.view0 + (x - 1) / w * (self.view1 - self.view0)
        return int(round(max(0, min(self.total, f))))

    # --------------------------------------------------------------- paint
    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        pal = self.palette()
        p.fillRect(self.rect(), QColor(22, 25, 31))
        if self.total <= 0:
            p.setPen(QColor(150, 150, 150))
            p.drawText(self.rect(), Qt.AlignCenter, "The timeline appears here when a video is open")
            return
        track = QRectF(0, RULER_H, W, H - RULER_H)
        p.fillRect(track, QColor(26, 30, 38))

        # film strip (thumbnails of the edited film)
        strip = QRectF(0, RULER_H, W, STRIP_H)
        p.fillRect(strip, QColor(14, 16, 20))
        if self._thumb_keys and self.out_to_src:
            tw = STRIP_H * 16 / 9
            x = 0.0
            while x < W:
                f = min(self.total - 1, self._f(x + tw / 2))
                img = self._thumb_for(self.out_to_src(f))
                if img is not None:
                    p.drawImage(QRectF(x, RULER_H, tw, STRIP_H), img)
                x += tw
            p.fillRect(QRectF(0, RULER_H + STRIP_H - 1, W, 1), QColor(0, 0, 0))
        prof = QRectF(0, RULER_H + STRIP_H, W, H - RULER_H - STRIP_H)

        # elevation profile
        if len(self.profile) >= 2:
            lo, hi = min(self.profile), max(self.profile)
            rng = max(5.0, hi - lo)
            path = QPainterPath()
            top, bot = prof.top() + 6, prof.bottom() - 4
            first = True
            step = max(1, int(len(self.profile) / max(1, W) / 2))
            s0 = max(0, int(self.view0 / FPS) - 1)
            s1 = min(len(self.profile), int(self.view1 / FPS) + 2)
            for s in range(s0, s1, step):
                x = self._x(s * FPS)
                y = bot - (self.profile[s] - lo) / rng * (bot - top)
                if first:
                    path.moveTo(x, bot)
                    first = False
                path.lineTo(x, y)
            path.lineTo(self._x((s1 - 1) * FPS), bot)
            path.closeSubpath()
            grad = QLinearGradient(0, top, 0, bot)
            grad.setColorAt(0, QColor(61, 139, 253, 150))
            grad.setColorAt(1, QColor(61, 139, 253, 20))
            p.fillPath(path, grad)
            p.setPen(QPen(QColor(110, 170, 255), 1.5))
            p.drawPath(path)
            p.setPen(QColor(170, 190, 210))
            p.setFont(QFont(self.font().family(), 8))
            p.drawText(QRectF(4, prof.top() + 2, 200, 14), Qt.AlignLeft, f"{hi:.0f} m")
            p.drawText(QRectF(4, H - 16, 200, 14), Qt.AlignLeft, f"{lo:.0f} m")
        else:
            p.setPen(QColor(110, 115, 125))
            p.setFont(QFont(self.font().family(), 8))
            p.drawText(QRectF(8, prof.top() + 4, W, 14), Qt.AlignLeft, "No GPS data - no elevation profile")

        # ruler
        p.fillRect(QRectF(0, 0, W, RULER_H), QColor(18, 21, 27))
        span_s = (self.view1 - self.view0) / FPS
        steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]
        target = span_s / max(1, W / 90)
        step = next((s for s in steps if s >= target), 3600)
        p.setPen(QColor(160, 160, 170))
        p.setFont(QFont(self.font().family(), 8))
        t = int(self.view0 / FPS / step) * step
        while t * FPS <= self.view1:
            x = self._x(t * FPS)
            p.drawLine(QPointF(x, RULER_H - 6), QPointF(x, RULER_H))
            p.drawText(QPointF(x + 3, RULER_H - 8), fmt_frames(t * FPS, with_frames=False))
            t += step

        # join (cut) markers
        pen = QPen(QColor(245, 165, 36), 2)
        for j in self.joins:
            if self.view0 <= j <= self.view1:
                x = self._x(j)
                p.setPen(pen)
                p.drawLine(QPointF(x, RULER_H), QPointF(x, H))
                tri = QPainterPath()
                tri.moveTo(x - 5, RULER_H)
                tri.lineTo(x + 5, RULER_H)
                tri.lineTo(x, RULER_H + 7)
                tri.closeSubpath()
                p.fillPath(tri, QColor(245, 165, 36))

        # selection
        sel = self.selection()
        if self.sel_in is not None and sel is None:
            x = self._x(self.sel_in)
            p.setPen(QPen(QColor(255, 80, 80), 2, Qt.DashLine))
            p.drawLine(QPointF(x, RULER_H), QPointF(x, H))
        if sel:
            x0, x1 = self._x(sel[0]), self._x(sel[1])
            r = QRectF(x0, RULER_H, max(2, x1 - x0), H - RULER_H)
            p.fillRect(r, QColor(229, 72, 77, 85))
            p.setPen(QPen(QColor(229, 72, 77), 2))
            p.drawLine(QPointF(x0, RULER_H), QPointF(x0, H))
            p.drawLine(QPointF(x1, RULER_H), QPointF(x1, H))
            if x1 - x0 > 110:
                p.setPen(QColor(255, 220, 220))
                p.drawText(r, Qt.AlignCenter, f"✂ {fmt_frames(sel[1] - sel[0])}\nDelete to cut")

        if not sel:
            p.setPen(QColor(150, 160, 175))
            p.setFont(QFont(self.font().family(), 9))
            p.drawText(QRectF(8, H - 20, W - 16, 16), Qt.AlignRight | Qt.AlignVCenter,
                       "Drag across the timeline to mark a part  ·  Delete = cut it out  ·  Ctrl+Z = undo")

        # playhead
        x = self._x(self.playhead)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawLine(QPointF(x, 0), QPointF(x, H))
        head = QPainterPath()
        head.moveTo(x - 6, 0)
        head.lineTo(x + 6, 0)
        head.lineTo(x, 9)
        head.closeSubpath()
        p.fillPath(head, QColor(255, 255, 255))

        # zoom indicator
        if self.view1 - self.view0 < self.total - 1:
            p.fillRect(QRectF(0, H - 3, W, 3), QColor(60, 60, 60))
            a = self.view0 / self.total * W
            b = self.view1 / self.total * W
            p.fillRect(QRectF(a, H - 3, max(4, b - a), 3), QColor(180, 180, 180))
        del pal

    # --------------------------------------------------------------- mouse
    def _near_edge(self, x: float) -> Optional[str]:
        sel = self.selection()
        if not sel:
            return None
        if abs(x - self._x(sel[0])) <= EDGE_PX:
            return "in"
        if abs(x - self._x(sel[1])) <= EDGE_PX:
            return "out"
        return None

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if self.total <= 0:
            return
        x = ev.position().x()
        if ev.button() == Qt.MiddleButton or (ev.button() == Qt.LeftButton and ev.modifiers() & Qt.AltModifier):
            self._drag = "pan"
            self._pan_anchor = (x, self.view0, self.view1)
            return
        if ev.button() != Qt.LeftButton:
            return
        edge = self._near_edge(x)
        if edge:
            sel = self.selection()
            assert sel
            self.sel_in, self.sel_out = sel
            self._drag = edge
        elif ev.position().y() <= RULER_H:
            self._drag = "scrub"
            self.seekRequested.emit(min(self._f(x), self.total - 1))
        else:
            # click = move playhead, drag = mark a part
            self._drag = "press"
            self._press_x = x
            self._drag_anchor = self._f(x)
            if ev.modifiers() & Qt.ShiftModifier:
                self._drag = "select"
                self.set_selection(self._drag_anchor, self._drag_anchor)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        x = ev.position().x()
        if self._drag is None:
            self.setCursor(Qt.SizeHorCursor if self._near_edge(x) else Qt.ArrowCursor)
            return
        f = self._f(x)
        if self._drag == "press" and abs(x - self._press_x) >= DRAG_PX:
            self._drag = "select"
        if self._drag == "scrub":
            self.seekRequested.emit(min(f, self.total - 1))
        elif self._drag == "select":
            self.set_selection(self._drag_anchor, f)
            self.seekRequested.emit(min(f, self.total - 1))
        elif self._drag == "in":
            self.set_selection(f, self.sel_out)
            self.seekRequested.emit(min(f, self.total - 1))
        elif self._drag == "out":
            self.set_selection(self.sel_in, f)
            self.seekRequested.emit(min(f, self.total - 1))
        elif self._drag == "pan":
            x0, v0, v1 = self._pan_anchor
            span = v1 - v0
            df = (x0 - x) / max(1, self.width()) * span
            self.view0 = max(0.0, min(self.total - span, v0 + df))
            self.view1 = self.view0 + span
            self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._drag == "press":
            self.seekRequested.emit(min(self._f(ev.position().x()), self.total - 1))
        elif self._drag == "select" and self.selection() is None:
            self.set_selection(None, None)
        self._drag = None

    def wheelEvent(self, ev: QWheelEvent) -> None:
        if self.total <= 0:
            return
        dy = ev.angleDelta().y()
        dx = ev.angleDelta().x()
        span = self.view1 - self.view0
        if dx and not dy or ev.modifiers() & Qt.ShiftModifier:
            d = -(dx or dy) / 120 * span * 0.1
            self.view0 = max(0.0, min(self.total - span, self.view0 + d))
            self.view1 = self.view0 + span
        else:
            factor = 0.8 if dy > 0 else 1.25
            anchor = self.view0 + (ev.position().x() / max(1, self.width())) * span
            new_span = max(FPS * 2.0, min(float(self.total), span * factor))
            r = (anchor - self.view0) / span if span else 0.5
            self.view0 = max(0.0, anchor - r * new_span)
            self.view1 = min(float(self.total), self.view0 + new_span)
            self.view0 = max(0.0, self.view1 - new_span)
        self.update()

    def zoom_fit(self) -> None:
        self.view0, self.view1 = 0.0, float(max(1, self.total))
        self.update()
