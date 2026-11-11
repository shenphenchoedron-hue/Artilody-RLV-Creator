"""Minimal ISO-BMFF (MP4/MOV) parser.

Only the parts needed by RLV Creator are implemented: reading the movie
header, track headers, handler types, sample descriptions, sample tables and
edit lists.  Only the ``moov`` box is read into memory, so multi-gigabyte
GoPro files are handled quickly.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import BinaryIO, Iterator, List, Optional, Tuple

CONTAINER_BOXES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"udta", b"dinf"}


class Mp4Error(Exception):
    pass


@dataclass
class Track:
    track_id: int = 0
    handler: str = ""
    codec: str = ""  # first sample-description fourcc, e.g. 'avc1', 'hvc1', 'gpmd'
    timescale: int = 0
    duration: int = 0  # in track timescale
    width: float = 0.0
    height: float = 0.0
    sample_sizes: List[int] = field(default_factory=list)
    chunk_offsets: List[int] = field(default_factory=list)
    stsc: List[Tuple[int, int, int]] = field(default_factory=list)  # first_chunk, samples_per_chunk, desc_idx
    stts: List[Tuple[int, int]] = field(default_factory=list)  # count, delta
    edit_offset: float = 0.0  # seconds; presentation time = media time + edit_offset
    explicit_offsets: List[int] = field(default_factory=list)  # fragmented MP4: offset of every sample
    trex_duration: int = 0
    trex_size: int = 0

    @property
    def duration_seconds(self) -> float:
        return self.duration / self.timescale if self.timescale else 0.0

    @property
    def sample_count(self) -> int:
        return len(self.sample_sizes)

    def sample_offsets(self) -> List[int]:
        """Absolute file offsets of each sample."""
        if self.explicit_offsets:
            return list(self.explicit_offsets)
        offsets: List[int] = []
        n_samples = len(self.sample_sizes)
        n_chunks = len(self.chunk_offsets)
        if not self.stsc or not n_chunks:
            return offsets
        s = 0
        for i, (first, per_chunk, _desc) in enumerate(self.stsc):
            last = self.stsc[i + 1][0] - 1 if i + 1 < len(self.stsc) else n_chunks
            for chunk in range(first, last + 1):
                if chunk - 1 >= n_chunks:
                    break
                pos = self.chunk_offsets[chunk - 1]
                for _ in range(per_chunk):
                    if s >= n_samples:
                        return offsets
                    offsets.append(pos)
                    pos += self.sample_sizes[s]
                    s += 1
        return offsets

    def sample_times(self) -> List[Tuple[float, float]]:
        """(start, duration) in seconds of each sample, in presentation time."""
        out: List[Tuple[float, float]] = []
        if not self.timescale:
            return out
        t = 0
        for count, delta in self.stts:
            for _ in range(count):
                out.append((t / self.timescale + self.edit_offset, delta / self.timescale))
                t += delta
        # some files have an stts that is shorter than the sample table
        while len(out) < len(self.sample_sizes):
            last_d = out[-1][1] if out else 1.0
            start = out[-1][0] + last_d if out else self.edit_offset
            out.append((start, last_d))
        return out[: len(self.sample_sizes)]


@dataclass
class Movie:
    path: str
    timescale: int = 0
    duration: int = 0
    tracks: List[Track] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return self.duration / self.timescale if self.timescale else 0.0

    def track_by_handler(self, handler: str) -> Optional[Track]:
        for t in self.tracks:
            if t.handler == handler:
                return t
        return None

    @property
    def video_track(self) -> Optional[Track]:
        return self.track_by_handler("vide")

    @property
    def has_audio(self) -> bool:
        return self.track_by_handler("soun") is not None

    @property
    def gpmd_track(self) -> Optional[Track]:
        for t in self.tracks:
            if t.codec == "gpmd":
                return t
        return None

    @property
    def video_duration(self) -> float:
        v = self.video_track
        if v and v.timescale and v.duration:
            return v.duration_seconds
        return self.duration_seconds

    @property
    def video_fps(self) -> float:
        v = self.video_track
        if v and v.sample_count and v.duration:
            return v.sample_count / v.duration_seconds
        return 30.0


def _iter_boxes(data: bytes, start: int = 0, end: Optional[int] = None) -> Iterator[Tuple[bytes, int, int]]:
    """Yield (type, payload_start, payload_end) for boxes inside data[start:end]."""
    end = len(data) if end is None else end
    pos = start
    while pos + 8 <= end:
        size, btype = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            break
        yield btype, pos + header, min(pos + size, end)
        pos += size


def _find_moov(f: BinaryIO) -> bytes:
    f.seek(0, 2)
    file_size = f.tell()
    pos = 0
    while pos + 8 <= file_size:
        f.seek(pos)
        hdr = f.read(16)
        if len(hdr) < 8:
            break
        size, btype = struct.unpack(">I4s", hdr[:8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", hdr[8:16])[0]
            header = 16
        elif size == 0:
            size = file_size - pos
        if size < header:
            raise Mp4Error("Corrupt MP4 box structure")
        if btype == b"moov":
            f.seek(pos + header)
            return f.read(size - header)
        pos += size
    raise Mp4Error("No 'moov' box found - is this a valid MP4 file?")


def _parse_trak(data: bytes, start: int, end: int, movie_timescale: int) -> Track:
    trk = Track()
    edits: List[Tuple[int, int]] = []  # (segment_duration [movie ts], media_time [track ts])

    def walk(s: int, e: int) -> None:
        for btype, ps, pe in _iter_boxes(data, s, e):
            if btype in CONTAINER_BOXES:
                walk(ps, pe)
            elif btype == b"tkhd":
                version = data[ps]
                if version == 1:
                    trk.track_id = struct.unpack(">I", data[ps + 20:ps + 24])[0]
                    wh = ps + 4 + 32 + 52
                else:
                    trk.track_id = struct.unpack(">I", data[ps + 12:ps + 16])[0]
                    wh = ps + 4 + 20 + 52
                if wh + 8 <= pe:
                    w, h = struct.unpack(">II", data[wh:wh + 8])
                    trk.width, trk.height = w / 65536.0, h / 65536.0
            elif btype == b"mdhd":
                version = data[ps]
                if version == 1:
                    trk.timescale, trk.duration = struct.unpack(">IQ", data[ps + 20:ps + 32])
                else:
                    trk.timescale, trk.duration = struct.unpack(">II", data[ps + 12:ps + 20])
            elif btype == b"hdlr":
                trk.handler = data[ps + 8:ps + 12].decode("latin-1")
            elif btype == b"stsd":
                count = struct.unpack(">I", data[ps + 4:ps + 8])[0]
                if count:
                    trk.codec = data[ps + 12:ps + 16].decode("latin-1")
            elif btype == b"stsz":
                sample_size, count = struct.unpack(">II", data[ps + 4:ps + 12])
                if sample_size:
                    trk.sample_sizes = [sample_size] * count
                else:
                    trk.sample_sizes = list(struct.unpack(">%dI" % count, data[ps + 12:ps + 12 + 4 * count]))
            elif btype == b"stco":
                count = struct.unpack(">I", data[ps + 4:ps + 8])[0]
                trk.chunk_offsets = list(struct.unpack(">%dI" % count, data[ps + 8:ps + 8 + 4 * count]))
            elif btype == b"co64":
                count = struct.unpack(">I", data[ps + 4:ps + 8])[0]
                trk.chunk_offsets = list(struct.unpack(">%dQ" % count, data[ps + 8:ps + 8 + 8 * count]))
            elif btype == b"stsc":
                count = struct.unpack(">I", data[ps + 4:ps + 8])[0]
                vals = struct.unpack(">%dI" % (3 * count), data[ps + 8:ps + 8 + 12 * count])
                trk.stsc = [tuple(vals[i:i + 3]) for i in range(0, len(vals), 3)]  # type: ignore[misc]
            elif btype == b"stts":
                count = struct.unpack(">I", data[ps + 4:ps + 8])[0]
                vals = struct.unpack(">%dI" % (2 * count), data[ps + 8:ps + 8 + 8 * count])
                trk.stts = [tuple(vals[i:i + 2]) for i in range(0, len(vals), 2)]  # type: ignore[misc]
            elif btype == b"elst":
                version = data[ps]
                count = struct.unpack(">I", data[ps + 4:ps + 8])[0]
                p = ps + 8
                for _ in range(count):
                    if version == 1:
                        seg_dur, media_time = struct.unpack(">Qq", data[p:p + 16])
                        p += 20
                    else:
                        seg_dur, media_time = struct.unpack(">Ii", data[p:p + 8])
                        p += 12
                    edits.append((seg_dur, media_time))

    walk(start, end)

    offset = 0.0
    first_real = True
    for seg_dur, media_time in edits:
        if media_time == -1:
            if movie_timescale:
                offset += seg_dur / movie_timescale
        elif first_real:
            if trk.timescale:
                offset -= media_time / trk.timescale
            first_real = False
    trk.edit_offset = offset
    return trk


def _parse_fragments(f: BinaryIO, movie: Movie, moov: bytes) -> None:
    """Fragmented MP4 (moof/traf/trun): collect sample tables from all fragments."""
    by_id = {t.track_id: t for t in movie.tracks}
    # defaults from moov/mvex/trex
    for btype, ps, pe in _iter_boxes(moov):
        if btype == b"mvex":
            for bt, cs, ce in _iter_boxes(moov, ps, pe):
                if bt == b"trex":
                    tid, _desc, dur, size = struct.unpack(">IIII", moov[cs + 4:cs + 20])
                    if tid in by_id:
                        by_id[tid].trex_duration, by_id[tid].trex_size = dur, size
    f.seek(0, 2)
    file_size = f.tell()
    pos = 0
    found = False
    while pos + 8 <= file_size:
        f.seek(pos)
        hdr = f.read(16)
        if len(hdr) < 8:
            break
        size, btype = struct.unpack(">I4s", hdr[:8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", hdr[8:16])[0]
            header = 16
        elif size == 0:
            size = file_size - pos
        if size < header:
            break
        if btype == b"moof" and size < 64 * 1024 * 1024:
            f.seek(pos + header)
            data = f.read(size - header)
            moof_start = pos
            for bt, ts, te in _iter_boxes(data):
                if bt != b"traf":
                    continue
                trk = None
                base = moof_start
                def_dur = def_size = 0
                for b2, cs, ce in _iter_boxes(data, ts, te):
                    if b2 == b"tfhd":
                        flags = struct.unpack(">I", data[cs:cs + 4])[0] & 0xFFFFFF
                        tid = struct.unpack(">I", data[cs + 4:cs + 8])[0]
                        trk = by_id.get(tid)
                        q = cs + 8
                        if flags & 0x01:
                            base = struct.unpack(">Q", data[q:q + 8])[0]
                            q += 8
                        if flags & 0x02:
                            q += 4
                        if flags & 0x08:
                            def_dur = struct.unpack(">I", data[q:q + 4])[0]
                            q += 4
                        elif trk:
                            def_dur = trk.trex_duration
                        if flags & 0x10:
                            def_size = struct.unpack(">I", data[q:q + 4])[0]
                            q += 4
                        elif trk:
                            def_size = trk.trex_size
                    elif b2 == b"trun" and trk is not None:
                        found = True
                        vf = struct.unpack(">I", data[cs:cs + 4])[0]
                        flags = vf & 0xFFFFFF
                        count = struct.unpack(">I", data[cs + 4:cs + 8])[0]
                        q = cs + 8
                        off = base
                        if flags & 0x01:
                            off = base + struct.unpack(">i", data[q:q + 4])[0]
                            q += 4
                        if flags & 0x04:
                            q += 4
                        for _ in range(count):
                            dur, sz = def_dur, def_size
                            if flags & 0x100:
                                dur = struct.unpack(">I", data[q:q + 4])[0]
                                q += 4
                            if flags & 0x200:
                                sz = struct.unpack(">I", data[q:q + 4])[0]
                                q += 4
                            if flags & 0x400:
                                q += 4
                            if flags & 0x800:
                                q += 4
                            if not trk.explicit_offsets and trk.sample_sizes:
                                trk.explicit_offsets = trk.sample_offsets()
                            trk.explicit_offsets.append(off)
                            trk.sample_sizes.append(sz)
                            trk.stts.append((1, dur))
                            off += sz
        pos += size
    if found:
        for t in movie.tracks:
            total = sum(c * d for c, d in t.stts)
            if total > t.duration:
                t.duration = total
        if movie.timescale:
            longest = max((t.duration_seconds for t in movie.tracks), default=0.0)
            movie.duration = max(movie.duration, int(longest * movie.timescale))


def parse_movie(path: str) -> Movie:
    with open(path, "rb") as f:
        moov = _find_moov(f)
        movie = _parse_moov(path, moov)
        if any(bt == b"mvex" for bt, _s, _e in _iter_boxes(moov)):
            _parse_fragments(f, movie, moov)
    if not movie.tracks:
        raise Mp4Error("MP4 file contains no tracks")
    return movie


def _parse_moov(path: str, moov: bytes) -> Movie:
    movie = Movie(path=path)
    for btype, ps, pe in _iter_boxes(moov):
        if btype == b"mvhd":
            version = moov[ps]
            if version == 1:
                movie.timescale, movie.duration = struct.unpack(">IQ", moov[ps + 20:ps + 32])
            else:
                movie.timescale, movie.duration = struct.unpack(">II", moov[ps + 12:ps + 20])
    for btype, ps, pe in _iter_boxes(moov):
        if btype == b"trak":
            movie.tracks.append(_parse_trak(moov, ps, pe, movie.timescale))
    return movie


def read_samples(path: str, track: Track) -> Iterator[Tuple[float, float, bytes]]:
    """Yield (start_seconds, duration_seconds, payload) for every sample of a track."""
    offsets = track.sample_offsets()
    times = track.sample_times()
    with open(path, "rb") as f:
        for off, size, (t, d) in zip(offsets, track.sample_sizes, times):
            f.seek(off)
            yield t, d, f.read(size)
