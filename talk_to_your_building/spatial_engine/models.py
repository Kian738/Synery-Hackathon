"""Domain data models for spatial building representation.

Provides clean, performant dataclass structures for Building, Floor, Space,
Opening, VerticalConnector, and Asset with pre-parsed Shapely 2.0 geometries
and indexed lookups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from shapely.geometry import LinearRing, Point, Polygon


@dataclass(slots=True)
class BuildingMetadata:
    """Metadata describing a building dataset."""

    id: str
    name: str
    source: str
    source_ref: dict[str, Any] = field(default_factory=dict)
    license: Optional[str] = None
    attribution: Optional[str] = None
    split: Optional[str] = None
    units: str = "m"


@dataclass(slots=True)
class Floor:
    """Elevation level / story of a building."""

    id: str
    level: int
    name: str
    elevation_m: float
    height_m: float


@dataclass(slots=True)
class Space:
    """A room, hall, corridor, stairwell, lift shaft, or outdoor space."""

    id: str
    floor_id: str
    type: str  # room, hall, corridor, stair, lift, outdoor
    room_type: str  # generic_room, office, toilet, storage, etc.
    name: str
    ref: str
    polygon_coords: list[tuple[float, float]]
    polygon: Polygon
    area: float
    centroid: tuple[float, float]
    representative_point: tuple[float, float]
    exterior_ring: LinearRing
    synthetic: bool = False

    def contains_point(self, x: float, y: float) -> bool:
        """Check if 2D coordinate is inside or on the boundary of the space."""
        return self.polygon.contains(Point(x, y)) or self.polygon.touches(Point(x, y))


@dataclass(slots=True)
class Opening:
    """A door, cased opening, or building entrance connecting spaces."""

    id: str
    floor_id: str
    space_ids: list[str]  # Connected space IDs (or 'outside')
    kind: str  # door, opening, entrance
    position: tuple[float, float]
    width_m: float
    step_free: bool
    synthetic: bool = False

    @property
    def is_entrance(self) -> bool:
        """Check if opening leads to the outside."""
        return "outside" in self.space_ids

    def other_side(self, current_space_id: str) -> Optional[str]:
        """Return the space ID on the opposite side of the opening."""
        for sid in self.space_ids:
            if sid != current_space_id:
                return sid
        return None


@dataclass(slots=True)
class VerticalConnector:
    """Vertical connector (stairs or lift) spanning multiple floor levels."""

    id: str
    kind: str  # stairs, lift
    name: str
    floor_ids: list[str]
    space_ids: list[str]
    step_free: bool
    synthetic: bool = False

    @property
    def is_lift(self) -> bool:
        """Check if connector is an elevator."""
        return self.kind.lower() == "lift"

    @property
    def is_stairs(self) -> bool:
        """Check if connector is a staircase."""
        return self.kind.lower() in ("stairs", "stair")


# Backwards compatibility alias
Connector = VerticalConnector


@dataclass(slots=True)
class AssetFootprint:
    """Physical footprint dimensions of an asset."""

    width_m: float
    depth_m: float
    rotation_deg: float = 0.0


@dataclass(slots=True)
class Asset:
    """Equipment, machine, or furniture placed within a space."""

    id: str
    name: str
    category: str  # machine, furniture, equipment, etc.
    type: str  # office_chair, fire_extinguisher, bookshelf, etc.
    space_id: str
    floor_id: str
    position: tuple[float, float]
    footprint: Optional[AssetFootprint] = None
    source: Optional[str] = None


@dataclass
class Building:
    """Complete building model with pre-parsed geometries and fast spatial indices."""

    metadata: BuildingMetadata
    floors: dict[str, Floor]  # floor_id -> Floor
    spaces: dict[str, Space]  # space_id -> Space
    openings: dict[str, Opening]  # opening_id -> Opening
    connectors: dict[str, VerticalConnector]  # connector_id -> VerticalConnector
    assets: dict[str, Asset]  # asset_id -> Asset

    # Pre-computed spatial and category indices
    floors_by_level: dict[int, Floor] = field(default_factory=dict)
    spaces_by_floor: dict[str, list[Space]] = field(default_factory=dict)
    spaces_by_floor_and_room_type: dict[tuple[str, str], list[Space]] = field(default_factory=dict)
    openings_by_space: dict[str, list[Opening]] = field(default_factory=dict)
    openings_by_floor: dict[str, list[Opening]] = field(default_factory=dict)
    connectors_by_floor: dict[str, list[VerticalConnector]] = field(default_factory=dict)
    assets_by_space: dict[str, list[Asset]] = field(default_factory=dict)
    assets_by_type: dict[str, list[Asset]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Building identifier."""
        return self.metadata.id

    @property
    def name(self) -> str:
        """Building display name."""
        return self.metadata.name

    def get_floor(self, floor_id_or_level: str | int) -> Optional[Floor]:
        """Look up floor by ID or integer level."""
        if isinstance(floor_id_or_level, int):
            return self.floors_by_level.get(floor_id_or_level)
        return self.floors.get(floor_id_or_level)

    def get_space(self, space_id: str) -> Optional[Space]:
        """Look up space by space ID."""
        return self.spaces.get(space_id)

    def find_spaces(
        self,
        floor_id: Optional[str] = None,
        room_type: Optional[str] = None,
        space_type: Optional[str] = None,
    ) -> list[Space]:
        """Query spaces by floor, room_type, and/or structural space type."""
        norm_room_type = room_type.strip().lower().replace(" ", "_") if room_type else None
        if floor_id and norm_room_type:
            res = self.spaces_by_floor_and_room_type.get((floor_id, norm_room_type), [])
            if space_type:
                res = [s for s in res if s.type == space_type]
            return list(res)

        candidates = (
            self.spaces_by_floor.get(floor_id, [])
            if floor_id
            else list(self.spaces.values())
        )

        if norm_room_type:
            candidates = [s for s in candidates if s.room_type == norm_room_type]
        if space_type:
            candidates = [s for s in candidates if s.type == space_type]

        return candidates

    def find_space_by_ref_or_name(
        self, ref_or_name: str, floor_id: Optional[str] = None
    ) -> Optional[Space]:
        """Find a space by exact space ID, reference, or name matching."""
        ref_or_name_clean = ref_or_name.strip()
        ref_or_name_lower = ref_or_name_clean.lower()

        # 1. Exact ID
        if ref_or_name_clean in self.spaces:
            space = self.spaces[ref_or_name_clean]
            if floor_id is None or space.floor_id == floor_id:
                return space

        candidates = (
            self.spaces_by_floor.get(floor_id, list(self.spaces.values()))
            if floor_id
            else list(self.spaces.values())
        )

        # 2. Case-insensitive ID
        for s in candidates:
            if s.id.lower() == ref_or_name_lower:
                return s

        # 3. Exact ref
        for s in candidates:
            if s.ref and s.ref.lower() == ref_or_name_lower:
                return s

        # 4. Exact name
        for s in candidates:
            if s.name and s.name.lower() == ref_or_name_lower:
                return s

        # 5. Name ending with ref or partial match
        for s in candidates:
            ref = s.ref.lower() if s.ref else ""
            if ref and (ref_or_name_lower.endswith(" " + ref) or ref_or_name_lower == ref):
                return s

        # 6. Stripped match
        for s in candidates:
            if s.name and s.name.lower().strip() == ref_or_name_lower:
                return s

        return None
