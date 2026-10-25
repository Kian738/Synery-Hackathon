"""Static geographic anchors, metadata, and 3D footprints for OSM buildings.

All 17 coordinates are verified against OpenStreetMap API way centroids.
Procedural/Swiss Dwellings buildings are excluded as they have no real-world coordinates.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

# building_id -> (lat, lon, zoom_hint, campus_group, default_height_m)
GEOREF: dict[str, tuple[float, float, int, str, float]] = {
    # --- TUM Garching Campus ---
    "osm-way27917482": (
        48.262423,
        11.668203,
        17,
        "garching",
        22.0,  # TUM CIT (Informatik / Mathematik)
    ),
    "osm-way476929995": (
        48.266834,
        11.670111,
        18,
        "garching",
        15.0,  # StudiTUM Garching
    ),

    # --- TUM Main Campus (Munich Stammgelände) ---
    "osm-way10053349": (
        48.148858,
        11.568008,
        18,
        "munich_center",
        24.0,  # Hauptgebäude
    ),
    "osm-way61408163": (
        48.148572,
        11.566122,
        18,
        "munich_center",
        22.0,  # Thierschbau
    ),
    "osm-way50300147": (
        48.148072,
        11.567535,
        18,
        "munich_center",
        18.0,  # Arcisstraße 21
    ),
    "osm-way19183732": (
        48.147319,
        11.567167,
        18,
        "munich_center",
        16.0,  # Mensa Arcisstraße
    ),
    "osm-way50299720": (
        48.149123,
        11.566283,
        18,
        "munich_center",
        19.0,  # Landwirtschaftsbau
    ),
    "osm-way50299584": (
        48.149878,
        11.566947,
        18,
        "munich_center",
        20.0,  # Wirtschaftswissenschaften
    ),
    "osm-way58216509": (
        48.150081,
        11.568273,
        18,
        "munich_center",
        18.0,  # U-Trakt
    ),
    "osm-way22744230": (
        48.151082,
        11.567701,
        18,
        "munich_center",
        25.0,  # N3
    ),
    "osm-way43035346": (
        48.150623,
        11.569514,
        18,
        "munich_center",
        24.0,  # N8
    ),

    # --- TUM Weihenstephan Campus (Freising) ---
    "osm-way27326387": (
        48.395714,
        11.726692,
        18,
        "weihenstephan",
        16.0,  # Institutsgebäude 3
    ),

    # --- Greater Munich Area & Special Facilities ---
    "osm-way360544293": (
        48.354222,
        11.792183,
        17,
        "munich_metro",
        28.0,  # Munich Airport Terminal 2
    ),
    "osm-way363805324": (
        48.137924,
        11.552929,
        18,
        "munich_metro",
        16.0,  # EineWeltHaus
    ),
    "osm-way52060470": (
        48.147858,
        11.463790,
        17,
        "munich_metro",
        22.0,  # Pasing Arcaden
    ),
    "osm-way13507441": (
        48.064977,
        11.665473,
        18,
        "munich_metro",
        15.0,  # Wolf-Ferrari-Haus (Ottobrunn)
    ),
    "osm-way37850565": (
        48.077060,
        11.662449,
        18,
        "munich_metro",
        16.0,  # Haus der Weiterbildung
    ),
}

# Campus quick-fly viewpoints
CAMPUS_VIEWPOINTS = {
    "garching": {
        "id": "garching",
        "label": "TUM Garching (CIT)",
        "coords": [11.668203, 48.262423],
        "zoom": 16.5,
        "pitch": 65,
        "bearing": -20,
    },
    "munich_center": {
        "id": "munich_center",
        "label": "TUM Main Campus",
        "coords": [11.567500, 48.149200],
        "zoom": 16.2,
        "pitch": 65,
        "bearing": 35,
    },
    "weihenstephan": {
        "id": "weihenstephan",
        "label": "TUM Weihenstephan",
        "coords": [11.726692, 48.395714],
        "zoom": 16.5,
        "pitch": 65,
        "bearing": 10,
    },
}


@lru_cache(maxsize=1)
def get_buildings_geojson() -> dict[str, Any]:
    """Generate GeoJSON FeatureCollection of 3D building footprint extrusions."""
    from floorwise.paths import DATA

    features: list[dict[str, Any]] = []
    m_per_deg_lat = 111320.0

    for bid, (anchor_lat, anchor_lon, _zoom, campus, height_m) in GEOREF.items():
        candidates = list(DATA.glob(f"*/{bid}/building.json"))
        if not candidates:
            continue
        try:
            with open(candidates[0], encoding="utf-8") as f:
                d = json.load(f)
            spaces = d.get("spaces", [])
            all_pts = [pt for s in spaces for pt in s.get("polygon", [])]
            if not all_pts:
                continue

            min_x = min(pt[0] for pt in all_pts)
            max_x = max(pt[0] for pt in all_pts)
            min_y = min(pt[1] for pt in all_pts)
            max_y = max(pt[1] for pt in all_pts)

            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0

            m_per_deg_lon = 111320.0 * math.cos(math.radians(anchor_lat))

            corners = [
                (min_x - cx, min_y - cy),
                (max_x - cx, min_y - cy),
                (max_x - cx, max_y - cy),
                (min_x - cx, max_y - cy),
                (min_x - cx, min_y - cy),
            ]
            ring = [
                [
                    round(anchor_lon + dx / m_per_deg_lon, 6),
                    round(anchor_lat + dy / m_per_deg_lat, 6),
                ]
                for dx, dy in corners
            ]

            color_map = {
                "garching": "#00f0ff",
                "munich_center": "#ffd45c",
                "weihenstephan": "#00ff88",
                "munich_metro": "#ff79c6",
            }

            features.append(
                {
                    "type": "Feature",
                    "id": bid,
                    "properties": {
                        "building_id": bid,
                        "name": d.get("building", {}).get("name", bid),
                        "campus": campus,
                        "height": height_m,
                        "floors": len(d.get("floors", [])),
                        "spaces": len(spaces),
                        "color": color_map.get(campus, "#ffd45c"),
                        "lat": anchor_lat,
                        "lon": anchor_lon,
                    },
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                }
            )
        except Exception:
            continue

    return {"type": "FeatureCollection", "features": features}
