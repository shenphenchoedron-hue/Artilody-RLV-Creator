import os
import struct
import xml.etree.ElementTree as ET

import pytest

from rlvcreator import exporters
from rlvcreator.edit import EditModel
from rlvcreator.gpmf import parse_payload
from rlvcreator.project import GPX_BASE_TIME, Info, OutputPoint, gopro_sort_key
from rlvcreator.sensors import load_sensor_file
from rlvcreator.track import ascent, build_source_track, clean_samples, haversine

DATA = os.path.join(os.path.dirname(__file__), "data")


# ------------------------------------------------------------------ GPMF
def klv(key: bytes, typ: str, size: int, repeat: int, data: bytes) -> bytes:
    raw = key + typ.encode() + bytes([size]) + struct.pack(">H", repeat) + data
    return raw + b"\0" * ((-len(raw)) % 4)


def nest(key: bytes, children: bytes) -> bytes:
    return key + b"\0" + bytes([1]) + struct.pack(">H", len(children)) + children


def test_gps5_payload():
    rows = [(331264969 + i, -1173273542, -20184, 167, 19) for i in range(18)]
    strm = (klv(b"STNM", "c", 1, 4, b"GPS!")
            + klv(b"GPSF", "L", 4, 1, struct.pack(">I", 3))
            + klv(b"GPSU", "U", 16, 1, b"170417173103.000")
            + klv(b"GPSP", "S", 2, 1, struct.pack(">H", 606))
            + klv(b"SCAL", "l", 4, 5, struct.pack(">5i", 10000000, 10000000, 1000, 1000, 100))
            + klv(b"GPS5", "l", 20, len(rows), b"".join(struct.pack(">5i", *r) for r in rows)))
    payload = nest(b"DEVC", nest(b"STRM", strm))
    g5, g9 = parse_payload(payload, 10.0, 1.0)
    assert not g9 and len(g5) == 18
    s = g5[0]
    assert s.t == pytest.approx(10.0)
    assert s.lat == pytest.approx(33.1264969)
    assert s.lon == pytest.approx(-117.3273542)
    assert s.ele == pytest.approx(-20.184)
    assert s.speed2d == pytest.approx(0.167)
    assert s.fix == 3 and s.dop == pytest.approx(6.06)
    assert s.utc == pytest.approx(1492450263.0)
    assert g5[-1].t == pytest.approx(10.0 + 17 / 18)


def test_gps9_payload():
    rows = [(446602170, 54209080, 498130, 4670, 4700, 9000, 43200000 + 100 * i, 150, 3) for i in range(10)]
    strm = (klv(b"SCAL", "l", 4, 9, struct.pack(">9i", 10000000, 10000000, 1000, 1000, 100, 1, 1000, 100, 1))
            + klv(b"TYPE", "c", 1, 9, b"lllllllSS")
            + klv(b"GPS9", "?", 32, len(rows), b"".join(struct.pack(">7i2H", *r) for r in rows)))
    g5, g9 = parse_payload(nest(b"DEVC", nest(b"STRM", strm)), 0.0, 1.0)
    assert len(g9) == 10 and not g5
    s = g9[1]
    assert s.lat == pytest.approx(44.660217) and s.lon == pytest.approx(5.420908)
    assert s.ele == pytest.approx(498.13) and s.speed2d == pytest.approx(4.67)
    assert s.dop == pytest.approx(1.5) and s.fix == 3
    assert s.utc == pytest.approx(946684800 + 9000 * 86400 + 43200.1)


# --------------------------------------------------------------- edit model
def test_edit_cut_undo_redo():
    e = EditModel(source_frames=3000)
    assert e.output_frames == 3000
    assert e.cut(100, 200)
    assert e.segments == [(0, 100), (200, 3000)]
    assert e.output_frames == 2900
    assert e.out_to_src(99) == 99 and e.out_to_src(100) == 200
    assert e.src_to_out(150) is None and e.src_to_out(200) == 100
    # cut spanning a join
    assert e.cut(50, 150)
    assert e.segments == [(0, 50), (250, 3000)]
    assert e.join_points() == [50]
    assert e.removed_source_ranges() == [(50, 250)]
    assert e.undo() and e.segments == [(0, 100), (200, 3000)]
    assert e.undo() and e.segments == [(0, 3000)]
    assert not e.undo()
    assert e.redo() and e.redo() and e.segments == [(0, 50), (250, 3000)]
    # new edit clears redo
    e.undo()
    e.cut(0, 10)
    assert not e.can_redo
    # cannot delete everything
    assert not e.cut(0, e.output_frames)


def test_edit_restore_and_time_mapping():
    e = EditModel(source_frames=900)
    e.cut(300, 600)
    assert e.out_to_src_time(10.0, 30) == pytest.approx(20.0)
    assert e.out_to_src_time(9.5, 30) == pytest.approx(9.5)
    assert e.next_kept_src(400) == 600
    assert e.restore_source_range(300, 600)
    assert e.segments == [(0, 900)]


