"""Side panels: route information (XML), GPS settings and list of cuts."""

from __future__ import annotations

import uuid
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..project import FPS, Info, Project
from .common import fmt_distance, fmt_frames, fmt_seconds

COUNTRIES = ["AT", "BE", "CH", "CZ", "DE", "DK", "ES", "FI", "FR", "GB", "GR", "HR", "IE", "IS", "IT",
             "LU", "NL", "NO", "PL", "PT", "SE", "SI", "SK", "US", "CA", "AU", "NZ", "ZA", "JP"]

DIFFICULTY = {"Easy": "Leicht", "Medium": "Mittel", "Hard": "Schwer", "Very hard": "Sehr schwer"}


class RoutePanel(QWidget):
    """Metadata written to the XML file + information texts shown during the ride."""

    changed = Signal()
    seekDistance = Signal(float)

    def __init__(self, position_distance: Callable[[], float], parent=None) -> None:
        super().__init__(parent)
        self.project: Optional[Project] = None
        self._position_distance = position_distance
        self._loading = False

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setToolTip("File name used for the .mp4, .gpx and .xml files")
        self.title = QLineEdit()
        self.country = QComboBox()
        self.country.setEditable(True)
        self.country.addItems(COUNTRIES)
        self.country.setCurrentText("")
        id_row = QHBoxLayout()
        self.route_id = QLineEdit()
        self.route_id.setReadOnly(True)
        regen = QPushButton("New")
        regen.setToolTip("Generate a new unique ID")
        regen.clicked.connect(self._new_id)
        id_row.addWidget(self.route_id)
        id_row.addWidget(regen)
        form.addRow("Name:", self.name)
        form.addRow("Title:", self.title)
        form.addRow("Country:", self.country)
        form.addRow("ID:", id_row)
        lay.addLayout(form)

        self.stats = QLabel()
        self.stats.setStyleSheet("color: palette(mid); padding: 2px;")
        self.stats.setWordWrap(True)
        lay.addWidget(self.stats)

        box = QGroupBox("Information texts (shown at a distance along the route)")
        bl = QVBoxLayout(box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Distance (m)", "German (de)", "English (en)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setToolTip("Double-click a cell to edit.  Write \\n for a line break.")
        bl.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("+ At current position")
        add.setToolTip("Add an information text at the distance of the playhead")
        add.clicked.connect(self._add_here)
        summ = QPushButton("+ Route summary")
        summ.setToolTip("Add a text with title, length, ascent and difficulty at 20 m")
        summ.clicked.connect(self._add_summary)
        self.difficulty = QComboBox()
        self.difficulty.addItems(list(DIFFICULTY))
        go = QPushButton("Go to")
        go.setToolTip("Move the playhead to the selected information")
        go.clicked.connect(self._goto)
        rm = QPushButton("Remove")
        rm.clicked.connect(self._remove)
        for w in (add, summ, self.difficulty, go, rm):
            row.addWidget(w)
        row.addStretch()
        bl.addLayout(row)
        lay.addWidget(box, 1)

        for w in (self.name, self.title):
            w.textEdited.connect(self._meta_edited)
        self.country.currentTextChanged.connect(self._meta_edited)
        self.table.itemChanged.connect(self._table_edited)

    # ---------------------------------------------------------------- sync
    def set_project(self, project: Optional[Project]) -> None:
        self.project = project
        self.refresh()

    def refresh(self) -> None:
        p = self.project
        self._loading = True
        try:
            self.setEnabled(p is not None)
            if p is None:
                return
            self.name.setText(p.name)
            self.title.setText(p.title)
            self.country.setCurrentText(p.country)
            self.route_id.setText(p.route_id)
            self._fill_table()
            self.update_stats()
        finally:
            self._loading = False

    def update_stats(self) -> None:
        p = self.project
        if not p or not p.loaded:
            self.stats.setText("")
            return
        length, up = p.stats()
        txt = (f"Film: {fmt_frames(p.output_frames)}  ({p.output_frames} frames @ {FPS} fps)   ·   "
               f"Length: {fmt_distance(length)}   ·   Ascent: {up:.0f} m")
        if not p.has_gps:
            txt += "   ·   ⚠ no GPS data in the video"
        self.stats.setText(txt)

    def _fill_table(self) -> None:
        assert self.project
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for info in sorted(self.project.infos, key=lambda i: i.distance):
            r = self.table.rowCount()
            self.table.insertRow(r)
            d = QTableWidgetItem()
            d.setData(Qt.EditRole, int(info.distance))
            self.table.setItem(r, 0, d)
            self.table.setItem(r, 1, QTableWidgetItem(info.de))
            self.table.setItem(r, 2, QTableWidgetItem(info.en))
        self.table.blockSignals(False)

    def _collect(self) -> List[Info]:
        out = []
        for r in range(self.table.rowCount()):
            items = [self.table.item(r, c) for c in range(3)]
            try:
                d = int(float(items[0].text())) if items[0] else 0
            except ValueError:
                d = 0
            out.append(Info(d, items[1].text() if items[1] else "", items[2].text() if items[2] else ""))
        return out

    def _meta_edited(self, *_a) -> None:
        if self._loading or not self.project:
            return
        self.project.name = self.name.text().strip()
        self.project.title = self.title.text().strip()
        self.project.country = self.country.currentText().strip().upper()
        self.changed.emit()

    def _table_edited(self, *_a) -> None:
        if self._loading or not self.project:
            return
        self.project.infos = self._collect()
        self.changed.emit()

    def _new_id(self) -> None:
        if self.project:
            self.project.route_id = uuid.uuid4().hex
            self.route_id.setText(self.project.route_id)
            self.changed.emit()

    def _add_info(self, info: Info) -> None:
        assert self.project
        self.project.infos.append(info)
        self._fill_table()
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.EditRole) == info.distance and self.table.item(r, 2).text() == info.en:
                self.table.selectRow(r)
                self.table.editItem(self.table.item(r, 2))
                break
        self.changed.emit()

    def _add_here(self) -> None:
        if self.project:
            self._add_info(Info(int(round(self._position_distance())), "", ""))

    def _add_summary(self) -> None:
        p = self.project
        if not p:
            return
        length, up = p.stats()
        diff = self.difficulty.currentText()
        km_en = f"{length / 1000:.1f}"
        km_de = km_en.replace(".", ",")
        title = p.title or p.name
        de = f"{title} - Länge: {km_de} km - Anstieg: {up:.0f} hm\\nSchwierigkeitsgrad: {DIFFICULTY[diff]}"
        en = f"{title}\\nLength: {km_en} km - Ascent: {up:.0f} hm\\nDifficulty: {diff}"
        self._add_info(Info(20, de, en))

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows and self.project:
            self.project.infos = self._collect()
            self.changed.emit()

    def _goto(self) -> None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        if rows:
            item = self.table.item(min(rows), 0)
            if item:
                self.seekDistance.emit(float(item.data(Qt.EditRole) or 0))


