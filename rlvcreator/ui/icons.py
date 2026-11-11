"""Small vector icon set drawn with QPainter (crisp at any size, matches the dark theme)."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from typing import Callable, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

S = 64  # drawing grid
Painter = Callable[[QPainter, QColor], None]


def _pen(c: QColor, w: float = 5.5) -> QPen:
    return QPen(c, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _tri(x0: float, y0: float, x1: float, y1: float, x2: float, y2: float) -> QPainterPath:
    p = QPainterPath()
    p.moveTo(x0, y0)
    p.lineTo(x1, y1)
    p.lineTo(x2, y2)
    p.closeSubpath()
    return p


def _play(p: QPainter, c: QColor) -> None:
    p.fillPath(_tri(20, 12, 20, 52, 52, 32), c)


def _pause(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(16, 12, 11, 40), 3, 3)
    p.drawRoundedRect(QRectF(37, 12, 11, 40), 3, 3)


def _skip_start(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(12, 14, 7, 36), 2, 2)
    p.fillPath(_tri(52, 14, 52, 50, 22, 32), c)


def _skip_end(p: QPainter, c: QColor) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(45, 14, 7, 36), 2, 2)
    p.fillPath(_tri(12, 14, 12, 50, 42, 32), c)


def _frame_back(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 6))
    p.drawPolyline([QPointF(38, 16), QPointF(22, 32), QPointF(38, 48)])


def _frame_fwd(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 6))
    p.drawPolyline([QPointF(26, 16), QPointF(42, 32), QPointF(26, 48)])


def _sec_back(p: QPainter, c: QColor) -> None:
    p.fillPath(_tri(32, 16, 32, 48, 8, 32), c)
    p.fillPath(_tri(56, 16, 56, 48, 32, 32), c)


def _sec_fwd(p: QPainter, c: QColor) -> None:
    p.fillPath(_tri(8, 16, 8, 48, 32, 32), c)
    p.fillPath(_tri(32, 16, 32, 48, 56, 32), c)


def _undo(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c))
    path = QPainterPath()
    path.moveTo(16, 26)
    path.lineTo(40, 26)
    path.cubicTo(58, 26, 58, 52, 40, 52)
    path.lineTo(26, 52)
    p.drawPath(path)
    p.drawPolyline([QPointF(26, 14), QPointF(14, 26), QPointF(26, 38)])


def _redo(p: QPainter, c: QColor) -> None:
    p.save()
    p.translate(S, 0)
    p.scale(-1, 1)
    _undo(p, c)
    p.restore()


def _scissors(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(18, 46), 8, 8)
    p.drawEllipse(QPointF(46, 46), 8, 8)
    p.drawLine(QPointF(23, 40), QPointF(46, 10))
    p.drawLine(QPointF(41, 40), QPointF(18, 10))


def _folder(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    path = QPainterPath()
    path.moveTo(8, 50)
    path.lineTo(8, 16)
    path.lineTo(24, 16)
    path.lineTo(30, 22)
    path.lineTo(56, 22)
    path.lineTo(56, 50)
    path.closeSubpath()
    p.drawPath(path)


def _save(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    path = QPainterPath()
    path.moveTo(10, 10)
    path.lineTo(44, 10)
    path.lineTo(54, 20)
    path.lineTo(54, 54)
    path.lineTo(10, 54)
    path.closeSubpath()
    p.drawPath(path)
    p.drawRect(QRectF(20, 10, 20, 12))
    p.drawRect(QRectF(19, 34, 26, 20))


def _export(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5.5))
    p.drawPolyline([QPointF(12, 34), QPointF(12, 54), QPointF(52, 54), QPointF(52, 34)])
    p.drawLine(QPointF(32, 40), QPointF(32, 8))
    p.drawPolyline([QPointF(20, 20), QPointF(32, 8), QPointF(44, 20)])


def _film(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 5))
    p.drawRoundedRect(QRectF(8, 14, 48, 36), 6, 6)
    p.fillPath(_tri(27, 23, 27, 41, 41, 32), c)


def _volume(p: QPainter, c: QColor, muted: bool = False) -> None:
    path = QPainterPath()
    path.moveTo(8, 24)
    path.lineTo(18, 24)
    path.lineTo(32, 12)
    path.lineTo(32, 52)
    path.lineTo(18, 40)
    path.lineTo(8, 40)
    path.closeSubpath()
    p.fillPath(path, c)
    p.setPen(_pen(c, 5))
    if muted:
        p.drawLine(QPointF(40, 24), QPointF(56, 40))
        p.drawLine(QPointF(56, 24), QPointF(40, 40))
    else:
        p.drawArc(QRectF(30, 20, 16, 24), -60 * 16, 120 * 16)
        p.drawArc(QRectF(30, 12, 28, 40), -60 * 16, 120 * 16)


def _mark_in(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 6))
    p.drawPolyline([QPointF(30, 12), QPointF(18, 12), QPointF(18, 52), QPointF(30, 52)])
    p.fillPath(_tri(30, 22, 30, 42, 48, 32), c)


def _mark_out(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 6))
    p.drawPolyline([QPointF(34, 12), QPointF(46, 12), QPointF(46, 52), QPointF(34, 52)])
    p.fillPath(_tri(34, 22, 34, 42, 16, 32), c)


def _trim_start(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 6))
    p.drawLine(QPointF(40, 10), QPointF(40, 54))
    p.setPen(_pen(c, 5))
    p.drawLine(QPointF(10, 32), QPointF(30, 32))
    p.drawPolyline([QPointF(20, 22), QPointF(10, 32), QPointF(20, 42)])


def _trim_end(p: QPainter, c: QColor) -> None:
    p.save()
    p.translate(S, 0)
    p.scale(-1, 1)
    _trim_start(p, c)
    p.restore()


def _check(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 8))
    p.drawPolyline([QPointF(14, 33), QPointF(27, 46), QPointF(50, 20)])


def _chev_down(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 7))
    p.drawPolyline([QPointF(16, 24), QPointF(32, 40), QPointF(48, 24)])


def _chev_up(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 7))
    p.drawPolyline([QPointF(16, 40), QPointF(32, 24), QPointF(48, 40)])


PAINTERS: Dict[str, Painter] = {
    "chev_down": _chev_down, "chev_up": _chev_up,
    "play": _play, "pause": _pause, "skip_start": _skip_start, "skip_end": _skip_end,
    "frame_back": _frame_back, "frame_fwd": _frame_fwd, "sec_back": _sec_back, "sec_fwd": _sec_fwd,
    "undo": _undo, "redo": _redo, "scissors": _scissors, "folder": _folder, "save": _save,
    "export": _export, "film": _film, "volume": lambda p, c: _volume(p, c, False),
    "mute": lambda p, c: _volume(p, c, True), "mark_in": _mark_in, "mark_out": _mark_out,
    "trim_start": _trim_start, "trim_end": _trim_end, "check": _check,
}


def pixmap(name: str, color: str = "#e6e9ef", size: int = 64) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / S, size / S)
    PAINTERS[name](p, QColor(color))
    p.end()
    return pm


@lru_cache(maxsize=None)
def icon(name: str, color: str = "#e6e9ef") -> QIcon:
    ic = QIcon()
    for size in (16, 24, 32, 48, 64):
        ic.addPixmap(pixmap(name, color, size), QIcon.Normal)
        ic.addPixmap(pixmap(name, "#596070", size), QIcon.Disabled)
    return ic


_resources: Dict[str, str] = {}


def register_resources() -> Dict[str, str]:
    """Write small images needed by the style sheet to a cache folder; returns name -> path."""
    if not _resources:
        d = os.path.join(tempfile.gettempdir(), "artilody-rlv-creator")
        os.makedirs(d, exist_ok=True)
        for name, color, size in (("check", "#ffffff", 36), ("chev_down", "#aab2c0", 24),
                                  ("chev_up", "#aab2c0", 24), ("chev_down_dis", "#4a5160", 24)):
            path = os.path.join(d, name + ".png").replace("\\", "/")
            pixmap(name.replace("_dis", ""), color, size).save(path)
            _resources[name] = path
    return _resources
