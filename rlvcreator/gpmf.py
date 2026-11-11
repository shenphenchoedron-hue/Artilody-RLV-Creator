"""GoPro GPMF telemetry parser - extracts GPS data (GPS5 and GPS9 streams).

GPMF is a KLV format: 4 byte FourCC key, 1 byte type, 1 byte structure
size, 2 byte repeat count, followed by the data padded to 32 bits.
See https://github.com/gopro/gpmf-parser for the specification.
"""

from __future__ import annotations

import datetime as _dt
import re
import struct
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .mp4 import Movie, parse_movie, read_samples

# type char -> (struct format, size)
_TYPES: Dict[str, Tuple[str, int]] = {
    "b": ("b", 1), "B": ("B", 1), "c": ("c", 1),
    "s": ("h", 2), "S": ("H", 2),
    "l": ("i", 4), "L": ("I", 4),
    "f": ("f", 4), "d": ("d", 8),
    "j": ("q", 8), "J": ("Q", 8),
    "q": ("i", 4),  # Q15.16 fixed point (signed) - value / 65536
    "Q": ("q", 8),  # Q31.32 fixed point - value / 2**32
    "F": ("4s", 4),
}


class GpmfError(Exception):
    pass


@dataclass
class GpsSample:
    t: float  # seconds from the start of the video file (presentation time)
    lat: float
    lon: float
    ele: float
    speed2d: float  # m/s
    speed3d: float  # m/s
    fix: int  # 0 none, 2 = 2D, 3 = 3D
    dop: float  # dilution of precision (e.g. 1.5)
    utc: Optional[float] = None  # POSIX timestamp, if known


def _expand_type_string(s: str) -> str:
    """Expand array notation in TYPE strings, e.g. 'f[3]L' -> 'fffL'."""
    return re.sub(r"(.)\[(\d+)\]", lambda m: m.group(1) * int(m.group(2)), s)


def _klv_iter(buf: bytes, start: int = 0, end: Optional[int] = None):
    end = len(buf) if end is None else end
    pos = start
    while pos + 8 <= end:
        key = buf[pos:pos + 4]
        typ = chr(buf[pos + 4])
        size = buf[pos + 5]
        repeat = struct.unpack(">H", buf[pos + 6:pos + 8])[0]
        data_len = size * repeat
        data_start = pos + 8
        if key == b"\x00\x00\x00\x00":
            break
        yield key, typ, size, repeat, data_start, data_start + data_len
        pos = data_start + ((data_len + 3) & ~3)


def _decode_values(buf: bytes, typ: str, size: int, repeat: int, ds: int,
                   complex_type: Optional[str] = None) -> List[List[float]]:
    """Return list of samples, each a list of numeric values."""
    if typ == "?":
        if not complex_type:
            return []
        fields = _expand_type_string(complex_type)
        fmt = ">" + "".join(_TYPES[c][0] for c in fields)
    elif typ in ("c", "U"):
        return []
    elif typ in _TYPES:
        fmt_c, elem = _TYPES[typ]
        if typ == "F" or elem == 0:
            return []
        n = size // elem
        fmt = ">" + fmt_c * n
        fields = typ * n
    else:
        return []
    ssize = struct.calcsize(fmt)
    if ssize != size:
        return []
    out = []
    for i in range(repeat):
        vals = list(struct.unpack_from(fmt, buf, ds + i * size))
        for j, c in enumerate(fields):
            if c == "q":
                vals[j] = vals[j] / 65536.0
            elif c == "Q":
                vals[j] = vals[j] / 4294967296.0
        out.append(vals)
    return out


def _parse_gpsu(raw: bytes) -> Optional[float]:
    """GPSU is 'yymmddhhmmss.sss' in UTC."""
    try:
        s = raw.decode("ascii").strip("\x00 ")
        dt = _dt.datetime.strptime(s[:12], "%y%m%d%H%M%S").replace(tzinfo=_dt.timezone.utc)
        frac = float("0" + s[12:]) if len(s) > 12 else 0.0
        return dt.timestamp() + frac
    except (ValueError, UnicodeDecodeError):
        return None


