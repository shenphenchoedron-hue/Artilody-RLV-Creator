"""GPS track processing: cleaning, smoothing, resampling and geometry helpers."""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .gpmf import GpsSample

EARTH_RADIUS = 6371008.8


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS * math.asin(min(1.0, math.sqrt(a)))


def clean_samples(samples: Sequence[GpsSample], max_dop: float = 10.0,
                  max_speed: float = 70.0) -> List[GpsSample]:
    """Remove samples without a fix, with bad precision, or physically impossible jumps."""
    good = [s for s in samples
            if s.fix >= 2 and (max_dop <= 0 or s.dop <= max_dop)
            and -90 <= s.lat <= 90 and -180 <= s.lon <= 180 and not (s.lat == 0 and s.lon == 0)]
    if not good:
        # fall back to fix only - some cameras report pessimistic DOP values
        good = [s for s in samples if s.fix >= 2 and not (s.lat == 0 and s.lon == 0)]
    good.sort(key=lambda s: s.t)
    out: List[GpsSample] = []
    for s in good:
        if out:
            prev = out[-1]
            dt = s.t - prev.t
            if dt <= 0:
                continue
            if haversine(prev.lat, prev.lon, s.lat, s.lon) / dt > max_speed and dt < 5:
                continue
        out.append(s)
    return out


def _window_mean(times: List[float], values: List[float], grid: List[float], half: float) -> List[Optional[float]]:
    """Mean of values whose time lies within +-half of each grid time (None when empty)."""
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    res: List[Optional[float]] = []
    for g in grid:
        lo = bisect.bisect_left(times, g - half)
        hi = bisect.bisect_right(times, g + half)
        res.append((prefix[hi] - prefix[lo]) / (hi - lo) if hi > lo else None)
    return res


def _fill_gaps(vals: List[Optional[float]]) -> List[float]:
    n = len(vals)
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        return [0.0] * n
    out = [0.0] * n
    for i in range(0, known[0] + 1):
        out[i] = vals[known[0]]  # type: ignore[assignment]
    for a, b in zip(known, known[1:]):
        va, vb = vals[a], vals[b]
        for i in range(a, b + 1):
            out[i] = va + (vb - va) * (i - a) / (b - a)  # type: ignore[operator]
    for i in range(known[-1], n):
        out[i] = vals[known[-1]]  # type: ignore[assignment]
    return out


@dataclass
class SourceTrack:
    """GPS track resampled to a regular grid on the source (unedited) timeline."""

    rate: float = 10.0  # grid points per second
    lat: List[float] = field(default_factory=list)
    lon: List[float] = field(default_factory=list)
    ele: List[float] = field(default_factory=list)
    speed: List[float] = field(default_factory=list)  # m/s
    utc: List[Optional[float]] = field(default_factory=list)
    valid: List[bool] = field(default_factory=list)  # grid point had real GPS data nearby

    @property
    def empty(self) -> bool:
        return not self.lat

    def _idx(self, t: float) -> Tuple[int, int, float]:
        n = len(self.lat)
        x = max(0.0, min(t * self.rate, n - 1))
        i = int(math.floor(x))
        j = min(i + 1, n - 1)
        return i, j, x - i

    def at(self, t: float) -> Tuple[float, float, float, float]:
        """(lat, lon, ele, speed m/s) at source time t (linear interpolation)."""
        if self.empty:
            return 0.0, 0.0, 0.0, 0.0
        i, j, f = self._idx(t)
        lerp = lambda arr: arr[i] + (arr[j] - arr[i]) * f  # noqa: E731
        return lerp(self.lat), lerp(self.lon), lerp(self.ele), lerp(self.speed)

    def utc_at(self, t: float) -> Optional[float]:
        if self.empty:
            return None
        i, j, f = self._idx(t)
        a, b = self.utc[i], self.utc[j]
        if a is None or b is None:
            return a if a is not None else b
        return a + (b - a) * f


def build_source_track(samples: Sequence[GpsSample], duration: float, rate: float = 10.0,
                       pos_window: float = 1.0, ele_window: float = 5.0,
                       speed_window: float = 2.0) -> SourceTrack:
    track = SourceTrack(rate=rate)
    if not samples or duration <= 0:
        return track
    n = int(math.floor(duration * rate)) + 1
    grid = [i / rate for i in range(n)]
    times = [s.t for s in samples]
    lat = _window_mean(times, [s.lat for s in samples], grid, pos_window / 2)
    lon = _window_mean(times, [s.lon for s in samples], grid, pos_window / 2)
    ele = _window_mean(times, [s.ele for s in samples], grid, ele_window / 2)
    spd = _window_mean(times, [s.speed2d for s in samples], grid, speed_window / 2)
    track.valid = [v is not None for v in lat]
    track.lat, track.lon = _fill_gaps(lat), _fill_gaps(lon)
    track.ele, track.speed = _fill_gaps(ele), _fill_gaps(spd)

    utc_samples = [(s.t, s.utc) for s in samples if s.utc is not None]
    if len(utc_samples) >= 2:
        # GPS clock is very stable: fit utc = a + t (rate 1) using the median offset
        offsets = sorted(u - t for t, u in utc_samples)
        off = offsets[len(offsets) // 2]
        track.utc = [g + off for g in grid]
    else:
        track.utc = [None] * n
    return track


def ascent(elevations: Sequence[float], threshold: float = 2.0) -> float:
    """Total ascent with hysteresis to suppress GPS noise."""
    if not elevations:
        return 0.0
    total = 0.0
    ref = elevations[0]
    for e in elevations[1:]:
        if e > ref + threshold:
            total += e - ref
            ref = e
        elif e < ref - threshold:
            ref = e
    return total
