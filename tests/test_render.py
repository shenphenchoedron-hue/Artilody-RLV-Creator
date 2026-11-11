"""End-to-end tests: frame-accurate rendering and real GoPro GPS extraction."""

import os
import re
import subprocess
import urllib.request

import pytest

from rlvcreator import exporters
from rlvcreator.ffmpeg import ExportSettings, build_command, find_ffmpeg
from rlvcreator.project import FPS, Project

FFMPEG = find_ffmpeg()
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg not available")

SAMPLE_URL = "https://raw.githubusercontent.com/gopro/gpmf-parser/main/samples/{}"


def _make_chapter(path, seconds, rate, base):
    # every 30 fps frame gets a unique grey level so we can identify it after encoding
    idx = "N" if rate == 30 else f"floor(N*30/{rate})"
    lum = f"16+mod({idx}+{base}\\,25)*8"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"color=black:s=320x240:r={rate}:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-vf", f"geq=lum='{lum}':cb=128:cr=128", "-c:v", "libx264", "-qp", "0",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


def _frame_levels(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-vf",
                        "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    vals = [float(v) for v in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", r.stdout + r.stderr)]
    return [int(round((v - 16) / 8)) % 25 for v in vals]


@needs_ffmpeg
@pytest.mark.parametrize("audio,encoder", [(False, "libx264"), (True, "libx264"), (False, "libx265")])
def test_frame_accurate_render(tmp_path, audio, encoder):
    a = tmp_path / "GH010001.MP4"
    b = tmp_path / "GH020001.MP4"
    _make_chapter(a, 4, 30, 0)
    _make_chapter(b, 3, 60, 120)  # second chapter at 60 fps, continues the numbering
    p = Project()
    p.load_videos([str(b), str(a)])  # order is fixed by GoPro chapter naming
    assert [os.path.basename(c.path) for c in p.chapters] == ["GH010001.MP4", "GH020001.MP4"]
    assert p.source_frames == 210
    p.edit.cut(10, 25)  # inside chapter 1
    p.edit.cut(90, 130)  # across the chapter boundary
    p.edit.cut(p.edit.output_frames - 7, p.edit.output_frames)  # trim the end
    expected = [p.edit.out_to_src(k) % 25 for k in range(p.output_frames)]

    out = tmp_path / "out.mp4"
    st = ExportSettings(encoder=encoder, preset="ultrafast", quality=90, width=320, height=180, audio=audio,
                        title="Mein Weg ä")
    args, total = build_command(FFMPEG, p, str(out), st)
    assert total == p.output_frames
    subprocess.run(args, check=True, capture_output=True)
    got = _frame_levels(out)
    assert len(got) == total
    assert got == expected

    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    if encoder == "libx264":
        assert "h264" in probe and "avc1" in probe and "mp42" in probe
    else:
        assert "hevc" in probe and "hvc1" in probe
    assert "Mein Weg ä" in probe
    assert "30 fps" in probe and "yuv420p(tv, bt709, progressive)" in probe
    assert ("Audio:" in probe) == audio


@needs_ffmpeg
def test_fragmented_mp4_duration(tmp_path):
    """Many downloaded/stock MP4 files are fragmented (moof boxes); length must still be read."""
    from rlvcreator.mp4 import parse_movie

    src = tmp_path / "frag.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=30000/1001:d=5",
                    "-c:v", "libx264", "-g", "30", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                    str(src)], check=True)
    m = parse_movie(str(src))
    assert m.video_duration == pytest.approx(5.0, abs=0.05)
    assert m.video_track.sample_count == 150
    p = Project()
    p.load_videos([str(src)])
    assert p.source_frames == 150
    p.edit.cut(30, 60)
    out = tmp_path / "out.mp4"
    args, total = build_command(FFMPEG, p, str(out), ExportSettings(preset="ultrafast", width=320, height=180))
    subprocess.run(args, check=True, capture_output=True)
    assert total == 120 and len(_frame_count(out)) == 120


def _frame_count(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-vf", "showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    return re.findall(r" n:\s*\d+\s+pts:", r.stderr)


@pytest.fixture(scope="module")
def gopro_sample(tmp_path_factory):
    path = os.environ.get("RLV_GOPRO_SAMPLE")
    if path and os.path.exists(path):
        return path
    dest = tmp_path_factory.mktemp("gopro") / "hero6.mp4"
    try:
        urllib.request.urlretrieve(SAMPLE_URL.format("hero6.mp4"), dest)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"GoPro sample not available: {e}")
    return str(dest)


def test_real_gopro_gps(gopro_sample, tmp_path):
    p = Project()
    p.load_videos([gopro_sample])
    assert p.has_gps
    assert len(p.raw_gps) > 300
    first = p.raw_gps[0]
    assert first.lat == pytest.approx(33.126515, abs=1e-5)
    assert first.lon == pytest.approx(-117.3271676, abs=1e-5)

    n_before = len(p.output_points())
    p.edit.cut(5 * FPS, 10 * FPS)  # remove 5 seconds
    pts = p.output_points()
    assert len(pts) == n_before - 5
    # point 5 of the edited film is the GPS position of second 10 of the recording
    lat, lon, _e, _s = p.track.at(10.0)
    assert (pts[5].lat, pts[5].lon) == pytest.approx((lat, lon))

    gpx = tmp_path / "r.gpx"
    xml = tmp_path / "r.xml"
    exporters.write_gpx(p, str(gpx))
    exporters.write_xml(p, str(xml), "r.mp4", "r.gpx")
    back = exporters.read_gpx_points(str(gpx))
    assert len(back) == len(pts)
    meta = open(xml, encoding="utf-8").read()
    assert f"<end-frame>{p.output_frames}</end-frame>" in meta
    assert "<framerate>30.0</framerate>" in meta


def test_project_save_load(gopro_sample, tmp_path):
    p = Project()
    p.load_videos([gopro_sample])
    p.edit.cut(30, 90)
    p.title, p.country = "Test", "DK"
    f = tmp_path / "x.rlvproj"
    p.save(str(f))
    q = Project.load(str(f))
    assert q.edit.segments == p.edit.segments
    assert q.title == "Test" and q.country == "DK" and q.route_id == p.route_id
