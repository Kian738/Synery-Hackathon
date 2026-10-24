"""Level 4: rebuild a floor from a plan image (rooms, doors, entrances) into the building.json format.

Geometry is recovered deterministically (computer vision on the flat-colour plan): every room is a
connected region of one fill colour, doors are small dots sitting on the wall between two regions,
entrances are red markers. Names and room types come from Claude vision with numbered marks on the
image (set-of-mark prompting), or from a colour -> type table learned from the training plans.

A plan image carries no absolute scale, so the caller passes metres_per_pixel (e.g. from one known
dimension: "the building is 55 m wide")."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

MIN_FILL_SHARE = 0.0004  # a colour covering less of the image is not a room fill
MIN_REGION_PX = 120
COLOUR_TOLERANCE = 7
DOOR_SEARCH_PX = 7


@dataclass
class Region:
    index: int
    colour: tuple[int, int, int]
    polygon_px: list[tuple[float, float]]
    area_px: float
    centre_px: tuple[float, float]


@dataclass
class Marker:
    kind: str  # door | entrance
    centre_px: tuple[float, float]
    regions: list[int] = field(default_factory=list)


@dataclass
class FloorScan:
    width: int
    height: int
    regions: list[Region]
    markers: list[Marker]
    label_map: np.ndarray


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def fill_colours(image: np.ndarray) -> list[tuple[int, int, int]]:
    flat = image.reshape(-1, 3)
    colours, counts = np.unique(flat, axis=0, return_counts=True)
    share = counts / flat.shape[0]
    result = []
    for colour, part in zip(colours, share):
        r, g, b = (int(v) for v in colour)
        if part < MIN_FILL_SHARE or (r > 250 and g > 250 and b > 250):
            continue
        if 0.299 * r + 0.587 * g + 0.114 * b < 140:  # walls, text
            continue
        result.append((r, g, b))
    return result


def scan(image_path: Path | str) -> FloorScan:
    image = np.array(Image.open(image_path).convert("RGB")).astype(np.int16)
    height, width = image.shape[:2]
    label_map = np.full((height, width), -1, dtype=np.int32)
    regions: list[Region] = []
    for colour in fill_colours(image.astype(np.uint8)):
        mask = (np.abs(image - np.array(colour)).max(axis=2) <= COLOUR_TOLERANCE).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        for component in range(1, count):
            if stats[component, cv2.CC_STAT_AREA] < MIN_REGION_PX:
                continue
            region_mask = (labels == component).astype(np.uint8)
            # Close text holes and grow to the wall centre line (walls are ~1-2 px).
            closed = cv2.morphologyEx(region_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            grown = cv2.dilate(closed, np.ones((3, 3), np.uint8), iterations=1)
            contours, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour = max(contours, key=cv2.contourArea)
            approx = cv2.approxPolyDP(contour, 1.5, True).reshape(-1, 2)
            if len(approx) < 3:
                continue
            index = len(regions)
            label_map[closed.astype(bool) & (label_map < 0)] = index
            moments = cv2.moments(contour)
            centre = (moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]) if moments["m00"] else tuple(approx[0])
            regions.append(Region(index, colour, [(float(x), float(y)) for x, y in approx], float(cv2.contourArea(contour)), centre))
    markers = _markers(image, label_map)
    return FloorScan(width, height, regions, markers, label_map)


def _markers(image: np.ndarray, label_map: np.ndarray) -> list[Marker]:
    r, g, b = image[..., 0], image[..., 1], image[..., 2]
    luminance = _luminance(image)
    saturation = image.max(axis=2) - image.min(axis=2)
    red = (r > 170) & (g < 100) & (b < 100)
    # Door dots: brown (saturated, mid luminance) or mid grey; not fills (label_map), not walls/text (dark).
    brown = (saturation > 60) & (luminance > 50) & (luminance < 140) & ~red
    grey = (saturation < 12) & (luminance > 130) & (luminance < 185)
    candidates = []
    for kind, mask in (("entrance", red), ("door", brown | grey)):
        mask = (mask & (label_map < 0)).astype(np.uint8) if kind == "door" else mask.astype(np.uint8)
        count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for component in range(1, count):
            area = stats[component, cv2.CC_STAT_AREA]
            w, h = stats[component, cv2.CC_STAT_WIDTH], stats[component, cv2.CC_STAT_HEIGHT]
            if kind == "door" and not (4 <= area <= 90 and max(w, h) <= 12 and 0.5 <= w / max(h, 1) <= 2):
                continue
            if kind == "entrance" and area < 12:
                continue
            candidates.append(Marker(kind, (float(centroids[component][0]), float(centroids[component][1]))))
    for marker in candidates:
        x, y = int(round(marker.centre_px[0])), int(round(marker.centre_px[1]))
        radius = DOOR_SEARCH_PX + (4 if marker.kind == "entrance" else 0)
        window = label_map[max(0, y - radius): y + radius + 1, max(0, x - radius): x + radius + 1]
        values, counts = np.unique(window[window >= 0], return_counts=True)
        order = np.argsort(-counts)
        marker.regions = [int(values[i]) for i in order[:2]]
    return [m for m in candidates if (m.kind == "door" and len(m.regions) == 2) or (m.kind == "entrance" and m.regions)]


# ---------- building.json ----------

def to_building(scans: list[tuple[int, FloorScan]], metres_per_pixel: float, building_id: str = "built",
                name: str = "New building", labels: dict | None = None, floor_height_m: float = 3.5) -> dict:
    """scans: [(level, FloorScan)]. labels: {(level, region index): {"name", "ref", "type", "room_type"}}."""
    labels = labels or {}
    building = {
        "building": {"id": building_id, "name": name, "source": "built_from_plan", "units": "m", "split": "custom"},
        "floors": [], "spaces": [], "openings": [], "vertical_connectors": [], "assets": [],
    }
    for level, floor_scan in scans:
        floor_id = f"{building_id}-F{level}"
        building["floors"].append({"id": floor_id, "level": level, "name": "Ground floor" if level == 0 else
                                   (f"Floor {level}" if level > 0 else f"Basement {-level}"),
                                   "elevation_m": level * floor_height_m, "height_m": floor_height_m})

        def to_m(point):
            return [round(point[0] * metres_per_pixel, 3), round((floor_scan.height - point[1]) * metres_per_pixel, 3)]

        ids = {}
        for region in floor_scan.regions:
            space_id = f"{floor_id}-S{region.index:03d}"
            ids[region.index] = space_id
            label = labels.get((level, region.index), {})
            ref = label.get("ref") or f"{level}.{region.index:02d}"
            room_type = label.get("room_type") or "generic_room"
            building["spaces"].append({
                "id": space_id, "floor_id": floor_id, "type": label.get("type") or "room", "room_type": room_type,
                "name": label.get("name") or f"{room_type.replace('_', ' ').capitalize()} {ref}", "ref": ref,
                "polygon": [to_m(p) for p in region.polygon_px], "synthetic": True,
            })
        for number, marker in enumerate(floor_scan.markers):
            space_ids = [ids[r] for r in marker.regions]
            if marker.kind == "entrance":
                space_ids = [space_ids[0], "outside"]
            building["openings"].append({
                "id": f"{floor_id}-O{number:04d}", "floor_id": floor_id, "space_ids": space_ids,
                "kind": "entrance" if marker.kind == "entrance" else "door", "position": to_m(marker.centre_px),
                "width_m": 0.9, "step_free": True, "synthetic": True,
            })
    return building


def save(building: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "building.json"
    path.write_text(json.dumps(building, indent=1, ensure_ascii=False), encoding="utf-8")
    return path
