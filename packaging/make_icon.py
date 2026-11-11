"""Generates the application icon (PNG, ICO, ICNS). Run: python packaging/make_icon.py"""
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

app = QGuiApplication(sys.argv)
S = 1024
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
bg = QPainterPath()
bg.addRoundedRect(QRectF(40, 40, S - 80, S - 80), 200, 200)
g = QLinearGradient(0, 0, 0, S)
g.setColorAt(0, QColor(46, 134, 222))
g.setColorAt(1, QColor(18, 52, 110))
p.fillPath(bg, g)
p.setClipPath(bg)
# mountains
m = QPainterPath()
m.moveTo(40, 760)
for x, y in [(230, 520), (360, 640), (560, 360), (760, 600), (880, 500), (984, 640), (984, 984), (40, 984)]:
    m.lineTo(x, y)
m.closeSubpath()
p.fillPath(m, QColor(255, 255, 255, 60))
# road
road = QPainterPath()
road.moveTo(330, 984)
road.cubicTo(420, 820, 640, 820, 560, 640)
road.lineTo(600, 640)
road.cubicTo(720, 820, 560, 860, 700, 984)
road.closeSubpath()
p.fillPath(road, QColor(40, 40, 46))
p.setPen(QPen(QColor(255, 200, 0), 16, Qt.DashLine, Qt.RoundCap))
c = QPainterPath()
c.moveTo(515, 984)
c.cubicTo(560, 840, 680, 820, 580, 640)
p.drawPath(c)
# play button
p.setClipping(False)
p.setPen(Qt.NoPen)
p.setBrush(QColor(255, 255, 255, 235))
p.drawEllipse(QPointF(512, 330), 190, 190)
tri = QPainterPath()
tri.moveTo(462, 230)
tri.lineTo(462, 430)
tri.lineTo(632, 330)
tri.closeSubpath()
p.fillPath(tri, QColor(220, 60, 50))
p.end()

here = os.path.dirname(os.path.abspath(__file__))
res = os.path.join(here, "..", "rlvcreator", "resources")
png = os.path.join(res, "icon.png")
img.scaled(512, 512, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(png)
try:
    from PIL import Image
    im = Image.open(png)
    im.save(os.path.join(here, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big = os.path.join(here, "icon_1024.png")
    img.save(big)
    Image.open(big).save(os.path.join(here, "icon.icns"))
    os.remove(big)
except ImportError:
    print("Pillow not installed - only PNG written")
print("ok")
