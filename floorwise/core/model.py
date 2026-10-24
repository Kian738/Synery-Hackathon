"""Typed, cached view of one building.json: the scene graph's nodes (floors, spaces, openings,
connectors, assets) plus the geometry every operator needs (shapely polygons, levels, elevations)."""

import json
from functools import cached_property
from pathlib import Path

from shapely.geometry import Polygon
from shapely.validation import make_valid

OUTSIDE = "outside"
# Space types that are circulation or vertical cores rather than rooms people go to.
CIRCULATION_TYPES = {"corridor", "stair", "lift"}


class Building:
    def __init__(self, data: dict, directory: Path | None = None) -> None:
        self.data = data
        self.directory = directory
        self.info = data["building"]
        self.id: str = self.info["id"]
        self.floors = {floor["id"]: floor for floor in data["floors"]}
        self.spaces = {space["id"]: space for space in data["spaces"]}
        self.openings = {opening["id"]: opening for opening in data["openings"]}
        self.connectors = {connector["id"]: connector for connector in data["vertical_connectors"]}
        self.assets = {asset["id"]: asset for asset in data["assets"]}

    @classmethod
    def load(cls, path: Path | str) -> "Building":
        path = Path(path)
        building_file = path / "building.json" if path.is_dir() else path
        return cls(json.loads(building_file.read_text(encoding="utf-8")), building_file.parent)

    # ---------- floors ----------

    def level(self, floor_id: str) -> int:
        return self.floors[floor_id]["level"]

    def elevation(self, floor_id: str) -> float:
        return float(self.floors[floor_id].get("elevation_m") or 0.0)

    @cached_property
    def floors_by_level(self) -> dict[int, dict]:
        return {floor["level"]: floor for floor in self.floors.values()}

    def floor_name(self, floor_id: str) -> str:
        return self.floors[floor_id]["name"]

    def spaces_on(self, floor_id: str) -> list[dict]:
        return [space for space in self.spaces.values() if space["floor_id"] == floor_id]

    # ---------- geometry ----------

    @cached_property
    def polygons(self) -> dict[str, Polygon]:
        result = {}
        for space_id, space in self.spaces.items():
            polygon = Polygon(space["polygon"])
            if not polygon.is_valid:
                polygon = make_valid(polygon)
            result[space_id] = polygon
        return result

    def area(self, space_id: str) -> float:
        return Polygon(self.spaces[space_id]["polygon"]).area

    # ---------- descriptions ----------

    def label(self, space_id: str) -> str:
        if space_id == OUTSIDE:
            return "outside"
        space = self.spaces[space_id]
        return f"{space['name']} ({self.floor_name(space['floor_id'])})"

    def is_room(self, space_id: str) -> bool:
        return self.spaces[space_id]["type"] not in CIRCULATION_TYPES
