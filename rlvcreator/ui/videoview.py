"""Video display based on QGraphicsVideoItem (works the same on all platforms)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView


class VideoView(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setFocusPolicy(Qt.NoFocus)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.item = QGraphicsVideoItem()
        self.item.setSize(QSizeF(1920, 1080))
        self.scene_.addItem(self.item)
        self.item.nativeSizeChanged.connect(self._native_size)
        self._fit()

    def _native_size(self, size: QSizeF) -> None:
        if size.width() > 0 and size.height() > 0:
            self.item.setSize(size)
            self._fit()

    def _fit(self) -> None:
        r = QRectF(self.item.pos(), self.item.size())
        self.scene_.setSceneRect(r)
        self.fitInView(r, Qt.KeepAspectRatio)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._fit()

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        self._fit()
