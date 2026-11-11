"""Playback of the edited film: plays the kept segments only, across chapter files."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from ..project import FPS, Project


class EditedPlayer(QObject):
    positionChanged = Signal(int)  # output frame
    playingChanged = Signal(bool)
    errorOccurred = Signal(str)

    def __init__(self, video_output, parent=None) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.6)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(video_output)
        self.project: Optional[Project] = None
        self.chapter = -1
        self.out_frame = 0
        self.playing = False
        self._pending_ms: Optional[int] = None
        self._jump_until = 0.0
        self._jump_target_ms = 0
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._tick)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(lambda _e, msg: self.errorOccurred.emit(msg))

    # -------------------------------------------------------------- control
    def set_project(self, project: Optional[Project]) -> None:
        self.pause()
        self.project = project
        self.chapter = -1
        self.player.setSource(QUrl())
        if project and project.loaded:
            self.seek(0)

    def set_muted(self, muted: bool) -> None:
        self.audio.setMuted(muted)

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def play(self) -> None:
        if not self.project or not self.project.loaded:
            return
        if self.out_frame >= self.project.output_frames - 1:
            self.seek(0)
        self.playing = True
        self.player.play()
        self.timer.start()
        self.playingChanged.emit(True)

    def pause(self) -> None:
        was = self.playing
        self.playing = False
        self.timer.stop()
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        if was:
            # snap to the exact frame we stopped at
            self.seek(self.out_frame)
            self.playingChanged.emit(False)

    def seek(self, out_frame: int) -> None:
        p = self.project
        if not p or not p.loaded or p.output_frames <= 0:
            return
        out_frame = max(0, min(int(out_frame), p.output_frames - 1))
        self.out_frame = out_frame
        src = p.edit.out_to_src(out_frame)
        self._go_src(src)
        self.positionChanged.emit(out_frame)

    def step(self, frames: int) -> None:
        if self.playing:
            self.pause()
        self.seek(self.out_frame + frames)

    # ------------------------------------------------------------- internals
    def _go_src(self, src_frame: int) -> None:
        assert self.project
        ci, local = self.project.chapter_for_frame(src_frame)
        # aim for the middle of the frame so decoders land on the right one
        ms = int(round((local + 0.5 / FPS) * 1000))
        self._jump_target_ms = ms
        self._jump_until = time.monotonic() + 0.4
        if ci != self.chapter:
            self.chapter = ci
            self._pending_ms = ms
            self.player.setSource(QUrl.fromLocalFile(self.project.chapters[ci].path))
            if self.playing:
                self.player.play()
            else:
                self.player.pause()
        else:
            self.player.setPosition(ms)

    def _on_status(self, status) -> None:
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia) and self._pending_ms is not None:
            ms = self._pending_ms
            self._pending_ms = None
            self.player.setPosition(ms)
            if self.playing:
                self.player.play()
            else:
                self.player.pause()
        elif status == QMediaPlayer.EndOfMedia and self.playing and self.project:
            ch = self.project.chapters[self.chapter]
            nxt = self.project.edit.next_kept_src(ch.end_frame)
            if nxt is None:
                self._finish()
            else:
                self._go_src(nxt)

    def _finish(self) -> None:
        assert self.project
        self.pause()
        self.seek(self.project.output_frames - 1)

    def _tick(self) -> None:
        p = self.project
        if not self.playing or not p or self.chapter < 0 or self._pending_ms is not None:
            return
        pos = self.player.position()
        if time.monotonic() < self._jump_until and abs(pos - self._jump_target_ms) > 150:
            return  # the player has not reached the jump target yet
        ch = p.chapters[self.chapter]
        src = ch.first_frame + min(ch.frames - 1, int(pos * FPS / 1000.0))
        out = p.edit.src_to_out(src)
        if out is None:
            nxt = p.edit.next_kept_src(src)
            if nxt is None:
                self._finish()
                return
            self._go_src(nxt)
            out = p.edit.src_to_out(nxt)
            if out is None:
                return
        if out != self.out_frame:
            self.out_frame = out
            self.positionChanged.emit(out)
