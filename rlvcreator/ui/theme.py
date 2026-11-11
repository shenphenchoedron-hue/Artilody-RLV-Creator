"""Dark application theme (palette + style sheet)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#16191f"        # window background
SURFACE = "#1e222a"   # panels / cards
SURFACE2 = "#262b35"  # inputs, raised elements
BORDER = "#323846"
TEXT = "#e6e9ef"
MUTED = "#8b93a3"
ACCENT = "#3d8bfd"
ACCENT_HOVER = "#5a9dff"
DANGER = "#e5484d"
DANGER_HOVER = "#f2555a"
SUCCESS = "#30a46c"
WARN = "#f5a524"

STYLE = f"""
* {{ outline: 0; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-size: 10pt; }}
QToolTip {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}

QMenuBar {{ background: {BG}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {SURFACE2}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::item:disabled {{ color: {MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

QToolBar {{ background: {BG}; border: none; padding: 6px 8px; spacing: 6px; }}
QToolBar::separator {{ width: 1px; background: {BORDER}; margin: 6px 6px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 6px 10px; }}
QToolButton:hover {{ background: {SURFACE2}; border-color: {BORDER}; }}
QToolButton:pressed, QToolButton:checked {{ background: {BORDER}; }}
QToolButton:disabled {{ color: #5a6170; }}
QToolButton#primary {{ background: {ACCENT}; color: white; font-weight: 600; padding: 7px 16px; }}
QToolButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QToolButton#primary:disabled {{ background: {SURFACE2}; color: #5a6170; }}

QPushButton {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 16px; }}
QPushButton:hover {{ background: #2f3541; border-color: #3d4556; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #5a6170; background: {SURFACE}; border-color: {SURFACE2}; }}
QPushButton:default, QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton:default:hover, QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#danger {{ background: {DANGER}; border-color: {DANGER}; color: white; font-weight: 600; }}
QPushButton#danger:hover {{ background: {DANGER_HOVER}; }}
QPushButton#danger:disabled {{ background: {SURFACE}; border-color: {SURFACE2}; color: #5a6170; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; }}
QPushButton#link:hover {{ color: {ACCENT_HOVER}; text-decoration: underline; }}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 7px; padding: 6px 8px;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:read-only {{ color: {MUTED}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url(@chev_down); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url(@chev_down_dis); }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ border: none; width: 20px; background: transparent; }}
QAbstractSpinBox::up-arrow {{ image: url(@chev_up); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url(@chev_down); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;
    selection-background-color: {ACCENT}; selection-color: white; padding: 4px; }}

QTabWidget::pane {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 16px; margin-right: 2px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QGroupBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 14px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {MUTED}; font-weight: 600; }}

QTableWidget, QListWidget {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: {BORDER}; alternate-background-color: #2a303b; selection-background-color: {ACCENT}; }}
QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px; font-weight: 600; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QSlider::groove:horizontal {{ height: 6px; background: {SURFACE2}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; margin: -6px 0; border-radius: 8px; }}

QProgressBar {{ background: {SURFACE2}; border: none; border-radius: 6px; height: 12px; text-align: center; color: white; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {BORDER}; background: {SURFACE2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(@check); }}

QSplitter::handle {{ background: transparent; width: 8px; }}
QStatusBar {{ background: {BG}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}

QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#chip {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 4px 8px;
    font-family: monospace; }}
QLabel#time {{ background: #0f1115; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 10px;
    font-family: monospace; font-size: 11pt; color: white; }}
QToolButton#play {{ background: {ACCENT}; border-radius: 20px; padding: 8px; }}
QToolButton#play:hover {{ background: {ACCENT_HOVER}; }}
QToolButton#play:disabled {{ background: {SURFACE2}; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    c = QColor
    pal.setColor(QPalette.Window, c(BG))
    pal.setColor(QPalette.WindowText, c(TEXT))
    pal.setColor(QPalette.Base, c(SURFACE2))
    pal.setColor(QPalette.AlternateBase, c(SURFACE))
    pal.setColor(QPalette.ToolTipBase, c(SURFACE2))
    pal.setColor(QPalette.ToolTipText, c(TEXT))
    pal.setColor(QPalette.Text, c(TEXT))
    pal.setColor(QPalette.Button, c(SURFACE2))
    pal.setColor(QPalette.ButtonText, c(TEXT))
    pal.setColor(QPalette.BrightText, c("#ffffff"))
    pal.setColor(QPalette.Highlight, c(ACCENT))
    pal.setColor(QPalette.HighlightedText, c("#ffffff"))
    pal.setColor(QPalette.Link, c(ACCENT))
    pal.setColor(QPalette.PlaceholderText, c(MUTED))
    pal.setColor(QPalette.Mid, c(MUTED))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c("#5a6170"))
    app.setPalette(pal)
    from . import icons
    style = STYLE
    for name, path in sorted(icons.register_resources().items(), key=lambda kv: -len(kv[0])):
        style = style.replace("@" + name, path)
    app.setStyleSheet(style)
