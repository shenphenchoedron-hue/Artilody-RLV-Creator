"""Writers for the RLV GPX and XML files (format identical to the reference files)."""

from __future__ import annotations

import datetime as _dt
import html
import html.entities
import re
from typing import Iterable, List, Optional, Sequence

from .project import FPS, GPX_BASE_TIME, Info, OutputPoint, Project

NL = "\r\n"  # the reference files use Windows line endings

GPX_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>' + NL
    + '<gpx version="1.1" creator="GPS Track Editor" xmlns="http://www.topografix.com/GPX/1/1" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns:gte="http://www.gpstrackeditor.com/xmlschemas/General/1" '
    'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" '
    'xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3" '
    'targetNamespace="http://www.topografix.com/GPX/1/1" elementFormDefault="qualified" '
    'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">' + NL
)


def _xml_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_time(ts: float) -> str:
    return _dt.datetime.fromtimestamp(round(ts), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_gpx(points: Sequence[OutputPoint], file_name: str, track_name: str,
              start_times: Optional[Sequence[float]] = None) -> str:
    """Build GPX text. ``start_times`` optionally gives a real UTC time per point."""
    out: List[str] = [GPX_HEADER]
    out.append("<metadata>" + NL)
    out.append(f"\t<name>{_xml_text(file_name)}</name>" + NL)
    out.append("</metadata>" + NL)
    out.append("<trk>" + NL)
    out.append(f"\t<name>{_xml_text(track_name)}</name>" + NL)
    out.append("\t<trkseg>" + NL)
    for k, p in enumerate(points):
        ts = start_times[k] if start_times is not None else GPX_BASE_TIME + p.t
        out.append(f'\t\t<trkpt lat="{p.lat:.6f}" lon="{p.lon:.6f}">' + NL)
        out.append(f"\t\t\t<ele>{p.ele:.2f}</ele>" + NL)
        out.append(f"\t\t\t<time>{_fmt_time(ts)}</time>" + NL)
        out.append("\t\t\t<extensions>" + NL)
        out.append(f'\t\t\t\t<gte:gps speed="{p.speed_kmh:.1f}"/>' + NL)
        if p.hr is not None or p.cad is not None:
            out.append("\t\t\t\t<gpxtpx:TrackPointExtension>" + NL)
            if p.hr is not None:
                out.append(f"\t\t\t\t\t<gpxtpx:hr>{p.hr}</gpxtpx:hr>" + NL)
            if p.cad is not None:
                out.append(f"\t\t\t\t\t<gpxtpx:cad>{p.cad}</gpxtpx:cad>" + NL)
            out.append("\t\t\t\t</gpxtpx:TrackPointExtension>" + NL)
        out.append("\t\t\t</extensions>" + NL)
        out.append("\t\t</trkpt>" + NL)
    out.append("\t\t<extensions>" + NL)
    out.append("\t\t\t<gte:name>#1</gte:name>" + NL)
    out.append("\t\t\t<gte:color>#fbaf00</gte:color>" + NL)
    out.append("\t\t</extensions>" + NL)
    out.append("\t</trkseg>" + NL)
    out.append("</trk>" + NL)
    out.append("</gpx>")
    return "".join(out)


def write_gpx(project: Project, path: str) -> int:
    import os
    pts = project.output_points()
    if not pts:
        raise ValueError("No GPS data available for the edited film")
    times = None
    if project.use_real_time:
        utcs = [project.track.utc_at(project.edit.out_to_src_time(float(p.t), FPS)) for p in pts]
        if all(u is not None for u in utcs):
            times = utcs  # type: ignore[assignment]
    text = build_gpx(pts, os.path.basename(path), project.title or project.name, times)  # type: ignore[arg-type]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return len(pts)


# ---------------------------------------------------------------------- XML

_XML_SAFE = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def encode_entities(s: str) -> str:
    """Encode text like the reference file: XML specials plus HTML named entities for
    non-ASCII characters (e.g. ä -> &auml;, ß -> &szlig;). Real newlines become the
    literal two characters backslash-n used by the RLV player."""
    s = s.replace("\r\n", "\n").replace("\n", "\\n")
    out = []
    for ch in s:
        if ch in _XML_SAFE:
            out.append(_XML_SAFE[ch])
        elif ord(ch) < 128:
            out.append(ch)
        else:
            name = html.entities.codepoint2name.get(ord(ch))
            out.append(f"&{name};" if name else f"&#{ord(ch)};")
    return "".join(out)


def decode_entities(s: str) -> str:
    return html.unescape(s)


def build_xml(name: str, route_id: str, country: str, title: str, video_file: str, gpx_file: str,
              end_frame: int, infos: Iterable[Info], framerate: float = 30.0, start_frame: int = 1) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8" standalone="yes"?>',
        "<gpx-import>",
        f"    <name>{encode_entities(name)}</name>",
        f"    <id>{encode_entities(route_id)}</id>",
        f"    <country>{encode_entities(country)}</country>",
        f"    <title>{encode_entities(title)}</title>",
        f"    <video-file-path>{encode_entities(video_file)}</video-file-path>",
        f"    <gpx-file-path>{encode_entities(gpx_file)}</gpx-file-path>",
        f"    <framerate>{framerate:.1f}</framerate>",
        f"    <start-frame>{start_frame}</start-frame>",
        f"    <end-frame>{end_frame}</end-frame>",
        "    <informations>",
    ]
    for info in sorted(infos, key=lambda i: i.distance):
        lines.append(f'        <information distance="{int(info.distance)}" de="{encode_entities(info.de)}" '
                     f'en="{encode_entities(info.en)}" />')
    lines.append("    </informations>")
    lines.append("</gpx-import>")
    return NL.join(lines)


