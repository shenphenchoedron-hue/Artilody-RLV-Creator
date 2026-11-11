"""Export dialog: writes the MP4 (HEVC 1080p30), GPX and XML files."""

from __future__ import annotations

import os
import time
from typing import List, Optional

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QSlider, QVBoxLayout)

from .. import exporters
from ..ffmpeg import Encoder, ExportSettings, Renderer, build_command, detect_encoders, find_ffmpeg
from ..project import Project, sanitize_name
from .common import fmt_frames


class _EncoderProbe(QThread):
    found = Signal(list)

    def __init__(self, ffmpeg: str) -> None:
        super().__init__()
        self.ffmpeg = ffmpeg

    def run(self) -> None:
        self.found.emit(detect_encoders(self.ffmpeg))


class _Bridge(QObject):
    progress = Signal(float, str)
    done = Signal(bool, str)


class ExportDialog(QDialog):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export RLV")
        self.setMinimumWidth(560)
        self.project = project
        self.settings = QSettings()
        self.renderer: Optional[Renderer] = None
        self.ffmpeg = find_ffmpeg(self.settings.value("ffmpeg_path", "", str) or None)
        self._t0 = 0.0
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_progress)
        self._bridge.done.connect(self._on_done)

        lay = QVBoxLayout(self)
        files = QGroupBox("Files")
        f = QFormLayout(files)
        row = QHBoxLayout()
        default_dir = self.settings.value("export_dir", "", str) or os.path.dirname(project.chapters[0].path)
        self.folder = QLineEdit(default_dir)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder)
        row.addWidget(browse)
        f.addRow("Folder:", row)
        self.name = QLineEdit(sanitize_name(project.name or "route"))
        self.name.textChanged.connect(self._update_names)
        f.addRow("Name:", self.name)
        self.do_video = QCheckBox()
        self.do_gpx = QCheckBox()
        self.do_xml = QCheckBox()
        for cb in (self.do_video, self.do_gpx, self.do_xml):
            cb.setChecked(True)
        f.addRow(self.do_video)
        f.addRow(self.do_gpx)
        f.addRow(self.do_xml)
        lay.addWidget(files)
        if not project.has_gps:
            self.do_gpx.setChecked(False)
            self.do_gpx.setEnabled(False)

        vid = QGroupBox("Video:  MP4  ·  H.265 / HEVC  ·  1920×1080 (16:9)  ·  30 fps")
        v = QFormLayout(vid)
        self.encoder = QComboBox()
        self.encoder.addItem("Detecting encoders…", "libx265")
        v.addRow("Encoder:", self.encoder)
        self.preset = QComboBox()
        for label, val in [("Fastest", "ultrafast"), ("Very fast", "veryfast"), ("Fast", "fast"),
                           ("Balanced", "medium"), ("Small file (slow)", "slow")]:
            self.preset.addItem(label, val)
        self.preset.setCurrentIndex(self.settings.value("preset_idx", 2, int))
        self.preset.setToolTip("Speed / file size trade-off for the x265 software encoder")
        v.addRow("Speed:", self.preset)
        qrow = QHBoxLayout()
        self.quality = QSlider(Qt.Horizontal)
        self.quality.setRange(0, 100)
        self.quality.setValue(self.settings.value("quality", 62, int))
        self.qlabel = QLabel()
        self.quality.valueChanged.connect(self._qlabel)
        qrow.addWidget(self.quality)
        qrow.addWidget(self.qlabel)
        v.addRow("Quality:", qrow)
        self.fit = QComboBox()
        self.fit.addItem("Fill 16:9 (crop top/bottom if needed)", "crop")
        self.fit.addItem("Fit inside 16:9 (black bars if needed)", "pad")
        self.fit.setCurrentIndex(self.settings.value("fit_idx", 0, int))
        v.addRow("Aspect:", self.fit)
        self.audio = QCheckBox("Include audio")
        self.audio.setChecked(self.settings.value("audio", False, bool) and project.has_audio)
        self.audio.setEnabled(project.has_audio)
        v.addRow(self.audio)
        lay.addWidget(vid)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        btns.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._export)
        btns.addWidget(self.close_btn)
        btns.addWidget(self.export_btn)
        lay.addLayout(btns)

        self._qlabel()
        self._update_names()
        if self.ffmpeg:
            self._probe = _EncoderProbe(self.ffmpeg)
            self._probe.found.connect(self._set_encoders)
            self._probe.start()
        else:
            self.encoder.clear()
            self.encoder.addItem("FFmpeg not found", "")
            self.do_video.setChecked(False)
            self.do_video.setEnabled(False)
            self.status.setText("⚠ FFmpeg was not found. Install FFmpeg or set its path under Settings to export video.")

    # ------------------------------------------------------------------ UI
    def _qlabel(self) -> None:
        q = self.quality.value()
        crf = int(round(34 - q * 0.16))
        self.qlabel.setText(f"{q}  (CRF {crf})")

    def _set_encoders(self, encs: List[Encoder]) -> None:
        self.encoder.clear()
        if not encs:
            self.encoder.addItem("No HEVC encoder available in this FFmpeg", "")
            self.do_video.setChecked(False)
            self.do_video.setEnabled(False)
            return
        for e in encs:
            self.encoder.addItem(e.label, e.name)
        last = self.settings.value("encoder", "libx265", str)
        i = self.encoder.findData(last)
        self.encoder.setCurrentIndex(max(0, i))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Export folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def _update_names(self) -> None:
        n = sanitize_name(self.name.text() or "route")
        self.do_video.setText(f"Video   {n}.mp4")
        self.do_gpx.setText(f"GPS track   {n}.gpx")
        self.do_xml.setText(f"RLV description   {n}.xml")
        p = self.project
        length, up = p.stats()
        self.summary.setText(f"Film length {fmt_frames(p.output_frames)} = {p.output_frames} frames  ·  "
                             f"{len(p.output_points())} GPS points  ·  {length / 1000:.2f} km  ·  {up:.0f} m ascent")

    # -------------------------------------------------------------- export
    def _export(self) -> None:
        if self.renderer:
            self.renderer.cancel()
            return
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Export", "Please choose an existing folder.")
            return
        name = sanitize_name(self.name.text() or "route")
        mp4_path = os.path.join(folder, name + ".mp4")
        gpx_path = os.path.join(folder, name + ".gpx")
        xml_path = os.path.join(folder, name + ".xml")
        targets = [p for p, cb in ((mp4_path, self.do_video), (gpx_path, self.do_gpx), (xml_path, self.do_xml))
                   if cb.isChecked()]
        if not targets:
            return
        src_paths = {os.path.abspath(c.path) for c in self.project.chapters}
        if any(os.path.abspath(t) in src_paths for t in targets):
            QMessageBox.warning(self, "Export", "The export would overwrite a source video. Choose another name.")
            return
        existing = [t for t in targets if os.path.exists(t)]
        if existing and QMessageBox.question(
                self, "Export", "These files exist and will be overwritten:\n\n"
                + "\n".join(os.path.basename(e) for e in existing)) != QMessageBox.Yes:
            return
        self.settings.setValue("export_dir", folder)
        self.settings.setValue("encoder", self.encoder.currentData())
        self.settings.setValue("preset_idx", self.preset.currentIndex())
        self.settings.setValue("quality", self.quality.value())
        self.settings.setValue("fit_idx", self.fit.currentIndex())
        self.settings.setValue("audio", self.audio.isChecked())

        self.project.name = name
        try:
            if self.do_gpx.isChecked():
                exporters.write_gpx(self.project, gpx_path)
            if self.do_xml.isChecked():
                exporters.write_xml(self.project, xml_path, os.path.basename(mp4_path), os.path.basename(gpx_path))
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        if not self.do_video.isChecked():
            self.status.setText("✔ Files written to " + folder)
            return
        st = ExportSettings(encoder=self.encoder.currentData() or "libx265", quality=self.quality.value(),
                            preset=self.preset.currentData(), fit=self.fit.currentData(),
                            audio=self.audio.isChecked())
        try:
            assert self.ffmpeg
            args, total = build_command(self.ffmpeg, self.project, mp4_path, st)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._mp4 = mp4_path
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText("Rendering video…")
        self.export_btn.setText("Cancel")
        self.close_btn.setEnabled(False)
        self._t0 = time.monotonic()
        self.renderer = Renderer(args, total, self._bridge.progress.emit, self._bridge.done.emit)
        self.renderer.start()

    def _on_progress(self, frac: float, speed: str) -> None:
        self.progress.setValue(int(frac * 1000))
        el = time.monotonic() - self._t0
        eta = ""
        if frac > 0.01:
            rem = el / frac - el
            eta = f"  ·  about {int(rem // 60)} min {int(rem % 60)} s left"
        self.status.setText(f"Rendering video… {frac * 100:.1f} %  (speed {speed or '-'}){eta}")

    def _on_done(self, ok: bool, msg: str) -> None:
        self.renderer = None
        self.export_btn.setText("Export")
        self.close_btn.setEnabled(True)
        if ok:
            self.progress.setValue(1000)
            el = time.monotonic() - self._t0
            self.status.setText(f"✔ Export finished in {int(el // 60)} min {int(el % 60)} s  -  "
                                f"{os.path.dirname(self._mp4)}")
        else:
            self.progress.setVisible(False)
            if os.path.exists(self._mp4) and msg == "Export cancelled":
                try:
                    os.remove(self._mp4)
                except OSError:
                    pass
            self.status.setText("✖ " + msg.splitlines()[0] if msg else "✖ Export failed")
            if msg != "Export cancelled":
                QMessageBox.critical(self, "Export failed", msg)

    def reject(self) -> None:
        if self.renderer:
            if QMessageBox.question(self, "Export", "Cancel the running export?") != QMessageBox.Yes:
                return
            self.renderer.cancel()
            self.renderer.thread.join(timeout=5)
            self.renderer = None
        super().reject()
