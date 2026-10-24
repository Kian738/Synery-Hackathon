"""Fast, robust ingestion and spatial indexing of building models and assets."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Union

from shapely.geometry import MultiPolygon, Polygon
from shapely.validation import make_valid

from .models import (
    Asset,
    AssetFootprint,
    Building,
    BuildingMetadata,
    Floor,
    Opening,
    Space,
    VerticalConnector,
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
                type=row.get("type", "").strip().lower().replace(" ", "_"),
                space_id=row.get("space_id", ""),
                floor_id=row.get("floor_id", ""),
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
        and fast spatial indices.
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
        units=str(meta_dict.get("units", "m")),
    )

    # 2. Parse Floors (sorted by level/elevation)
    raw_floors = data.get("floors", [])
    floors: dict[str, Floor] = {}
    floors_by_level: dict[int, Floor] = {}

    # Sort raw floors by level
    sorted_raw_floors = sorted(raw_floors, key=lambda fl: int(fl.get("level", 0)))
    for f_data in sorted_raw_floors:
        fid = str(f_data["id"])
        level = int(f_data.get("level", 0))
        floor = Floor(
            id=fid,
            level=level,
            name=str(f_data.get("name", f"Floor {level}")),
            elevation_m=float(f_data.get("elevation_m", 0.0)),
            height_m=float(f_data.get("height_m", 3.0)),
        )
        floors[fid] = floor
        floors_by_level[level] = floor

    # 3. Parse Spaces & Polygons
    spaces: dict[str, Space] = {}
    spaces_by_floor: dict[str, list[Space]] = defaultdict(list)
    spaces_by_floor_and_room_type: dict[tuple[str, str], list[Space]] = defaultdict(list)

    for s_data in data.get("spaces", []):
        sid = str(s_data["id"])
        fid = str(s_data.get("floor_id", ""))
        raw_coords = s_data.get("polygon", [])
        coords: list[tuple[float, float]] = [(float(pt[0]), float(pt[1])) for pt in raw_coords]

        # Construct and validate Shapely Polygon
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = make_valid(poly)
            if isinstance(poly, MultiPolygon):
                # Take the polygon with the maximum area
                poly = max(poly.geoms, key=lambda g: g.area)

        area = float(poly.area)
        centroid_pt = poly.centroid
        centroid = (float(centroid_pt.x), float(centroid_pt.y))
        rep_pt = poly.representative_point()
        representative_point = (float(rep_pt.x), float(rep_pt.y))
        exterior_ring = poly.exterior

        room_type = str(s_data.get("room_type", "")).strip().lower().replace(" ", "_")

        space = Space(
            id=sid,
            floor_id=fid,
            type=str(s_data.get("type", "room")),
            room_type=room_type,
            name=str(s_data.get("name", "")),
            ref=str(s_data.get("ref", "")),
            polygon_coords=coords,
            polygon=poly,
            area=area,
            centroid=centroid,
            representative_point=representative_point,
            exterior_ring=exterior_ring,
            synthetic=bool(s_data.get("synthetic", False)),
        )
        spaces[sid] = space
        spaces_by_floor[fid].append(space)
        spaces_by_floor_and_room_type[(fid, room_type)].append(space)

    # 4. Parse Openings (doors, entrances)
    openings: dict[str, Opening] = {}
    openings_by_space: dict[str, list[Opening]] = defaultdict(list)
    openings_by_floor: dict[str, list[Opening]] = defaultdict(list)

    for o_data in data.get("openings", []):
        oid = str(o_data["id"])
        fid = str(o_data.get("floor_id", ""))
        pos = o_data.get("position", [0.0, 0.0])
        position = (float(pos[0]), float(pos[1]))
        space_ids = [str(s) for s in o_data.get("space_ids", [])]

        opening = Opening(
            id=oid,
            floor_id=fid,
            space_ids=space_ids,
            kind=str(o_data.get("kind", "door")),
            position=position,
            width_m=float(o_data.get("width_m", 1.0)),
            step_free=bool(o_data.get("step_free", True)),
            synthetic=bool(o_data.get("synthetic", False)),
        )
        openings[oid] = opening
        openings_by_floor[fid].append(opening)
        for sid in space_ids:
            if sid != "outside":
                openings_by_space[sid].append(opening)

    # 5. Parse Vertical Connectors (stairs, lifts)
    connectors: dict[str, VerticalConnector] = {}
    connectors_by_floor: dict[str, list[VerticalConnector]] = defaultdict(list)

    for c_data in data.get("vertical_connectors", []):
        cid = str(c_data["id"])
        floor_ids = [str(f) for f in c_data.get("floor_ids", [])]
        space_ids = [str(s) for s in c_data.get("space_ids", [])]

        connector = VerticalConnector(
            id=cid,
            kind=str(c_data.get("kind", "stairs")),
            name=str(c_data.get("name", "")),
            floor_ids=floor_ids,
            space_ids=space_ids,
            step_free=bool(c_data.get("step_free", False)),
            synthetic=bool(c_data.get("synthetic", False)),
        )
        connectors[cid] = connector
        for fid in floor_ids:
            connectors_by_floor[fid].append(connector)

    # 6. Parse Assets (from building.json and equipment.csv)
    assets: dict[str, Asset] = {}
    assets_by_space: dict[str, list[Asset]] = defaultdict(list)
    assets_by_type: dict[str, list[Asset]] = defaultdict(list)

    # 6a. Assets embedded in building.json
    for a_data in data.get("assets", []):
        aid = str(a_data["id"])
        sid = str(a_data.get("space_id", ""))
        fid = str(a_data.get("floor_id", ""))
        if not fid and sid in spaces:
            fid = spaces[sid].floor_id

        pos = a_data.get("position", [0.0, 0.0])
        position = (float(pos[0]), float(pos[1]))

        footprint = None
        fp_data = a_data.get("footprint")
        if fp_data and isinstance(fp_data, dict):
            try:
                footprint = AssetFootprint(
                    width_m=float(fp_data.get("width_m", 1.0)),
                    depth_m=float(fp_data.get("depth_m", 1.0)),
                    rotation_deg=float(fp_data.get("rotation_deg", 0.0)),
                )
            except (ValueError, TypeError):
                footprint = None

        norm_type = str(a_data.get("type", "")).strip().lower().replace(" ", "_")
        asset = Asset(
            id=aid,
            name=str(a_data.get("name", "")),
            category=str(a_data.get("category", "")),
            type=norm_type,
            space_id=sid,
            floor_id=fid,
            position=position,
            footprint=footprint,
            source=a_data.get("source"),
        )
        assets[aid] = asset
        assets_by_space[sid].append(asset)
        assets_by_type[norm_type].append(asset)

    # 6b. Supplementary assets from equipment.csv if exists
    csv_assets = load_equipment_csv(equipment_csv_path)
    for c_asset in csv_assets:
        if c_asset.id not in assets:
            if not c_asset.floor_id and c_asset.space_id in spaces:
                c_asset.floor_id = spaces[c_asset.space_id].floor_id
            assets[c_asset.id] = c_asset
            assets_by_space[c_asset.space_id].append(c_asset)
            assets_by_type[c_asset.type].append(c_asset)

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