def write_xml(project: Project, path: str, video_file: str, gpx_file: str) -> None:
    text = build_xml(project.name, project.route_id, project.country, project.title,
                     video_file, gpx_file, project.output_frames, project.infos, float(FPS))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read_xml_metadata(path: str) -> dict:
    """Read a reference-style XML file (tolerates HTML entities)."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()

    def tag(t: str) -> str:
        m = re.search(rf"<{t}>(.*?)</{t}>", raw, re.S)
        return decode_entities(m.group(1).strip()) if m else ""

    infos = []
    for m in re.finditer(r"<information\s+([^>]*?)/?>", raw, re.S):
        attrs = dict((k, v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        try:
            dist = int(float(attrs.get("distance", "0")))
        except ValueError:
            dist = 0
        infos.append(Info(dist, decode_entities(attrs.get("de", "")), decode_entities(attrs.get("en", ""))))
    return {"name": tag("name"), "id": tag("id"), "country": tag("country"), "title": tag("title"),
            "infos": infos}


def read_gpx_points(path: str) -> List[OutputPoint]:
    """Parse a reference-style GPX back into output points (used for testing/import)."""
    import xml.etree.ElementTree as ET
    ns = {"g": "http://www.topografix.com/GPX/1/1", "gte": "http://www.gpstrackeditor.com/xmlschemas/General/1",
          "tpx": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"}
    root = ET.parse(path).getroot()
    pts: List[OutputPoint] = []
    for i, el in enumerate(root.iterfind(".//g:trkpt", ns)):
        ele = el.find("g:ele", ns)
        sp = el.find(".//gte:gps", ns)
        hr = el.find(".//tpx:hr", ns)
        cad = el.find(".//tpx:cad", ns)
        pts.append(OutputPoint(i, float(el.get("lat")), float(el.get("lon")),
                               float(ele.text) if ele is not None else 0.0,
                               float(sp.get("speed")) if sp is not None else 0.0, 0.0,
                               int(hr.text) if hr is not None else None,
                               int(cad.text) if cad is not None else None))
    return pts
