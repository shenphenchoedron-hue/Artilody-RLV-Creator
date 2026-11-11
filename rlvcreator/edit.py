"""Frame accurate edit model with undo/redo.

The edit is a list of *kept* segments ``[start, end)`` expressed in frames of
the source timeline (all chapters joined, at the fixed output frame rate).
The output film is the concatenation of the kept segments.  Video and GPS
are both derived from the same segments, so they always stay in sync.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Segment = Tuple[int, int]


@dataclass
class _State:
    segments: List[Segment]
    label: str


@dataclass
class EditModel:
    source_frames: int = 0
    segments: List[Segment] = field(default_factory=list)
    _undo: List[_State] = field(default_factory=list)
    _redo: List[_State] = field(default_factory=list)
    _starts: List[int] = field(default_factory=list)  # output start frame of each segment

    def __post_init__(self) -> None:
        if not self.segments and self.source_frames > 0:
            self.segments = [(0, self.source_frames)]
        self._reindex()

    # ------------------------------------------------------------------ basics
    def reset(self, source_frames: int) -> None:
        self.source_frames = source_frames
        self.segments = [(0, source_frames)] if source_frames > 0 else []
        self._undo.clear()
        self._redo.clear()
        self._reindex()

    def _reindex(self) -> None:
        self._starts = []
        acc = 0
        for a, b in self.segments:
            self._starts.append(acc)
            acc += b - a
        self._total = acc

    @property
    def output_frames(self) -> int:
        return self._total

    def join_points(self) -> List[int]:
        """Output frames where two kept segments meet (i.e. where something was cut)."""
        return self._starts[1:]

    def removed_source_ranges(self) -> List[Segment]:
        out: List[Segment] = []
        pos = 0
        for a, b in self.segments:
            if a > pos:
                out.append((pos, a))
            pos = b
        if pos < self.source_frames:
            out.append((pos, self.source_frames))
        return out

    # ----------------------------------------------------------------- mapping
    def out_to_src(self, f: int) -> int:
        """Map an output frame to a source frame. Clamps to the valid range."""
        if not self.segments:
            return 0
        f = max(0, min(f, self._total - 1)) if self._total else 0
        i = bisect.bisect_right(self._starts, f) - 1
        a, _b = self.segments[i]
        return a + (f - self._starts[i])

    def out_to_src_time(self, t: float, fps: float) -> float:
        """Continuous mapping of output seconds to source seconds."""
        if not self.segments:
            return 0.0
        x = t * fps
        i = bisect.bisect_right(self._starts, int(x)) - 1
        i = max(0, min(i, len(self.segments) - 1))
        a, b = self.segments[i]
        local = min(x - self._starts[i], b - a)
        return (a + local) / fps

    def src_to_out(self, f: int) -> Optional[int]:
        """Map a source frame to an output frame, or None if it was cut away."""
        for (a, b), s in zip(self.segments, self._starts):
            if a <= f < b:
                return s + (f - a)
        return None

    def next_kept_src(self, f: int) -> Optional[int]:
        """First kept source frame >= f, or None if nothing is kept after f."""
        for a, b in self.segments:
            if f < b:
                return max(a, f)
        return None

    def segment_index_for_src(self, f: int) -> Optional[int]:
        for i, (a, b) in enumerate(self.segments):
            if a <= f < b:
                return i
        return None

    # ----------------------------------------------------------------- editing
    def _push(self, label: str) -> None:
        self._undo.append(_State(list(self.segments), label))
        self._redo.clear()

    def cut(self, out_start: int, out_end: int, label: str = "") -> bool:
        """Remove output frames [out_start, out_end). Returns True if anything changed."""
        out_start = max(0, out_start)
        out_end = min(self._total, out_end)
        if out_end <= out_start:
            return False
        if out_start == 0 and out_end >= self._total:
            return False  # refuse to delete everything
        new: List[Segment] = []
        for (a, b), s in zip(self.segments, self._starts):
            e = s + (b - a)
            if e <= out_start or s >= out_end:
                new.append((a, b))
                continue
            if s < out_start:
                new.append((a, a + (out_start - s)))
            if e > out_end:
                new.append((a + (out_end - s), b))
        self._push(label or "Cut")
        self.segments = self._merge(new)
        self._reindex()
        return True

    @staticmethod
    def _merge(segs: List[Segment]) -> List[Segment]:
        out: List[Segment] = []
        for a, b in sorted(segs):
            if b <= a:
                continue
            if out and a <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        return out

    def restore_source_range(self, a: int, b: int, label: str = "Restore") -> bool:
        """Put a removed source range back into the film."""
        a, b = max(0, a), min(self.source_frames, b)
        if b <= a:
            return False
        merged = self._merge(self.segments + [(a, b)])
        if merged == self.segments:
            return False
        self._push(label)
        self.segments = merged
        self._reindex()
        return True

    def set_segments(self, segments: List[Segment], label: str = "Edit", record: bool = True) -> None:
        if record:
            self._push(label)
        self.segments = self._merge(list(segments))
        self._reindex()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def undo(self) -> bool:
        if not self._undo:
            return False
        st = self._undo.pop()
        self._redo.append(_State(list(self.segments), st.label))
        self.segments = st.segments
        self._reindex()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        st = self._redo.pop()
        self._undo.append(_State(list(self.segments), st.label))
        self.segments = st.segments
        self._reindex()
        return True
