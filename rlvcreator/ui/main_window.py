"""Main application window."""

from __future__ import annotations

import os
import traceback
from typing import List, Optional

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QSplitter, QStackedWidget, QStyle, QTabWidget, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget, QAbstractItemView)

from .. import __version__, exporters
from ..project import FPS, Project
from ..sensors import load_sensor_file
from .common import fmt_distance, fmt_frames
from .export_dialog import ExportDialog
from .mapview import MapView
from .panels import CutsPanel, GpsPanel, RoutePanel
from .player import EditedPlayer
from .timeline import Timeline
from .videoview import VideoView

VIDEO_FILTER = "GoPro / MP4 video (*.mp4 *.MP4 *.mov *.MOV *.lrv *.LRV);;All files (*)"
PROJECT_FILTER = "RLV Creator project (*.rlvproj);;All files (*)"

SHORTCUTS_HELP = """
<h3>Keyboard shortcuts</h3>
<table cellspacing=4>
<tr><td><b>Space</b></td><td>Play / pause</td></tr>
<tr><td><b>← / →</b></td><td>One frame back / forward</td></tr>
<tr><td><b>Shift + ← / →</b></td><td>One second back / forward</td></tr>
<tr><td><b>Ctrl + ← / →</b></td><td>Ten seconds back / forward</td></tr>
<tr><td><b>↑ / ↓</b></td><td>Previous / next cut point</td></tr>
<tr><td><b>Home / End</b></td><td>Start / end of the film</td></tr>
<tr><td><b>I / O</b></td><td>Mark start / end of the part to remove</td></tr>
<tr><td><b>Delete / X</b></td><td>Cut the marked part out (video + GPS)</td></tr>
<tr><td><b>Esc</b></td><td>Clear the marking</td></tr>
<tr><td><b>Ctrl + Z / Ctrl + Y</b></td><td>Undo / redo</td></tr>
<tr><td><b>Ctrl + E</b></td><td>Export</td></tr>
</table>
<p>In the timeline: click or drag to move the playhead, <b>Shift + drag</b> to mark a part,
drag the red edges to adjust it, mouse wheel to zoom.</p>
"""


