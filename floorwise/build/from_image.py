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
    # Integer colour histograms avoid sorting millions of structured RGB rows.
    # This is exactly the same colour/count calculation, not quantization.
    flat = image.reshape(-1, 3).astype(np.uint32)
    packed = (flat[:,0] << 16) | (flat[:,1] << 8) | flat[:,2]
    values, counts = np.unique(packed, return_counts=True)
    colours = np.column_stack(((values>>16)&255,(values>>8)&255,values&255))
    share = counts / len(packed)
    result = []
    # Dominant fills must claim pixels before anti-aliased shades of the same fill.
    for index in np.argsort(-counts):
        colour, part = colours[index], share[index]
        r, g, b = (int(v) for v in colour)
        if part < MIN_FILL_SHARE or (r > 250 and g > 250 and b > 250):
            continue
        if 0.299 * r + 0.587 * g + 0.114 * b < 140:  # walls, text
            continue
        result.append((r, g, b))
    return result


def feature_area(image: np.ndarray) -> float:
    """Estimate drawn feature scale from compact uniform marker interiors."""
    lum=_luminance(image);sat=image.max(2)-image.min(2)
    mask=(((sat>60)&(lum>50)&(lum<140))|((sat<12)&(lum>130)&(lum<185))).astype(np.uint8)
    n,components,stats,_=cv2.connectedComponentsWithStats(mask,connectivity=8)
    areas=[];limit=max(16,min(image.shape[:2])*.08)
    for i in range(1,n):
        x,y,w,h,area=map(int,stats[i])
        if area<4 or max(w,h)>limit or area/(w*h)<.6 or not .5<=w/h<=2:continue
        pixels=image[y:y+h,x:x+w][components[y:y+h,x:x+w]==i]
        _,counts=np.unique(pixels//8,axis=0,return_counts=True)
        if max(counts)/area>=.7:areas.append(area)
    return float(np.median(areas)) if areas else 21.


def scan(image_path: Path | str) -> FloorScan:
    image = np.array(Image.open(image_path).convert("RGB")).astype(np.int16)
    height, width = image.shape[:2]
    minimum_region=max(24,int(round(feature_area(image)*3)))
    label_map = np.full((height, width), -1, dtype=np.int32)
    regions: list[Region] = []
    for colour in fill_colours(image.astype(np.uint8)):
        mask = (np.abs(image - np.array(colour)).max(axis=2) <= COLOUR_TOLERANCE).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        for component in range(1, count):
            if stats[component, cv2.CC_STAT_AREA] < minimum_region:
                continue
            # Work in the component's bounding box, with enough margin for the
            # morphology kernels. Full-image copies per room made large plans
            # needlessly quadratic in pixel count times room count.
            sx, sy, sw, sh = map(int, stats[component, :4])
            x0, y0 = max(0, sx-6), max(0, sy-6)
            x1, y1 = min(width, sx+sw+6), min(height, sy+sh+6)
            region_mask = (labels[y0:y1, x0:x1] == component).astype(np.uint8)
            # Close text holes and grow to the wall centre line (walls are ~1-2 px).
            closed = cv2.morphologyEx(region_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            grown = cv2.dilate(closed, np.ones((3, 3), np.uint8), iterations=1)
            contours, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(x0,y0))
            contour = max(contours, key=cv2.contourArea)
            approx = cv2.approxPolyDP(contour, 1.5, True).reshape(-1, 2)
            if len(approx) < 3:
                continue
            # A nearby fill shade can recover the same room again. Previously the
            # duplicate polygon was appended even when it owned almost no pixels,
            # and its label stole a door from the real room.
            owned = closed.astype(bool)
            claimed = label_map[y0:y1, x0:x1]
            fresh = owned & (claimed < 0)
            if np.count_nonzero(fresh) < .65 * np.count_nonzero(owned):
                continue
            index = len(regions)
            claimed[fresh] = index
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
    brown = (saturation > 60) & (luminance > 50) & (luminance < 140) & ~red
    grey = (saturation < 12) & (luminance > 130) & (luminance < 185)
    blobs = []
    for kind, mask in (("entrance", red), ("door", brown | grey)):
        mask = (mask & (label_map < 0)).astype(np.uint8) if kind == "door" else mask.astype(np.uint8)
        count, components, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for component in range(1, count):
            x, y, w, h, area = map(int, stats[component])
            if area < 3 or not .45 <= w / max(h, 1) <= 2.2:
                continue
            local = components[y:y+h, x:x+w] == component
            pixels = image[y:y+h, x:x+w][local]
            _, frequencies = np.unique(pixels // 8, axis=0, return_counts=True)
            uniform = float(max(frequencies) / area)
            solidity = area / (w*h)
            # Anti-aliased text and wall edges also cross the grey range. A real
            # marker has a compact, substantially uniform coloured interior.
            if uniform < .6 or solidity < .5:
                continue
            blobs.append((kind, centroids[component], area, w, h, uniform))
    diameters = [np.sqrt(area / .84) for kind, _, area, w, h, _ in blobs
                 if kind == 'door' and 3 <= area <= max(144, (min(image.shape[:2])*.08)**2) and max(w,h) <= max(16,min(image.shape[:2])*.08)]
    diameter = float(np.median(diameters)) if diameters else 5.
    diameter = max(2., min(diameter, min(image.shape[:2])*.05))
    radius = max(3, int(np.ceil(diameter * 1.8)))
    height, width = label_map.shape

    def ray(x, y, dx, dy, sign):
        for distance in range(max(1,int(diameter*.3)),radius+1):
            xx, yy = int(round(x+dx*distance*sign)),int(round(y+dy*distance*sign))
            if 0 <= xx < width and 0 <= yy < height and label_map[yy,xx]>=0:
                return int(label_map[yy,xx]), distance
        return None

    candidates = []
    for kind, centre, area, w, h, uniform in sorted(blobs,key=lambda item:-item[2]):
        if kind == 'door' and not (max(3,diameter**2*.30) <= area <= diameter**2*5 and max(w,h)<=diameter*3):
            continue
        if kind == 'entrance' and area < max(6,diameter**2*.25):
            continue
        x,y=map(float,centre)
        pairs=[]
        for angle in np.linspace(0,np.pi,24,endpoint=False):
            a=ray(x,y,np.cos(angle),np.sin(angle),1)
            other=ray(x,y,np.cos(angle),np.sin(angle),-1)
            if a and other and a[0]!=other[0]:
                pairs.append((a[1]+other[1],abs(a[1]-other[1]),[a[0],other[0]]))
        if kind=='door':
            if not pairs:continue
            regions=min(pairs,key=lambda pair:pair[:2])[2]
        else:
            rr=radius+4;xx,yy=round(x),round(y)
            window=label_map[max(0,yy-rr):yy+rr+1,max(0,xx-rr):xx+rr+1]
            values,counts=np.unique(window[window>=0],return_counts=True)
            if not len(values):continue
            # Require visible background near an entrance rather than treating
            # any interior red decoration as an exit.
            pixels=image[max(0,yy-rr):yy+rr+1,max(0,xx-rr):xx+rr+1]
            if not np.any((pixels.min(axis=2)>245)&(window<0)):continue
            regions=[int(values[np.argmax(counts)])]
        if any(m.kind==kind and set(m.regions)==set(regions) and
               np.linalg.norm(np.array(m.centre_px)-centre)<diameter*.9 for m in candidates):
            continue
        candidates.append(Marker(kind,(x,y),regions))
    return candidates


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
