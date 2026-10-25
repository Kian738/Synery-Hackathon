"""Isometric thumbnails of buildings for the Building Atlas: every floor outline stacked, floor colours as in the app.

Deterministic (same building file, same SVG) and cached on disk next to the walk cache."""

import hashlib
import math
from pathlib import Path

from shapely import make_valid
from shapely.geometry import Polygon
from shapely.ops import unary_union

from floorwise.core.model import Building
from floorwise.paths import ROOT

# lib/floorColors.ts (keep in step)
HUES = ["#6ea8ff", "#4fd1c5", "#8fdc7a", "#c9a0ff", "#ff9f7a", "#f070a8", "#7fd0ff", "#b5d65c"]
WIDTH, HEIGHT = 240.0, 150.0
CACHE = ROOT / "runs" / ".thumb-cache"


def floor_colour(level: int) -> str:
    return HUES[level % len(HUES)]


def _outline(building: Building, floor_id: str):
    polygons = [make_valid(Polygon(s["polygon"])) for s in building.spaces.values()
                if s["floor_id"] == floor_id and len(s["polygon"]) >= 3 and s.get("type") != "outdoor"]
    if not polygons:
        return None
    shape = unary_union(polygons).buffer(0.4).buffer(-0.4)
    return shape.simplify(0.35)


def thumbnail_svg(building: Building) -> str:
    floors = sorted(building.floors.values(), key=lambda f: f["level"])
    shapes = [(f, _outline(building, f["id"])) for f in floors]
    shapes = [(f, s) for f, s in shapes if s is not None and not s.is_empty]
    if not shapes:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH:g} {HEIGHT:g}"><rect width="100%" height="100%" fill="#152128"/></svg>'
    cos, sin = math.cos(math.radians(30)), math.sin(math.radians(30))
    # footprint size sets the scale; floors are spread a fixed fraction of the building width apart so tall stacks stay readable
    minx = min(s.bounds[0] for _, s in shapes); maxx = max(s.bounds[2] for _, s in shapes)
    miny = min(s.bounds[1] for _, s in shapes); maxy = max(s.bounds[3] for _, s in shapes)
    span = max(maxx - minx, maxy - miny, 1.0)
    gap = span * 0.22 / max(len(shapes) - 1, 1) * min(len(shapes) - 1, 4) if len(shapes) > 1 else 0

    def project(x: float, y: float, level_index: int):
        u, v = x - minx - span / 2, y - miny - span / 2
        return ((u - v) * cos, (u + v) * sin * 0.62 - level_index * gap)

    raw = []
    for index, (floor, shape) in enumerate(shapes):
        parts = list(shape.geoms) if hasattr(shape, "geoms") else [shape]
        raw.append((floor, [[project(x, y, index) for x, y in part.exterior.coords] for part in parts if not part.is_empty]))
    xs = [p[0] for _, rings in raw for ring in rings for p in ring]
    ys = [p[1] for _, rings in raw for ring in rings for p in ring]
    scale = min((WIDTH - 24) / max(max(xs) - min(xs), 1e-6), (HEIGHT - 24) / max(max(ys) - min(ys), 1e-6))
    ox, oy = (WIDTH - (max(xs) - min(xs)) * scale) / 2 - min(xs) * scale, (HEIGHT - (max(ys) - min(ys)) * scale) / 2 - min(ys) * scale
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH:g} {HEIGHT:g}" role="img" aria-label="{building.data["building"].get("name", building.id)} floors">',
           f'<rect width="100%" height="100%" fill="#152128"/>']
    for floor, rings in raw:  # lowest floor first, upper floors painted over it
        colour = floor_colour(floor["level"])
        ground = floor["level"] == 0
        for ring in rings:
            points = " ".join(f"{x * scale + ox:.1f},{y * scale + oy:.1f}" for x, y in ring)
            out.append(f'<polygon points="{points}" fill="{colour}" fill-opacity="{0.9 if ground else 0.55}" stroke="#0c1317" stroke-width="0.8" stroke-linejoin="round"/>')
    out.append("</svg>")
    return "".join(out)


def cached_thumbnail(building: Building, directory: Path) -> str:
    source = Path(directory) / "building.json"
    stamp = f"{source.stat().st_size}-{source.stat().st_mtime_ns}" if source.exists() else "none"
    key = hashlib.sha1(f"{building.id}-{stamp}-v1".encode()).hexdigest()[:16]
    path = CACHE / f"{key}.svg"
    if path.exists():
        return path.read_text(encoding="utf-8")
    svg = thumbnail_svg(building)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
    except OSError:
        pass
    return svg
