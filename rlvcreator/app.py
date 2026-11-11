"""Application entry point."""

from __future__ import annotations

import os
import sys


def selftest() -> int:
    """Non-GUI check used by the release builds: FFmpeg, HEVC encoder and Qt Multimedia."""
    from PySide6 import QtMultimedia

    assert QtMultimedia.QMediaPlayer is not None

    from . import __version__
    from .ffmpeg import detect_encoders, find_ffmpeg

    ff = find_ffmpeg()
    print("Artilody RLV Creator", __version__)
    print("ffmpeg:", ff)
    encs = [e.name for e in detect_encoders(ff)] if ff else []
    print("HEVC encoders:", encs)
    return 0 if ff and "libx265" in encs else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if "--version" in sys.argv:
        from . import __version__
        print(__version__)
        return 0
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")
    # On Wayland, Qt's default shared-memory backing store sometimes hands popups and dialogs
    # to the compositor with a mismatched buffer stride (combo box lists and message boxes
    # show skewed/diagonal garbage until repainted). Composing widget windows through Qt RHI
    # (OpenGL/EGL buffers) avoids the shm path entirely and renders them correctly.
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") \
            and os.environ.get("QT_QPA_PLATFORM", "wayland").startswith("wayland"):
        os.environ.setdefault("QT_WIDGETS_RHI", "1")
        os.environ.setdefault("QT_WIDGETS_RHI_BACKEND", "opengl")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, __version__
    from .ui.main_window import MainWindow

    QCoreApplication.setOrganizationName("Artilody")
    QCoreApplication.setApplicationName("RLV Creator")
    QCoreApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_NAME)
    from .ui import theme
    theme.apply(app)
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("artilody-rlv-creator")
    win = MainWindow()
    win.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        proj = [a for a in args if a.lower().endswith(".rlvproj")]
        if proj:
            win.load([], proj[0])
        else:
            win.load(args)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