def test_gopro_sorting():
    files = ["GH020123.MP4", "GH010124.MP4", "GH010123.MP4", "GP010042.MP4", "GOPR0042.MP4", "zzz.mp4"]
    assert sorted(files, key=gopro_sort_key) == ["GOPR0042.MP4", "GP010042.MP4", "GH010123.MP4",
                                                  "GH020123.MP4", "GH010124.MP4", "zzz.mp4"]


# ---------------------------------------------------------------- track
def test_track_resampling_and_cleaning():
    from rlvcreator.gpmf import GpsSample
    samples = [GpsSample(i / 18, 55.0 + i * 1e-6, 12.0, 10.0 + i * 0.01, 5.0, 5.0, 3, 1.0, 1e9 + i / 18)
               for i in range(18 * 20)]
    samples.append(GpsSample(5.01, 10.0, 10.0, 0, 0, 0, 0, 99, None))  # no fix -> dropped
    cleaned = clean_samples(samples)
    assert len(cleaned) == 18 * 20
    tr = build_source_track(cleaned, 20.0)
    lat, lon, ele, spd = tr.at(10.0)
    assert lat == pytest.approx(55.0 + 180 * 1e-6, abs=2e-6)
    assert spd == pytest.approx(5.0)
    assert tr.utc_at(10.0) == pytest.approx(1e9 + 10.0, abs=0.01)


def test_ascent_and_distance():
    assert ascent([0, 1, 2, 1, 3], threshold=0) == pytest.approx(4)
    assert haversine(0, 0, 0, 1) == pytest.approx(111195, rel=1e-3)


# ------------------------------------------------------------- exporters
def test_gpx_identical_to_reference():
    ref = os.path.join(DATA, "reference_excerpt.gpx")
    pts = exporters.read_gpx_points(ref)
    assert len(pts) == 4 and pts[0].hr == 118
    text = exporters.build_gpx(pts, "FR_Le_petit_Menglonnais.gpx", "Menglonnais")
    with open(ref, "rb") as f:
        assert text.encode("utf-8") == f.read()


def test_gpx_without_sensor_data_is_valid():
    pts = [OutputPoint(i, 55.0, 12.0 + i * 1e-4, 10.0, 20.0, 0.0) for i in range(3)]
    text = exporters.build_gpx(pts, "a.gpx", "A & B")
    root = ET.fromstring(text.encode())
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    trkpts = root.findall(".//g:trkpt", ns)
    assert len(trkpts) == 3
    assert trkpts[2].find("g:time", ns).text == "1999-12-31T23:00:02Z"
    assert "<gpxtpx:TrackPointExtension>" not in text
    assert GPX_BASE_TIME == 946681200


def test_xml_matches_reference_structure():
    meta = exporters.read_xml_metadata(os.path.join(DATA, "reference.xml"))
    assert meta["country"] == "FR" and len(meta["infos"]) == 7
    assert meta["infos"][4].de == "Walnußplantagen"
    text = exporters.build_xml(meta["name"], meta["id"], meta["country"], meta["title"],
                               "FR_Le_petit_Menglonnais.mp4", "FR_Le_petit_Menglonnais.gpx", 53490, meta["infos"])
    assert "Walnu&szlig;plantagen" in text and "L&auml;nge" in text
    assert "\r\n" in text

    def norm(s):
        import re
        return [re.sub(r"\s+", " ", l).strip().replace(" />", "/>") for l in s.replace("\r", "").split("\n") if l.strip()]

    with open(os.path.join(DATA, "reference.xml"), encoding="utf-8") as f:
        assert norm(text) == norm(f.read())


def test_xml_newlines_and_escaping():
    text = exporters.build_xml("n", "id", "DK", "T", "n.mp4", "n.gpx", 30,
                               [Info(5, "Zwei\nZeilen", 'Say "hi" & <go>')])
    assert 'de="Zwei\\nZeilen"' in text
    assert 'en="Say &quot;hi&quot; &amp; &lt;go&gt;"' in text


def test_sensor_import(tmp_path):
    gpx = tmp_path / "s.gpx"
    gpx.write_text(
        '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><trkseg>'
        '<trkpt lat="1" lon="1"><time>2020-01-01T10:00:00Z</time><extensions><gpxtpx:TrackPointExtension>'
        '<gpxtpx:hr>120</gpxtpx:hr><gpxtpx:cad>80</gpxtpx:cad></gpxtpx:TrackPointExtension></extensions></trkpt>'
        '<trkpt lat="1" lon="1"><time>2020-01-01T10:00:01Z</time><extensions><gpxtpx:TrackPointExtension>'
        '<gpxtpx:hr>121</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>'
        '</trkseg></trk></gpx>')
    s = load_sensor_file(str(gpx))
    assert s.at(1577872800.2) == (120, 80)
    assert s.at(1577872801.0) == (121, None)
    assert s.at(1577872900.0) == (None, None)