class _Loader(QObject):
    progress = Signal(str, float)
    finished = Signal(object, str)

    def __init__(self, paths: List[str], project_file: Optional[str] = None) -> None:
        super().__init__()
        self.paths = paths
        self.project_file = project_file

    def run(self) -> None:
        try:
            if self.project_file:
                p = Project.load(self.project_file, lambda m, f: self.progress.emit(m, f))
            else:
                p = Project()
                p.load_videos(self.paths, lambda m, f: self.progress.emit(m, f))
            self.finished.emit(p, "")
        except Exception as e:  # pragma: no cover - shown to user
            traceback.print_exc()
            self.finished.emit(None, str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings()
        self.project: Optional[Project] = None
        self.dirty = False
        self._thread: Optional[QThread] = None
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        # ---------------- video area
        self.video = VideoView()
        self.video.setMinimumSize(480, 270)
        welcome = QWidget()
        wl = QVBoxLayout(welcome)
        wl.addStretch()
        t = QLabel("<h1>Artilody RLV Creator</h1><p>Create Real Life Videos from GoPro recordings.</p>"
                   "<p>Open one or more GoPro video files (chapters of one ride are joined automatically),<br>"
                   "or drop them onto this window.</p>")
        t.setAlignment(Qt.AlignCenter)
        wl.addWidget(t)
        b = QPushButton("  Open GoPro video(s)…")
        b.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        b.setIconSize(QSize(28, 28))
        b.setMinimumHeight(52)
        b.setStyleSheet("font-size: 16px; padding: 6px 24px;")
        b.clicked.connect(self.open_videos)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(b)
        bl.addStretch()
        wl.addLayout(bl)
        b2 = QPushButton("Open project…")
        b2.setFlat(True)
        b2.clicked.connect(self.open_project)
        bl2 = QHBoxLayout()
        bl2.addStretch()
        bl2.addWidget(b2)
        bl2.addStretch()
        wl.addLayout(bl2)
        wl.addStretch()
        self.stack = QStackedWidget()
        self.stack.addWidget(welcome)
        self.stack.addWidget(self.video)

        self.player = EditedPlayer(self.video.item, self)
        self.player.positionChanged.connect(self._on_position)
        self.player.playingChanged.connect(self._on_playing)
        self.player.errorOccurred.connect(lambda m: self.statusBar().showMessage("Playback: " + m, 8000))

        # ---------------- side tabs
        self.map = MapView()
        self.map.seekRequested.connect(lambda s: self.seek(s * FPS))
        self.route_panel = RoutePanel(self._current_distance)
        self.route_panel.changed.connect(self._mark_dirty_meta)
        self.route_panel.seekDistance.connect(self._seek_distance)
        self.gps_panel = GpsPanel()
        self.gps_panel.settingsChanged.connect(self._gps_settings_changed)
        self.gps_panel.importSensors.connect(self.import_sensors)
        self.gps_panel.clearSensors.connect(self.clear_sensors)
        self.cuts_panel = CutsPanel()
        self.cuts_panel.restoreRequested.connect(self._restore)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.map, "Map")
        self.tabs.addTab(self.route_panel, "Route info (XML)")
        self.tabs.addTab(self.gps_panel, "GPS")
        self.tabs.addTab(self.cuts_panel, "Cuts")

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.stack)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([860, 540])

        # ---------------- actions
        self._make_actions()

        # ---------------- transport bar
        bar = QHBoxLayout()
        bar.setSpacing(4)

        def tb(action: QAction) -> QToolButton:
            w = QToolButton()
            w.setDefaultAction(action)
            w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if action.text().startswith(("✂", "Mark", "Undo", "Redo"))
                                 else Qt.ToolButtonIconOnly)
            w.setAutoRaise(True)
            return w

        for a in (self.act_start, self.act_back_s, self.act_back_f, self.act_play, self.act_fwd_f,
                  self.act_fwd_s, self.act_end):
            bar.addWidget(tb(a))
        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setStyleSheet("font-family: monospace; font-size: 14px; padding: 0 10px;")
        bar.addWidget(self.time_label)
        bar.addWidget(self._vline())
        for a in (self.act_mark_in, self.act_mark_out):
            bar.addWidget(tb(a))
        self.cut_btn = QPushButton("✂  Cut out selection")
        self.cut_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 4px 12px; }"
                                   "QPushButton:enabled { background: #c0392b; color: white; border-radius: 4px; }")
        self.cut_btn.clicked.connect(self.cut_selection)
        bar.addWidget(self.cut_btn)
        bar.addWidget(tb(self.act_cut_before))
        bar.addWidget(tb(self.act_cut_after))
        bar.addWidget(self._vline())
        bar.addWidget(tb(self.act_undo))
        bar.addWidget(tb(self.act_redo))
        bar.addStretch()
        self.gps_label = QLabel()
        self.gps_label.setStyleSheet("font-family: monospace;")
        bar.addWidget(self.gps_label)
        self.mute_btn = QToolButton()
        self.mute_btn.setCheckable(True)
        self.mute_btn.setAutoRaise(True)
        self.mute_btn.setChecked(self.settings.value("muted", True, bool))
        self.mute_btn.toggled.connect(self._mute)
        self._mute(self.mute_btn.isChecked())
        bar.addWidget(self.mute_btn)

        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self.seek)
        self.timeline.selectionChanged.connect(self._selection_changed)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(6, 6, 6, 6)
        cl.addWidget(split, 1)
        cl.addLayout(bar)
        cl.addWidget(self.timeline)
        self.setCentralWidget(central)

        self._make_menus()
        self._make_toolbar()
        QApplication.instance().installEventFilter(self)
        self._update_actions()
        self._update_title()
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    # ------------------------------------------------------------ building
    @staticmethod
    def _vline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setFrameShadow(QFrame.Sunken)
        return f

    def _act(self, text: str, slot, shortcut=None, icon=None, tip: str = "") -> QAction:
        a = QAction(text, self)
        if icon is not None:
            a.setIcon(self.style().standardIcon(icon) if isinstance(icon, QStyle.StandardPixmap) else icon)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setToolTip((tip or text.replace("&", "")) + (f"  ({QKeySequence(shortcut).toString()})" if shortcut else ""))
        a.triggered.connect(slot)
        return a

    def _make_actions(self) -> None:
        S = QStyle
        self.act_open = self._act("&Open video(s)…", self.open_videos, QKeySequence.Open, S.SP_DialogOpenButton)
        self.act_open_proj = self._act("Open &project…", self.open_project, "Ctrl+Shift+O")
        self.act_save = self._act("&Save project", self.save_project, QKeySequence.Save, S.SP_DialogSaveButton)
        self.act_save_as = self._act("Save project &as…", self.save_project_as, QKeySequence.SaveAs)
        self.act_export = self._act("&Export MP4 + GPX + XML…", self.export, "Ctrl+E", S.SP_DriveHDIcon,
                                    "Export the finished RLV")
        self.act_import_xml = self._act("Import route info from XML…", self.import_xml)
        self.act_import_sensors = self._act("Import heart rate / cadence (GPX/TCX)…", self.import_sensors)
        self.act_ffmpeg = self._act("Set FFmpeg location…", self.set_ffmpeg)
        self.act_quit = self._act("&Quit", self.close, QKeySequence.Quit)
        self.act_undo = self._act("Undo", self.undo, QKeySequence.Undo, S.SP_ArrowBack)
        self.act_redo = self._act("Redo", self.redo, "Ctrl+Y", S.SP_ArrowForward)
        self.act_redo2 = self._act("Redo", self.redo, "Ctrl+Shift+Z")
        self.addAction(self.act_redo2)
        self.act_play = self._act("Play", lambda: self.player.toggle(), None, S.SP_MediaPlay, "Play / pause (Space)")
        self.act_start = self._act("Start", lambda: self.seek(0), None, S.SP_MediaSkipBackward, "Go to start (Home)")
        self.act_end = self._act("End", lambda: self.seek(10 ** 9), None, S.SP_MediaSkipForward, "Go to end (End)")
        self.act_back_f = self._act("-1 frame", lambda: self.player.step(-1), None, S.SP_MediaSeekBackward,
                                    "One frame back (←)")
        self.act_fwd_f = self._act("+1 frame", lambda: self.player.step(1), None, S.SP_MediaSeekForward,
                                   "One frame forward (→)")
        self.act_back_s = self._act("-1 s", lambda: self.player.step(-FPS), None, S.SP_ArrowLeft,
                                    "One second back (Shift+←)")
        self.act_fwd_s = self._act("+1 s", lambda: self.player.step(FPS), None, S.SP_ArrowRight,
                                   "One second forward (Shift+→)")
        self.act_mark_in = self._act("Mark start [I]", self.mark_in, None, None, "Mark the start of the part to remove (I)")
        self.act_mark_out = self._act("Mark end [O]", self.mark_out, None, None, "Mark the end of the part to remove (O)")
        self.act_cut = self._act("✂ Cut out selection", self.cut_selection, None, None,
                                 "Remove the marked part from video and GPS (Delete)")
        self.act_cut_before = self._act("✂ Start→here", self.cut_before, None, None,
                                        "Remove everything before the playhead")
        self.act_cut_after = self._act("✂ Here→end", self.cut_after, None, None,
                                       "Remove everything after the playhead")
        self.act_clear_sel = self._act("Clear selection", self.clear_selection)
        self.act_zoom_fit = self._act("Zoom timeline to fit", lambda: self.timeline.zoom_fit())
        self.act_help = self._act("Keyboard shortcuts", self.show_help, QKeySequence.HelpContents)
        self.act_about = self._act("About", self.about)
        self.act_site = self._act("Project website", lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/shenphenchoedron-hue/Artilody-RLV-Creator")))

    def _make_menus(self) -> None:
        m = self.menuBar().addMenu("&File")
        for a in (self.act_open, self.act_open_proj, None, self.act_save, self.act_save_as, None,
                  self.act_import_xml, self.act_import_sensors, None, self.act_export, None,
                  self.act_ffmpeg, None, self.act_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = self.menuBar().addMenu("&Edit")
        for a in (self.act_undo, self.act_redo, None, self.act_mark_in, self.act_mark_out, self.act_clear_sel,
                  None, self.act_cut, self.act_cut_before, self.act_cut_after):
            m.addSeparator() if a is None else m.addAction(a)
        m = self.menuBar().addMenu("&View")
        m.addAction(self.act_zoom_fit)
        m = self.menuBar().addMenu("&Help")
        for a in (self.act_help, self.act_site, self.act_about):
            m.addAction(a)

    def _make_toolbar(self) -> None:
        t = self.addToolBar("Main")
        t.setObjectName("main_toolbar")
        t.setMovable(False)
        t.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        t.setIconSize(QSize(20, 20))
        for a in (self.act_open, self.act_save, None, self.act_undo, self.act_redo, None, self.act_export):
            t.addSeparator() if a is None else t.addAction(a)

    # ------------------------------------------------------------- loading
    def open_videos(self) -> None:
        if not self._confirm_discard():
            return
        start = self.settings.value("last_dir", os.path.expanduser("~"), str)
        paths, _ = QFileDialog.getOpenFileNames(self, "Open GoPro video(s) - select all chapters of the ride",
                                                start, VIDEO_FILTER)
        if paths:
            self.load(paths)

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        start = self.settings.value("last_dir", os.path.expanduser("~"), str)
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start, PROJECT_FILTER)
        if path:
            self.load([], path)

    def load(self, paths: List[str], project_file: Optional[str] = None) -> None:
        if self._thread is not None:
            return
        first = project_file or paths[0]
        self.settings.setValue("last_dir", os.path.dirname(first))
        self.player.set_project(None)
        dlg = QProgressDialog("Reading video…", "", 0, 1000, self)
        dlg.setWindowTitle("Loading")
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setValue(0)
        self._thread = QThread(self)
        self._loader = _Loader(paths, project_file)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)

        self._load_dlg = dlg
        self._loader.progress.connect(self._load_progress)
        self._loader.finished.connect(self._load_done)
        self._thread.start()

    @Slot(str, float)
    def _load_progress(self, msg: str, f: float) -> None:
        self._load_dlg.setLabelText(msg)
        self._load_dlg.setValue(int(f * 1000))

    @Slot(object, str)
    def _load_done(self, project: Optional[Project], err: str) -> None:
        self._load_dlg.close()
        assert self._thread
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        if project is None:
            QMessageBox.critical(self, "Could not open", err)
            return
        self.set_project(project)
        if project.raw_gps and not project.has_gps:
            QMessageBox.warning(self, "GPS", "The video contains GPS data, but no usable GPS fix was found.")
        elif not project.raw_gps:
            QMessageBox.warning(self, "GPS", "No GoPro GPS data (GPMF) was found in the video.\n\n"
                                "You can still edit and export the video, but no GPX file can be made. "
                                "Make sure GPS was switched on in the camera.")

    def set_project(self, project: Optional[Project]) -> None:
        self.project = project
        self.dirty = False
        self.stack.setCurrentIndex(1 if project else 0)
        self.timeline.set_selection(None, None)
        self.route_panel.set_project(project)
        self.gps_panel.set_project(project)
        self.cuts_panel.set_project(project)
        self._edit_changed(refit=True, record_dirty=False)
        self.player.set_project(project)
        self._update_title()

    # -------------------------------------------------------- edit actions
    def _edit_changed(self, refit: bool = False, record_dirty: bool = True) -> None:
        p = self.project
        if p is None:
            self.timeline.set_data(0, [], [])
            self.map.set_tracks([], [], refit=True)
            self._update_actions()
            return
        p.invalidate()
        pts = p.output_points()
        self.timeline.set_data(p.output_frames, p.edit.join_points(), [x.ele for x in pts], keep_view=not refit)
        src = []
        if p.has_gps:
            step = max(1, int(p.track.rate))
            src = list(zip(p.track.lat[::step], p.track.lon[::step]))
        self.map.set_tracks(src, [(x.lat, x.lon) for x in pts], refit=refit)
        self.cuts_panel.refresh()
        self.route_panel.update_stats()
        if record_dirty:
            self.dirty = True
        self._update_actions()
        self._update_title()
        self._on_position(min(self.player.out_frame, max(0, p.output_frames - 1)))

    def seek(self, out_frame: int) -> None:
        if self.project:
            self.player.seek(out_frame)

    def mark_in(self) -> None:
        if not self.project:
            return
        f = self.player.out_frame
        out = self.timeline.sel_out
        if out is not None and out <= f:
            out = None
        self.timeline.set_selection(f, out)

    def mark_out(self) -> None:
        if not self.project:
            return
        f = self.player.out_frame + 1  # include the current frame
        a = self.timeline.sel_in
        if a is None or a >= f:
            a = 0 if a is None else a
        self.timeline.set_selection(a, f)

    def clear_selection(self) -> None:
        self.timeline.set_selection(None, None)

    def _do_cut(self, a: int, b: int, label: str) -> None:
        p = self.project
        if not p:
            return
        if a <= 0 and b >= p.output_frames:
            QMessageBox.information(self, "Cut", "You cannot remove the whole film.")
            return
        self.player.pause()
        if p.edit.cut(a, b, label):
            self.timeline.set_selection(None, None)
            self._edit_changed()
            self.player.seek(min(a, p.output_frames - 1))
            self.statusBar().showMessage(f"{label}  -  removed from video and GPS.  Ctrl+Z to undo.", 6000)

    def cut_selection(self) -> None:
        sel = self.timeline.selection()
        if sel:
            self._do_cut(sel[0], sel[1], f"Cut {fmt_frames(sel[1] - sel[0])} at {fmt_frames(sel[0])}")

    def cut_before(self) -> None:
        if self.project and self.player.out_frame > 0:
            self._do_cut(0, self.player.out_frame, "Cut start")

    def cut_after(self) -> None:
        if self.project:
            f = self.player.out_frame + 1
            if f < self.project.output_frames:
                self._do_cut(f, self.project.output_frames, "Cut end")

    def _restore(self, a: int, b: int) -> None:
        if self.project and self.project.edit.restore_source_range(a, b):
            self.player.pause()
            self._edit_changed()
            out = self.project.edit.src_to_out(a)
            if out is not None:
                self.player.seek(out)

    def undo(self) -> None:
        if self.project and self.project.edit.can_undo:
            label = self.project.edit.undo_label
            self.player.pause()
            self.project.edit.undo()
            self._edit_changed()
            self.player.seek(self.player.out_frame)
            self.statusBar().showMessage(f"Undone: {label}", 4000)

    def redo(self) -> None:
        if self.project and self.project.edit.can_redo:
            label = self.project.edit.redo_label
            self.player.pause()
            self.project.edit.redo()
            self._edit_changed()
            self.player.seek(self.player.out_frame)
            self.statusBar().showMessage(f"Redone: {label}", 4000)

    def jump_join(self, direction: int) -> None:
        if not self.project:
            return
        joins = [0] + self.project.edit.join_points() + [self.project.output_frames - 1]
        f = self.player.out_frame
        cands = [j for j in joins if (j > f if direction > 0 else j < f)]
        if cands:
            self.seek(min(cands) if direction > 0 else max(cands))

    # ----------------------------------------------------------- feedback
    def _on_position(self, f: int) -> None:
        self.timeline.set_playhead(f)
        p = self.project
        if not p:
            self.time_label.setText("00:00.00 / 00:00.00")
            self.gps_label.setText("")
            return
        self.time_label.setText(f"{fmt_frames(f)} / {fmt_frames(p.output_frames)}")
        if p.has_gps:
            src_t = p.edit.out_to_src(f) / FPS
            lat, lon, ele, spd = p.track.at(src_t)
            self.map.set_position(lat, lon)
            d = p.distance_at_output_time(f / FPS)
            self.gps_label.setText(f"{fmt_distance(d):>9}   {spd * 3.6:5.1f} km/h   {ele:6.1f} m  ")
        else:
            self.gps_label.setText("no GPS  ")

    def _on_playing(self, playing: bool) -> None:
        self.act_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay))

    def _selection_changed(self) -> None:
        sel = self.timeline.selection()
        if self.project and sel:
            self.map.set_selection((sel[0] // FPS, sel[1] // FPS))
        else:
            self.map.set_selection(None)
        self._update_actions()

    def _update_actions(self) -> None:
        p = self.project
        has = p is not None and p.loaded
        for a in (self.act_save, self.act_save_as, self.act_export, self.act_import_xml, self.act_import_sensors,
                  self.act_play, self.act_start, self.act_end, self.act_back_f, self.act_fwd_f, self.act_back_s,
                  self.act_fwd_s, self.act_mark_in, self.act_mark_out, self.act_cut_before, self.act_cut_after,
                  self.act_clear_sel):
            a.setEnabled(has)
        sel = self.timeline.selection() is not None
        self.act_cut.setEnabled(has and sel)
        self.cut_btn.setEnabled(has and sel)
        self.act_undo.setEnabled(bool(has and p.edit.can_undo))
        self.act_redo.setEnabled(bool(has and p.edit.can_redo))
        self.act_redo2.setEnabled(bool(has and p.edit.can_redo))
        self.act_undo.setToolTip("Undo " + (p.edit.undo_label if has and p.edit.can_undo else "") + "  (Ctrl+Z)")
        self.act_redo.setToolTip("Redo " + (p.edit.redo_label if has and p.edit.can_redo else "") + "  (Ctrl+Y)")

    def _update_title(self) -> None:
        name = self.project.name if self.project else ""
        star = " *" if self.dirty else ""
        self.setWindowTitle(f"{name}{star} - Artilody RLV Creator" if name else "Artilody RLV Creator")

    def _mark_dirty_meta(self) -> None:
        self.dirty = True
        self._update_title()

    def _mute(self, muted: bool) -> None:
        self.player.set_muted(muted)
        self.mute_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaVolumeMuted if muted else QStyle.SP_MediaVolume))
        self.mute_btn.setToolTip("Unmute preview" if muted else "Mute preview")
        self.settings.setValue("muted", muted)

    def _current_distance(self) -> float:
        if not self.project:
            return 0.0
        return self.project.distance_at_output_time(self.player.out_frame / FPS)

    def _seek_distance(self, d: float) -> None:
        if self.project:
            self.seek(int(round(self.project.output_time_at_distance(d) * FPS)))

    def _gps_settings_changed(self) -> None:
        self.dirty = True
        self._edit_changed(record_dirty=True)

    # ------------------------------------------------------- file actions
    def save_project(self) -> bool:
        if not self.project:
            return False
        if not self.project.project_path:
            return self.save_project_as()
        try:
            self.project.save(self.project.project_path)
        except OSError as e:
            QMessageBox.critical(self, "Save", str(e))
            return False
        self.dirty = False
        self._update_title()
        self.statusBar().showMessage("Project saved", 3000)
        return True

    def save_project_as(self) -> bool:
        if not self.project:
            return False
        start = os.path.join(os.path.dirname(self.project.chapters[0].path), (self.project.name or "route") + ".rlvproj")
        path, _ = QFileDialog.getSaveFileName(self, "Save project", start, PROJECT_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".rlvproj"):
            path += ".rlvproj"
        self.project.project_path = path
        return self.save_project()

    def export(self) -> None:
        if not self.project:
            return
        self.player.pause()
        dlg = ExportDialog(self.project, self)
        dlg.exec()
        self.route_panel.refresh()
        self._update_title()

    def import_xml(self) -> None:
        if not self.project:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import route info from XML",
                                              self.settings.value("last_dir", "", str), "RLV XML (*.xml)")
        if not path:
            return
        try:
            meta = exporters.read_xml_metadata(path)
        except Exception as e:
            QMessageBox.critical(self, "Import", str(e))
            return
        p = self.project
        p.title = meta["title"] or p.title
        p.country = meta["country"] or p.country
        p.infos = meta["infos"]
        self.route_panel.refresh()
        self.tabs.setCurrentWidget(self.route_panel)
        self._mark_dirty_meta()

    def import_sensors(self) -> None:
        if not self.project:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import heart rate / cadence",
                                              self.settings.value("last_dir", "", str),
                                              "GPX / TCX (*.gpx *.tcx *.GPX *.TCX)")
        if not path:
            return
        try:
            self.project.sensors = load_sensor_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Import", f"Could not read the file:\n{e}")
            return
        self.project.invalidate()
        self.gps_panel.refresh()
        self.tabs.setCurrentWidget(self.gps_panel)
        pts = self.project.output_points()
        if pts and not any(x.hr is not None or x.cad is not None for x in pts):
            QMessageBox.warning(self, "Import", "The sensor file does not overlap in time with the video "
                                "(or the video has no GPS time). Check the offset.")
        self._mark_dirty_meta()

    def clear_sensors(self) -> None:
        if self.project:
            self.project.sensors = None
            self.project.invalidate()
            self.gps_panel.refresh()
            self._mark_dirty_meta()

    def set_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Locate the FFmpeg executable")
        self.settings.setValue("ffmpeg_path", path or "")

    def show_help(self) -> None:
        QMessageBox.information(self, "Keyboard shortcuts", SHORTCUTS_HELP)

    def about(self) -> None:
        QMessageBox.about(self, "About Artilody RLV Creator",
                          f"<h3>Artilody RLV Creator {__version__}</h3>"
                          "<p>Create Real Life Videos (MP4 + GPX + XML) from GoPro recordings.</p>"
                          "<p>License: GNU GPL v3<br>"
                          "<a href='https://github.com/shenphenchoedron-hue/Artilody-RLV-Creator'>"
                          "github.com/shenphenchoedron-hue/Artilody-RLV-Creator</a></p>"
                          "<p>Uses Qt / PySide6 and FFmpeg.</p>")

    # -------------------------------------------------------------- events
    def _confirm_discard(self) -> bool:
        if not self.project or not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save the current project first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_project()
        return r == QMessageBox.Discard

    def closeEvent(self, ev) -> None:
        if not self._confirm_discard():
            ev.ignore()
            return
        self.player.pause()
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(ev)

    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        proj = [p for p in paths if p.lower().endswith(".rlvproj")]
        vids = [p for p in paths if p.lower().endswith((".mp4", ".mov", ".lrv"))]
        if (proj or vids) and self._confirm_discard():
            if proj:
                self.load([], proj[0])
            else:
                self.load(vids)

    def eventFilter(self, obj, ev) -> bool:
        if ev.type() == QEvent.KeyPress and self.isActiveWindow() and self.project:
            fw = QApplication.focusWidget()
            if isinstance(fw, (QLineEdit, QTextEdit, QAbstractSpinBox, QComboBox, QAbstractItemView)):
                return False
            if QApplication.activeModalWidget() is not None:
                return False
            k = ev.key()
            mods = ev.modifiers()
            ctrl = bool(mods & Qt.ControlModifier)
            shift = bool(mods & Qt.ShiftModifier)
            step = 10 * FPS if ctrl else (FPS if shift else 1)
            handled = True
            if k == Qt.Key_Space:
                self.player.toggle()
            elif k == Qt.Key_Left:
                self.player.step(-step)
            elif k == Qt.Key_Right:
                self.player.step(step)
            elif k == Qt.Key_Up:
                self.jump_join(-1)
            elif k == Qt.Key_Down:
                self.jump_join(1)
            elif k == Qt.Key_Home:
                self.seek(0)
            elif k == Qt.Key_End:
                self.seek(10 ** 9)
            elif k == Qt.Key_I and not ctrl:
                self.mark_in()
            elif k == Qt.Key_O and not ctrl:
                self.mark_out()
            elif k in (Qt.Key_Delete, Qt.Key_Backspace) or (k == Qt.Key_X and not ctrl):
                self.cut_selection()
            elif k == Qt.Key_Escape:
                self.clear_selection()
            else:
                handled = False
            if handled:
                return True
        return False