class GpsPanel(QWidget):
    """GPS processing settings and optional heart-rate/cadence import."""

    settingsChanged = Signal()
    importSensors = Signal()
    clearSensors = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project: Optional[Project] = None
        lay = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        box = QGroupBox("GPS processing")
        f = QFormLayout(box)
        self.max_dop = QDoubleSpinBox()
        self.max_dop.setRange(0, 100)
        self.max_dop.setDecimals(1)
        self.max_dop.setToolTip("Ignore GPS points with a worse precision (DOP). 0 = keep all points with a fix.")
        self.ele_window = QDoubleSpinBox()
        self.ele_window.setRange(0.1, 60)
        self.ele_window.setSuffix(" s")
        self.ele_window.setToolTip("Elevation is averaged over this time window to give smooth gradients")
        self.ele_offset = QDoubleSpinBox()
        self.ele_offset.setRange(-500, 500)
        self.ele_offset.setSuffix(" m")
        self.ele_offset.setToolTip("Constant correction added to all elevations")
        self.real_time = QCheckBox("Write real recording time (UTC) in GPX")
        self.real_time.setToolTip("Default: times start at 1999-12-31T23:00:00Z like the reference RLV files")
        f.addRow("Max. DOP:", self.max_dop)
        f.addRow("Elevation smoothing:", self.ele_window)
        f.addRow("Elevation offset:", self.ele_offset)
        f.addRow(self.real_time)
        apply = QPushButton("Apply")
        apply.clicked.connect(self._apply)
        f.addRow(apply)
        lay.addWidget(box)

        sbox = QGroupBox("Heart rate / cadence (optional)")
        sl = QVBoxLayout(sbox)
        self.sensor_label = QLabel("GoPro cameras do not record heart rate or cadence. Import a GPX/TCX file "
                                   "from a bike computer or watch recorded on the same ride; it is matched "
                                   "to the video by GPS time.")
        self.sensor_label.setWordWrap(True)
        sl.addWidget(self.sensor_label)
        r = QHBoxLayout()
        imp = QPushButton("Import GPX/TCX…")
        imp.clicked.connect(self.importSensors.emit)
        clr = QPushButton("Remove")
        clr.clicked.connect(self.clearSensors.emit)
        self.sensor_offset = QDoubleSpinBox()
        self.sensor_offset.setRange(-36000, 36000)
        self.sensor_offset.setDecimals(1)
        self.sensor_offset.setSuffix(" s")
        self.sensor_offset.setToolTip("Clock correction of the sensor file")
        self.sensor_offset.editingFinished.connect(self._apply)
        r.addWidget(imp)
        r.addWidget(clr)
        r.addWidget(QLabel("Offset:"))
        r.addWidget(self.sensor_offset)
        r.addStretch()
        sl.addLayout(r)
        lay.addWidget(sbox)
        lay.addStretch()

    def set_project(self, project: Optional[Project]) -> None:
        self.project = project
        self.refresh()

    def refresh(self) -> None:
        p = self.project
        self.setEnabled(p is not None and p.loaded)
        if not p:
            self.info.setText("")
            return
        n_raw = len(p.raw_gps)
        chapters = len(p.chapters)
        self.info.setText(f"{chapters} video file(s), {n_raw} GPS samples"
                          + ("" if p.has_gps else "  -  ⚠ no usable GPS data found"))
        self.max_dop.setValue(p.max_dop)
        self.ele_window.setValue(p.ele_window)
        self.ele_offset.setValue(p.ele_offset)
        self.real_time.setChecked(p.use_real_time)
        self.sensor_offset.setValue(p.sensor_offset)
        if p.sensors:
            import os
            pts = p.output_points()
            n_hr = sum(1 for x in pts if x.hr is not None)
            n_cad = sum(1 for x in pts if x.cad is not None)
            self.sensor_label.setText(f"Sensor file: {os.path.basename(p.sensors.path)}  -  matched heart rate "
                                      f"for {n_hr} and cadence for {n_cad} of {len(pts)} points.")
        else:
            self.sensor_label.setText("GoPro cameras do not record heart rate or cadence. Import a GPX/TCX file "
                                      "from a bike computer or watch recorded on the same ride; it is matched "
                                      "to the video by GPS time.")

    def _apply(self) -> None:
        p = self.project
        if not p:
            return
        p.max_dop = self.max_dop.value()
        p.ele_window = self.ele_window.value()
        p.ele_offset = self.ele_offset.value()
        p.use_real_time = self.real_time.isChecked()
        p.sensor_offset = self.sensor_offset.value()
        p.rebuild_track()
        self.settingsChanged.emit()
        self.refresh()


class CutsPanel(QWidget):
    """Lists the parts that were cut away; they can be restored individually."""

    restoreRequested = Signal(int, int)  # source frame range

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project: Optional[Project] = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Parts removed from the film (times refer to the original recording):"))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        b = QPushButton("Restore selected")
        b.clicked.connect(self._restore)
        row.addWidget(b)
        row.addStretch()
        self.summary = QLabel()
        row.addWidget(self.summary)
        lay.addLayout(row)

    def set_project(self, project: Optional[Project]) -> None:
        self.project = project
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        p = self.project
        if not p:
            self.summary.setText("")
            return
        removed = p.edit.removed_source_ranges()
        total = 0
        for a, b in removed:
            total += b - a
            it = QListWidgetItem(f"✂  {fmt_frames(a)}  –  {fmt_frames(b)}     ({fmt_seconds((b - a) / FPS)} removed)")
            it.setData(Qt.UserRole, (a, b))
            self.list.addItem(it)
        self.summary.setText(f"{len(removed)} cut(s), {fmt_seconds(total / FPS)} removed")

    def _restore(self) -> None:
        for it in self.list.selectedItems():
            a, b = it.data(Qt.UserRole)
            self.restoreRequested.emit(int(a), int(b))
