"""Optional heart-rate / cadence data from a bike computer or watch (GPX or TCX).

GoPro cameras do not record heart rate or cadence.  When a sensor file
recorded at the same time is supplied, its values are matched to the video
by UTC time (the GoPro GPS clock) and written to the GPX output.
"""

from __future__ import annotations

import bisect
import datetime as _dt
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_iso_time(s: str) -> Optional[float]:
    s = s.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.timestamp()


@dataclass
class SensorData:
    path: str
    times: List[float] = field(default_factory=list)
    hr: List[Optional[int]] = field(default_factory=list)
    cad: List[Optional[int]] = field(default_factory=list)
    max_gap: float = 5.0

    @property
    def has_hr(self) -> bool:
        return any(v is not None for v in self.hr)

    @property
    def has_cad(self) -> bool:
        return any(v is not None for v in self.cad)

    @property
    def time_range(self) -> Tuple[float, float]:
        return (self.times[0], self.times[-1]) if self.times else (0.0, 0.0)

    def at(self, utc: float) -> Tuple[Optional[int], Optional[int]]:
        if not self.times:
            return None, None
        i = bisect.bisect_left(self.times, utc)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(self.times):
                d = abs(self.times[j] - utc)
                if d <= self.max_gap and (best is None or d < best[0]):
                    best = (d, j)
        if best is None:
            return None, None
        return self.hr[best[1]], self.cad[best[1]]


def _int_or_none(text: Optional[str]) -> Optional[int]:
    try:
        return int(round(float(text))) if text is not None and text.strip() else None
    except ValueError:
        return None


def load_sensor_file(path: str) -> SensorData:
    tree = ET.parse(path)
    root = tree.getroot()
    rows: List[Tuple[float, Optional[int], Optional[int]]] = []
    for el in root.iter():
        name = _local(el.tag)
        if name not in ("trkpt", "Trackpoint"):
            continue
        t = hr = cad = None
        for sub in el.iter():
            n = _local(sub.tag)
            if n in ("time", "Time"):
                t = parse_iso_time(sub.text or "")
            elif n == "hr":
                hr = _int_or_none(sub.text)
            elif n == "HeartRateBpm":
                for v in sub.iter():
                    if _local(v.tag) == "Value":
                        hr = _int_or_none(v.text)
            elif n in ("cad", "Cadence", "RunCadence"):
                cad = _int_or_none(sub.text)
        if t is not None:
            rows.append((t, hr, cad))
    rows.sort(key=lambda r: r[0])
    data = SensorData(path)
    for t, h, c in rows:
        data.times.append(t)
        data.hr.append(h)
        data.cad.append(c)
    if not data.times:
        raise ValueError("No time-stamped track points found in sensor file")
    return data
