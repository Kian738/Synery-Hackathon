"""Fast, robust ingestion and spatial indexing of building models and assets."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Union
from collections import defaultdict

from shapely.geometry import MultiPolygon, Polygon
from shapely.validation import make_valid

from .models import (
    Asset,
    AssetFootprint,
    Building,
    BuildingMetadata,
    Connector,
    Floor,
    Opening,
    Space,
)


def load_equipment_csv(csv_path: Union[str, Path]) -> list[Asset]:
    """Load assets from equipment.csv if available."""
    path = Path(csv_path)
    if not path.is_file():
        return []

    assets: list[Asset] = []
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asset_id = row.get("asset_id", "")
            if not asset_id:
                continue

            x = float(row.get("x_m", 0.0))
            y = float(row.get("y_m", 0.0))

            footprint = None
            if "width_m" in row and "depth_m" in row:
                try:
                    w = float(row["width_m"])
                    d = float(row["depth_m"])
                    rot = float(row.get("rotation_deg", 0.0))
                    footprint = AssetFootprint(width_m=w, depth_m=d, rotation_deg=rot)
                except (ValueError, TypeError):
                    footprint = None

            asset = Asset(
                id=asset_id,
                name=row.get("name", ""),
                category=row.get("category", ""),
                type=row.get("type", ""),
                space_id=row.get("space_id", ""),
                floor_id=row.get("floor_id", ""),  # May be resolved later
                position=(x, y),
                footprint=footprint,
                source=row.get("source"),
            )
            assets.append(asset)

    return assets


def load_building(path: Union[str, Path]) -> Building:
    """Load a building from building.json (or directory containing it) and index it.

    Args:
        path: Directory containing building.json or path directly to building.json.

    Returns:
        Fully initialized Building instance with pre-computed Shapely polygons
        and fast indices.
    """
    p = Path(path)
    if p.is_dir():
        building_json_path = p / "building.json"
        equipment_csv_path = p / "equipment.csv"
    else:
        building_json_path = p
        equipment_csv_path = p.parent / "equipment.csv"

    if not building_json_path.exists():
        raise FileNotFoundError(f"building.json not found at {building_json_path}")

    with open(building_json_path, mode="r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    # 1. Parse Metadata
    meta_dict = data.get("building", {})
    metadata = BuildingMetadata(
        id=str(meta_dict.get("id", p.name)),
        name=str(meta_dict.get("name", "")),
        source=str(meta_dict.get("source", "")),
        source_ref=meta_dict.get("source_ref", {}),
        license=meta_dict.get("license"),
        attribution=meta_dict.get("attribution"),
        split=meta_dict.get("split"),
        units=meta_dict.get("units", "m"),
    )

    # 2. Parse Floors
    floors: dict[str, Floor] = {}
    floors_by_level: dict[int, Floor] = {}
    for raw_floor in data.get("floors", []):
        floor_id = str(raw_floor["id"])
        level = int(raw_floor["level"])
        raw_elev = raw_floor.get("elevation_m")
        raw_height = raw_floor.get("height_m")
        height = float(raw_height) if raw_height is not None else 3.0
        elevation = float(raw_elev) if raw_elev is not None else float(level) * height
        floor = Floor(
            id=floor_id,
            level=level,
            name=str(raw_floor.get("name", f"Level {level}")),
            elevation_m=elevation,
            height_m=height,
        )
        floors[floor_id] = floor
        floors_by_level[level] = floor

    # 3. Parse Spaces
    spaces: dict[str, Space] = {}
    spaces_by_floor: dict[str, list[Space]] = defaultdict(list)
    spaces_by_floor_and_room_type: dict[tuple[str, str], list[Space]] = defaultdict(list)

    for raw_space in data.get("spaces", []):
        space_id = str(raw_space["id"])
        floor_id = str(raw_space["floor_id"])
        stype = str(raw_space.get("type", "room"))
        room_type = str(raw_space.get("room_type", stype))
        name = str(raw_space.get("name", space_id))
        ref = str(raw_space.get("ref", ""))

        raw_poly = raw_space.get("polygon", [])
        coords = [(float(pt[0]), float(pt[1])) for pt in raw_poly]

        if len(coords) < 3:
            # Fallback for degenerate spaces
            coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

        poly = Polygon(coords)
        if not poly.is_valid:
            poly = make_valid(poly)

        if isinstance(poly, MultiPolygon):
            polys = [g for g in poly.geoms if isinstance(g, Polygon) and not g.is_empty]
            poly = max(polys, key=lambda g: g.area) if polys else Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
        elif hasattr(poly, "geoms"):  # GeometryCollection, MultiLineString, etc.
            polys = [g for g in poly.geoms if isinstance(g, Polygon) and not g.is_empty]
            poly = max(polys, key=lambda g: g.area) if polys else Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
        elif not isinstance(poly, Polygon) or poly.is_empty:
            poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])

        area = float(poly.area)
        centroid = (float(poly.centroid.x), float(poly.centroid.y))
        rep_pt = poly.representative_point()
        rep_point = (float(rep_pt.x), float(rep_pt.y))
        exterior_ring = poly.exterior

        space = Space(
            id=space_id,
            floor_id=floor_id,
            type=stype,
            room_type=room_type,
            name=name,
            ref=ref,
            polygon_coords=coords,
            polygon=poly,
            area=area,
            centroid=centroid,
            representative_point=rep_point,
            exterior_ring=exterior_ring,
            synthetic=bool(raw_space.get("synthetic", False)),
        )
        spaces[space_id] = space
        spaces_by_floor[floor_id].append(space)
        spaces_by_floor_and_room_type[(floor_id, room_type)].append(space)

    # 4. Parse Openings
    openings: dict[str, Opening] = {}
    openings_by_space: dict[str, list[Opening]] = defaultdict(list)
    openings_by_floor: dict[str, list[Opening]] = defaultdict(list)

    for raw_op in data.get("openings", []):
        opening_id = str(raw_op["id"])
        floor_id = str(raw_op.get("floor_id", ""))
        pos = raw_op.get("position", [0.0, 0.0])
        position = (float(pos[0]), float(pos[1]))
        space_ids = [str(sid) for sid in raw_op.get("space_ids", [])]

        opening = Opening(
            id=opening_id,
            floor_id=floor_id,
            space_ids=space_ids,
            kind=str(raw_op.get("kind", "door")),
            position=position,
            width_m=float(raw_op.get("width_m", 0.9)),
            step_free=bool(raw_op.get("step_free", True)),
            synthetic=bool(raw_op.get("synthetic", False)),
        )
        openings[opening_id] = opening
        openings_by_floor[floor_id].append(opening)
        for sid in space_ids:
            if sid != "outside":
                openings_by_space[sid].append(opening)

    # 5. Parse Connectors
    connectors: dict[str, Connector] = {}
    connectors_by_floor: dict[str, list[Connector]] = defaultdict(list)

    for raw_conn in data.get("vertical_connectors", []):
        conn_id = str(raw_conn["id"])
        floor_ids = [str(fid) for fid in raw_conn.get("floor_ids", [])]
        space_ids = [str(sid) for sid in raw_conn.get("space_ids", [])]

        connector = Connector(
            id=conn_id,
            kind=str(raw_conn.get("kind", "stairs")),
            name=str(raw_conn.get("name", conn_id)),
            floor_ids=floor_ids,
            space_ids=space_ids,
            step_free=bool(raw_conn.get("step_free", False)),
            synthetic=bool(raw_conn.get("synthetic", False)),
        )
        connectors[conn_id] = connector
        for fid in floor_ids:
            connectors_by_floor[fid].append(connector)

    # 6. Parse Assets
    assets: dict[str, Asset] = {}
    assets_by_space: dict[str, list[Asset]] = defaultdict(list)
    assets_by_type: dict[str, list[Asset]] = defaultdict(list)

    raw_assets = data.get("assets", [])
    if not raw_assets and equipment_csv_path.is_file():
        loaded_assets = load_equipment_csv(equipment_csv_path)
        for a in loaded_assets:
            if not a.floor_id and a.space_id in spaces:
                a.floor_id = spaces[a.space_id].floor_id
            assets[a.id] = a
    else:
        for raw_a in raw_assets:
            asset_id = str(raw_a["id"])
            pos = raw_a.get("position", [0.0, 0.0])
            position = (float(pos[0]), float(pos[1]))
            space_id = str(raw_a.get("space_id", ""))
            floor_id = str(raw_a.get("floor_id", ""))
            if not floor_id and space_id in spaces:
                floor_id = spaces[space_id].floor_id

            footprint = None
            if "footprint" in raw_a and isinstance(raw_a["footprint"], dict):
                fp = raw_a["footprint"]
                footprint = AssetFootprint(
                    width_m=float(fp.get("width_m", 1.0)),
                    depth_m=float(fp.get("depth_m", 1.0)),
                    rotation_deg=float(fp.get("rotation_deg", 0.0)),
                )

            asset = Asset(
                id=asset_id,
                name=str(raw_a.get("name", asset_id)),
                category=str(raw_a.get("category", "")),
                type=str(raw_a.get("type", "")),
                space_id=space_id,
                floor_id=floor_id,
                position=position,
                footprint=footprint,
                source=raw_a.get("source"),
            )
            assets[asset_id] = asset

    for a in assets.values():
        if a.space_id:
            assets_by_space[a.space_id].append(a)
        if a.type:
            assets_by_type[a.type].append(a)

    return Building(
        metadata=metadata,
        floors=floors,
        spaces=spaces,
        openings=openings,
        connectors=connectors,
        assets=assets,
        floors_by_level=floors_by_level,
        spaces_by_floor=dict(spaces_by_floor),
        spaces_by_floor_and_room_type=dict(spaces_by_floor_and_room_type),
        openings_by_space=dict(openings_by_space),
        openings_by_floor=dict(openings_by_floor),
        connectors_by_floor=dict(connectors_by_floor),
        assets_by_space=dict(assets_by_space),
        assets_by_type=dict(assets_by_type),
    )
