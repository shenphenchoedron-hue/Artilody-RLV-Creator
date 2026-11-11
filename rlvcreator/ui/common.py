from __future__ import annotations

from ..project import FPS


def fmt_frames(frames: int, with_frames: bool = True) -> str:
    frames = max(0, int(frames))
    s, ff = divmod(frames, FPS)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    base = f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
    return f"{base}.{ff:02d}" if with_frames else base


def fmt_seconds(sec: float) -> str:
    return fmt_frames(int(round(sec * FPS)), with_frames=False)


def fmt_distance(m: float) -> str:
    return f"{m / 1000:.2f} km" if m >= 1000 else f"{m:.0f} m"
