"""Locating FFmpeg, detecting HEVC encoders and rendering the edited film."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .project import FPS, Project

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _bundled_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg(custom: Optional[str] = None) -> Optional[str]:
    """Find an FFmpeg executable: custom path, bundled copy, imageio-ffmpeg, PATH."""
    if custom and os.path.isfile(custom):
        return custom
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for d in (_bundled_dir(), os.path.join(_bundled_dir(), "ffmpeg"), os.path.dirname(sys.executable)):
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    try:
        import imageio_ffmpeg  # type: ignore

        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.isfile(p):
            return p
    return None


def _run(args: Sequence[str], timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                          creationflags=_CREATE_NO_WINDOW)


@dataclass
class Encoder:
    name: str  # ffmpeg encoder name
    label: str


ENCODER_LABELS: Dict[str, str] = {
    "libx265": "x265 (software, best quality)",
    "hevc_nvenc": "NVIDIA NVENC (hardware, fast)",
    "hevc_qsv": "Intel Quick Sync (hardware, fast)",
    "hevc_amf": "AMD AMF (hardware, fast)",
    "hevc_videotoolbox": "Apple VideoToolbox (hardware, fast)",
}


def detect_encoders(ffmpeg: str) -> List[Encoder]:
    """Return HEVC encoders that are actually usable on this machine."""
    try:
        listing = _run([ffmpeg, "-hide_banner", "-encoders"]).stdout.decode("utf-8", "replace")
    except Exception:
        return []
    found: List[Encoder] = []
    for name, label in ENCODER_LABELS.items():
        if f" {name} " not in listing:
            continue
        if name != "libx265":
            # hardware encoders are compiled in everywhere; test that the device exists
            try:
                r = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                          "color=c=black:s=640x360:r=30:d=0.2", "-c:v", name, "-f", "null", "-"], timeout=20)
                if r.returncode != 0:
                    continue
            except Exception:
                continue
        found.append(Encoder(name, label))
    return found


def encoder_args(name: str, quality: int, preset: str) -> List[str]:
    """quality: 0..100 slider (higher = better)."""
    crf = int(round(34 - quality * 0.16))  # 100 -> 18, 50 -> 26, 0 -> 34
    if name == "libx265":
        return ["-c:v", "libx265", "-preset", preset, "-crf", str(crf),
                "-x265-params", "log-level=error:keyint=60:min-keyint=30"]
    if name == "hevc_nvenc":
        return ["-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf), "-b:v", "0",
                "-g", "60"]
    if name == "hevc_qsv":
        return ["-c:v", "hevc_qsv", "-global_quality", str(crf), "-g", "60"]
    if name == "hevc_amf":
        return ["-c:v", "hevc_amf", "-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf), "-g", "60"]
    if name == "hevc_videotoolbox":
        return ["-c:v", "hevc_videotoolbox", "-q:v", str(max(1, min(100, quality))), "-g", "60"]
    raise ValueError(f"Unknown encoder {name}")


@dataclass
class ExportSettings:
    encoder: str = "libx265"
    quality: int = 62  # -> CRF 24
    preset: str = "medium"
    fit: str = "crop"  # 'crop' fills 16:9 by cropping, 'pad' letterboxes
    audio: bool = False
    width: int = 1920
    height: int = 1080


def build_command(ffmpeg: str, project: Project, out_path: str, s: ExportSettings) -> Tuple[List[str], int]:
    """Build the FFmpeg command line. Returns (args, total_output_frames)."""
    segs = project.edit.segments
    audio = s.audio and project.has_audio
    args: List[str] = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    filters: List[str] = []
    concat_inputs: List[str] = []
    n_in = 0
    total = 0
    W, H = s.width, s.height
    if s.fit == "pad":
        scale = (f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                 f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:
        scale = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}"
    for ch in project.chapters:
        # kept frame ranges inside this chapter, in chapter-local frames
        local: List[Tuple[int, int]] = []
        for a, b in segs:
            lo, hi = max(a, ch.first_frame), min(b, ch.end_frame)
            if hi > lo:
                local.append((lo - ch.first_frame, hi - ch.first_frame))
        if not local:
            continue
        # only decode the part of the chapter that is actually needed
        first_needed = local[0][0]
        last_needed = local[-1][1]
        seek = max(0, first_needed - FPS * 2)  # start a little early, trimmed exactly by frame index
        seek_s = seek / FPS
        args += ["-ss", f"{seek_s:.6f}", "-t", f"{(last_needed - seek) / FPS + 2:.6f}", "-i", ch.path]
        rel = [(a - seek, b - seek) for a, b in local]
        cond = "+".join(f"between(n\\,{a}\\,{b - 1})" for a, b in rel)
        nf = last_needed - seek
        frames = sum(b - a for a, b in local)
        total += frames
        filters.append(
            f"[{n_in}:v]setpts=PTS-STARTPTS,fps={FPS},tpad=stop_mode=clone:stop_duration=2,"
            f"trim=end_frame={nf},select='{cond}',setpts=N/({FPS}*TB),{scale},setsar=1,format=yuv420p[v{n_in}]")
        concat_inputs.append(f"[v{n_in}]")
        if audio:
            acond = "+".join(f"between(t\\,{a / FPS:.6f}\\,{b / FPS - 1e-6:.6f})" for a, b in rel)
            filters.append(
                f"[{n_in}:a]aresample=48000:async=1,asetpts=PTS-STARTPTS,apad,atrim=end={nf / FPS:.6f},"
                f"aselect='{acond}',asetpts=N/SR/TB[a{n_in}]")
            concat_inputs.append(f"[a{n_in}]")
        n_in += 1
    if n_in == 0:
        raise ValueError("Nothing to export - the film is empty")
    filters.append("".join(concat_inputs) + f"concat=n={n_in}:v=1:a={1 if audio else 0}"
                   + ("[vout][aout]" if audio else "[vout]"))
    args += ["-filter_complex", ";".join(filters), "-map", "[vout]"]
    if audio:
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    args += encoder_args(s.encoder, s.quality, s.preset)
    args += ["-pix_fmt", "yuv420p", "-r", str(FPS), "-frames:v", str(total),
             "-tag:v", "hvc1", "-movflags", "+faststart", "-map_metadata", "-1",
             "-progress", "pipe:1", "-nostats", out_path]
    return args, total


class Renderer:
    """Runs FFmpeg in a background thread and reports progress."""

    def __init__(self, args: List[str], total_frames: int,
                 on_progress: Callable[[float, str], None], on_done: Callable[[bool, str], None]) -> None:
        self.args = args
        self.total = max(1, total_frames)
        self.on_progress = on_progress
        self.on_done = on_done
        self.proc: Optional[subprocess.Popen] = None
        self.cancelled = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q") if self.proc.stdin else None  # type: ignore[func-returns-value]
            except Exception:
                pass
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _run(self) -> None:
        err_lines: List[str] = []
        try:
            self.proc = subprocess.Popen(self.args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL, creationflags=_CREATE_NO_WINDOW)
        except Exception as e:  # pragma: no cover
            self.on_done(False, f"Could not start FFmpeg: {e}")
            return

        def read_err() -> None:
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                err_lines.append(line.decode("utf-8", "replace").rstrip())

        t = threading.Thread(target=read_err, daemon=True)
        t.start()
        assert self.proc.stdout
        speed = ""
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("speed="):
                speed = line[6:]
            elif line.startswith("frame="):
                try:
                    f = int(line[6:])
                    self.on_progress(min(1.0, f / self.total), speed)
                except ValueError:
                    pass
        rc = self.proc.wait()
        t.join(timeout=2)
        if self.cancelled:
            self.on_done(False, "Export cancelled")
        elif rc != 0:
            self.on_done(False, "\n".join(err_lines[-15:]) or f"FFmpeg failed (exit code {rc})")
        else:
            self.on_progress(1.0, speed)
            self.on_done(True, "")
