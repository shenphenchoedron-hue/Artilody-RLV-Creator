"""Background generation of timeline thumbnails with FFmpeg."""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional, Tuple

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from ..ffmpeg import find_ffmpeg
from ..project import FPS, Project

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
THUMB_H = 54


class ThumbnailLoader(QThread):
    thumbReady = Signal(int, QImage)  # source frame, image

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.ffmpeg: Optional[str] = find_ffmpeg()
        self._stop = False
        total = project.source_frames
        n = max(2, min(120, total // FPS + 1))
        step = total / n
        self.jobs: List[Tuple[int, str, float]] = []
        for i in range(n):
            src = int(i * step + step / 2)
            ci, local = project.chapter_for_frame(src)
            self.jobs.append((src, project.chapters[ci].path, local))
        # coarse-to-fine order so the whole strip fills quickly
        order: List[int] = []
        stride = 1
        while stride * 2 < n:
            stride *= 2
        seen = set()
        while stride >= 1:
            for i in range(0, n, stride):
                if i not in seen:
                    seen.add(i)
                    order.append(i)
            stride //= 2
        self.jobs = [self.jobs[i] for i in order]

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        if not self.ffmpeg:
            return
        for src, path, t in self.jobs:
            if self._stop:
                return
            try:
                r = subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", path,
                                    "-frames:v", "1", "-vf", f"scale=-2:{THUMB_H}", "-f", "image2pipe",
                                    "-c:v", "ppm", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=30, creationflags=_NO_WINDOW)
            except Exception:
                continue
            if self._stop:
                return
            img = QImage.fromData(r.stdout, "PPM")
            if not img.isNull():
                self.thumbReady.emit(src, img)
