"""Project model: source chapters, GPS data, edit, route metadata."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from . import mp4
from .edit import EditModel
from .gpmf import GpsSample, extract_gps_from_movie
from .sensors import SensorData
from .track import SourceTrack, ascent, build_source_track, clean_samples, haversine

FPS = 30  # output frame rate
GPX_BASE_TIME = 946681200  # 1999-12-31T23:00:00Z, as used by the reference RLV files


@dataclass
class Chapter:
    path: str
    duration: float
    frames: int
    first_frame: int  # global source frame where this chapter starts
    has_audio: bool
    width: int
    height: int
    fps: float
    gps_count: int = 0

    @property
    def end_frame(self) -> int:
        return self.first_frame + self.frames


@dataclass
class Info:
    distance: int
    de: str = ""
    en: str = ""


@dataclass
class OutputPoint:
    t: int  # output second
    lat: float
    lon: float
    ele: float
    speed_kmh: float
    distance: float  # cumulative metres
    hr: Optional[int] = None
    cad: Optional[int] = None


def gopro_sort_key(path: str) -> Tuple:
    """Sort GoPro chapter files: GH010123, GH020123 ... / GOPR0123, GP010123 ..."""
    name = os.path.basename(path)
    m = re.match(r"^(G[HXL])(\d{2})(\d{4})", name, re.IGNORECASE)
    if m:
        return (0, int(m.group(3)), int(m.group(2)), name)
    m = re.match(r"^GOPR(\d{4})", name, re.IGNORECASE)
    if m:
        return (0, int(m.group(1)), 0, name)
    m = re.match(r"^GP(\d{2})(\d{4})", name, re.IGNORECASE)
    if m:
        return (0, int(m.group(2)), int(m.group(1)), name)
    return (1, 0, 0, name.lower())


def sanitize_name(name: str) -> str:
    name = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE)
    return name.strip("_") or "route"


class Project:
    def __init__(self) -> None:
        self.chapters: List[Chapter] = []
        self.raw_gps: List[GpsSample] = []
        self.track = SourceTrack()
        self.edit = EditModel()
        self.sensors: Optional[SensorData] = None
        self.sensor_offset = 0.0  # seconds added to sensor timestamps
        # metadata for XML/GPX
        self.name = ""
        self.route_id = uuid.uuid4().hex
        self.country = ""
        self.title = ""
        self.infos: List[Info] = []
        # GPS processing settings
        self.max_dop = 10.0
        self.ele_window = 5.0
        self.ele_offset = 0.0
        self.use_real_time = False
        self.project_path: Optional[str] = None
        self._out_cache: Optional[Tuple[Tuple, List[OutputPoint]]] = None

    # ------------------------------------------------------------- properties
    @property
    def loaded(self) -> bool:
        return bool(self.chapters)

    @property
    def source_frames(self) -> int:
        return self.chapters[-1].end_frame if self.chapters else 0

    @property
    def has_gps(self) -> bool:
        return not self.track.empty

    @property
    def has_audio(self) -> bool:
        return bool(self.chapters) and all(c.has_audio for c in self.chapters)

    def chapter_for_frame(self, f: int) -> Tuple[int, float]:
        """(chapter index, local seconds) for a global source frame."""
        for i, c in enumerate(self.chapters):
            if f < c.end_frame:
                return i, max(0, f - c.first_frame) / FPS
        if not self.chapters:
            return 0, 0.0
        c = self.chapters[-1]
        return len(self.chapters) - 1, max(0, c.frames - 1) / FPS

    # ---------------------------------------------------------------- loading
    def load_videos(self, paths: Sequence[str], progress: Optional[Callable[[str, float], None]] = None) -> None:
        paths = sorted(paths, key=gopro_sort_key)
        chapters: List[Chapter] = []
        gps: List[GpsSample] = []
        first = 0
        for k, p in enumerate(paths):
            if progress:
                progress(f"Reading {os.path.basename(p)}", k / len(paths))
            movie = mp4.parse_movie(p)
            vt = movie.video_track
            if vt is None:
                raise mp4.Mp4Error(f"{os.path.basename(p)} contains no video track")
            dur = movie.video_duration
            if dur < 0.5:
                from .ffmpeg import probe_duration
                dur = max(dur, probe_duration(p))
            if dur <= 0:
                raise mp4.Mp4Error(f"Could not determine the length of {os.path.basename(p)}")
            frames = max(1, int(round(dur * FPS)))

            def sub(f: float, k=k) -> None:
                if progress:
                    progress(f"Extracting GPS from {os.path.basename(p)}", (k + f) / len(paths))

            samples = extract_gps_from_movie(movie, sub)
            offset = first / FPS
            for s in samples:
                s.t += offset
            gps.extend(samples)
            chapters.append(Chapter(p, dur, frames, first, movie.has_audio,
                                    int(vt.width), int(vt.height), movie.video_fps, len(samples)))
            first += frames
        self.chapters = chapters
        self.raw_gps = gps
        self.edit.reset(self.source_frames)
        if not self.name:
            base = os.path.splitext(os.path.basename(paths[0]))[0]
            self.name = sanitize_name(base)
        if not self.title:
            self.title = self.name
        self.rebuild_track()
        if progress:
            progress("Done", 1.0)

    def rebuild_track(self) -> None:
        cleaned = clean_samples(self.raw_gps, self.max_dop)
        if self.ele_offset:
            cleaned = [GpsSample(s.t, s.lat, s.lon, s.ele + self.ele_offset, s.speed2d, s.speed3d,
                                 s.fix, s.dop, s.utc) for s in cleaned]
        self.track = build_source_track(cleaned, self.source_frames / FPS, ele_window=self.ele_window)
        self._out_cache = None

    def invalidate(self) -> None:
        self._out_cache = None

    # ------------------------------------------------------------- output GPS
    @property
    def output_frames(self) -> int:
        return self.edit.output_frames

    @property
    def output_duration(self) -> float:
        return self.output_frames / FPS

    def output_points(self) -> List[OutputPoint]:
        """One GPS point per second of the edited film (same layout as the reference GPX)."""
        key = (tuple(self.edit.segments), id(self.track), id(self.sensors), self.sensor_offset)
        if self._out_cache and self._out_cache[0] == key:
            return self._out_cache[1]
        pts: List[OutputPoint] = []
        if self.has_gps and self.output_frames > 0:
            n = int(math.floor(self.output_duration - 1e-9)) + 1
            dist = 0.0
            prev = None
            for i in range(n):
                src_t = self.edit.out_to_src_time(float(i), FPS)
                lat, lon, ele, spd = self.track.at(src_t)
                if prev is not None:
                    dist += haversine(prev[0], prev[1], lat, lon)
                prev = (lat, lon)
                hr = cad = None
                if self.sensors is not None:
                    utc = self.track.utc_at(src_t)
                    if utc is not None:
                        hr, cad = self.sensors.at(utc - self.sensor_offset)
                pts.append(OutputPoint(i, lat, lon, ele, spd * 3.6, dist, hr, cad))
        self._out_cache = (key, pts)
        return pts

    def distance_at_output_time(self, t: float) -> float:
        pts = self.output_points()
        if not pts:
            return 0.0
        i = int(math.floor(t))
        if i >= len(pts) - 1:
            return pts[-1].distance
        if i < 0:
            return 0.0
        f = t - i
        return pts[i].distance + (pts[i + 1].distance - pts[i].distance) * f

    def output_time_at_distance(self, d: float) -> float:
        pts = self.output_points()
        for a, b in zip(pts, pts[1:]):
            if b.distance >= d:
                span = b.distance - a.distance
                return a.t + ((d - a.distance) / span if span > 0 else 0)
        return float(pts[-1].t) if pts else 0.0

    def stats(self) -> Tuple[float, float]:
        """(length metres, ascent metres) of the edited route."""
        pts = self.output_points()
        if not pts:
            return 0.0, 0.0
        return pts[-1].distance, ascent([p.ele for p in pts])

    # ---------------------------------------------------------------- persist
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "chapters": [c.path for c in self.chapters],
            "segments": [list(s) for s in self.edit.segments],
            "name": self.name, "id": self.route_id, "country": self.country, "title": self.title,
            "infos": [asdict(i) for i in self.infos],
            "max_dop": self.max_dop, "ele_window": self.ele_window, "ele_offset": self.ele_offset,
            "use_real_time": self.use_real_time,
            "sensor_file": self.sensors.path if self.sensors else None,
            "sensor_offset": self.sensor_offset,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        self.project_path = path

    @classmethod
    def load(cls, path: str, progress: Optional[Callable[[str, float], None]] = None) -> "Project":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        p = cls()
        base = os.path.dirname(os.path.abspath(path))
        chapters = [c if os.path.isabs(c) else os.path.join(base, c) for c in d["chapters"]]
        p.name, p.route_id = d.get("name", ""), d.get("id", p.route_id)
        p.country, p.title = d.get("country", ""), d.get("title", "")
        p.infos = [Info(**i) for i in d.get("infos", [])]
        p.max_dop = d.get("max_dop", 10.0)
        p.ele_window = d.get("ele_window", 5.0)
        p.ele_offset = d.get("ele_offset", 0.0)
        p.use_real_time = d.get("use_real_time", False)
        p.sensor_offset = d.get("sensor_offset", 0.0)
        p.load_videos(chapters, progress)
        sf = d.get("sensor_file")
        if sf and os.path.exists(sf):
            from .sensors import load_sensor_file
            p.sensors = load_sensor_file(sf)
        segs = [tuple(s) for s in d.get("segments", [])]
        if segs:
            p.edit.set_segments(segs, record=False)  # type: ignore[arg-type]
        p.project_path = path
        p.invalidate()
        return p
