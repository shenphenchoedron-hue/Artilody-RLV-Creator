"""Start screen shown before a video is opened."""

from __future__ import annotations

import os

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import icons, theme


class _Step(QWidget):
    def __init__(self, num: str, icon_name: str, title: str, text: str) -> None:
        super().__init__()
        self.setFixedWidth(180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)
        top = QHBoxLayout()
        badge = QLabel(num)
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background: {theme.ACCENT}; color: white; border-radius: 13px; font-weight: 700;")
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, theme.TEXT, 26))
        top.addWidget(badge)
        top.addStretch()
        top.addWidget(ic)
        lay.addLayout(top)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; font-size: 11pt;")
        lay.addWidget(t)
        d = QLabel(text)
        d.setWordWrap(True)
        d.setObjectName("muted")
        lay.addWidget(d)
        lay.addStretch()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)


class WelcomeScreen(QWidget):
    openVideos = Signal()
    openProject = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hover = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.addStretch(2)

        logo = QLabel()
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "icon.png")
        if os.path.exists(path):
            logo.setPixmap(QPixmap(path).scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)

        title = QLabel("Artilody RLV Creator")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24pt; font-weight: 800; margin-top: 8px;")
        lay.addWidget(title)
        sub = QLabel("Turn your GoPro rides into Real Life Videos")
        sub.setAlignment(Qt.AlignCenter)
        sub.setObjectName("muted")
        sub.setStyleSheet("font-size: 12pt;")
        lay.addWidget(sub)
        lay.addSpacing(14)

        row = QHBoxLayout()
        row.addStretch()
        b = QPushButton("  Open GoPro video(s)…")
        b.setObjectName("primary")
        b.setIcon(icons.icon("folder", "#ffffff"))
        b.setIconSize(QSize(22, 22))
        b.setMinimumHeight(48)
        b.setStyleSheet("font-size: 12pt; padding: 8px 28px; border-radius: 10px;")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.openVideos.emit)
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addStretch()
        b2 = QPushButton("or open a saved project")
        b2.setObjectName("link")
        b2.setCursor(Qt.PointingHandCursor)
        b2.clicked.connect(self.openProject.emit)
        row2.addWidget(b2)
        row2.addStretch()
        lay.addLayout(row2)
        hint = QLabel("You can also drop video files here. Chapters of one ride (GH01…, GH02…) are joined automatically.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addSpacing(16)

        steps = QHBoxLayout()
        steps.setSpacing(14)
        steps.addStretch()
        steps.addWidget(_Step("1", "film", "Open", "GPS data is read straight from the GoPro video."))
        steps.addWidget(_Step("2", "scissors", "Cut", "Drag across the timeline and press Delete. "
                                                     "Video and GPS are cut together. Ctrl+Z undoes."))
        steps.addWidget(_Step("3", "export", "Export", "MP4 (HEVC 1080p, 30 fps), GPX and XML, ready to ride."))
        steps.addStretch()
        lay.addLayout(steps)
        lay.addStretch(3)

    def set_drag_hover(self, on: bool) -> None:
        self._hover = on
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#1b2230"))
        g.setColorAt(1, QColor(theme.BG))
        path = QPainterPath()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path.addRoundedRect(r, 14, 14)
        p.fillPath(path, g)
        pen = QPen(QColor(theme.ACCENT if self._hover else theme.BORDER), 2 if self._hover else 1.5, Qt.DashLine)
        p.setPen(pen)
        p.drawPath(path)