_GPS9_EPOCH = _dt.datetime(2000, 1, 1, tzinfo=_dt.timezone.utc).timestamp()


def parse_payload(payload: bytes, t0: float, dur: float) -> Tuple[List[GpsSample], List[GpsSample]]:
    """Parse one GPMF payload. Returns (gps5_samples, gps9_samples)."""
    gps5: List[GpsSample] = []
    gps9: List[GpsSample] = []

    def walk_strm(s: int, e: int) -> None:
        scal: Sequence[float] = [1.0]
        ctype: Optional[str] = None
        fix, dop, utc = 3, 0.0, None
        for key, typ, size, repeat, ds, de in _klv_iter(payload, s, e):
            if key == b"SCAL":
                vals = _decode_values(payload, typ, size, repeat, ds)
                if vals:
                    flat = [v for row in vals for v in row]
                    scal = flat or [1.0]
            elif key == b"TYPE":
                ctype = payload[ds:de].decode("latin-1").rstrip("\x00")
            elif key == b"GPSF":
                vals = _decode_values(payload, typ, size, repeat, ds)
                if vals:
                    fix = int(vals[0][0])
            elif key == b"GPSP":
                vals = _decode_values(payload, typ, size, repeat, ds)
                if vals:
                    dop = vals[0][0] / 100.0
            elif key == b"GPSU":
                utc = _parse_gpsu(payload[ds:ds + 16])
            elif key == b"GPS5":
                rows = _decode_values(payload, typ, size, repeat, ds, ctype)
                n = len(rows)
                for i, r in enumerate(rows):
                    sc = [scal[j] if j < len(scal) else scal[-1] for j in range(len(r))]
                    v = [r[j] / (sc[j] or 1.0) for j in range(len(r))]
                    t = t0 + dur * i / n
                    gps5.append(GpsSample(t, v[0], v[1], v[2], v[3], v[4], fix, dop,
                                          utc + dur * i / n if utc is not None else None))
            elif key == b"GPS9":
                rows = _decode_values(payload, typ, size, repeat, ds, ctype or "lllllllSS")
                n = len(rows)
                for i, r in enumerate(rows):
                    if len(r) < 9:
                        continue
                    sc = [scal[j] if j < len(scal) else scal[-1] for j in range(len(r))]
                    v = [r[j] / (sc[j] or 1.0) for j in range(len(r))]
                    t = t0 + dur * i / n
                    sample_utc = _GPS9_EPOCH + v[5] * 86400.0 + v[6]
                    gps9.append(GpsSample(t, v[0], v[1], v[2], v[3], v[4], int(v[8]), v[7], sample_utc))

    def walk(s: int, e: int) -> None:
        for key, typ, size, repeat, ds, de in _klv_iter(payload, s, e):
            if typ == "\x00":
                if key == b"STRM":
                    walk_strm(ds, de)
                else:  # DEVC or other nest
                    walk(ds, de)

    walk(0, len(payload))
    return gps5, gps9


def extract_gps_from_movie(movie: Movie, progress: Optional[Callable[[float], None]] = None) -> List[GpsSample]:
    trk = movie.gpmd_track
    if trk is None:
        return []
    all5: List[GpsSample] = []
    all9: List[GpsSample] = []
    n = max(1, trk.sample_count)
    for i, (t, d, payload) in enumerate(read_samples(movie.path, trk)):
        g5, g9 = parse_payload(payload, t, d)
        all5.extend(g5)
        all9.extend(g9)
        if progress and i % 50 == 0:
            progress(i / n)
    if progress:
        progress(1.0)
    return all9 if all9 else all5


def extract_gps(path: str, progress: Optional[Callable[[float], None]] = None) -> List[GpsSample]:
    return extract_gps_from_movie(parse_movie(path), progress)
