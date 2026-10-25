"""Rooms that overlap in the data are reported to the 3D scene as shared polygons (drawn blended), never merged into the analytical model."""
from shapely.geometry import Polygon

from eval.common import building_paths
from floorwise.core.model import Building
from floorwise.core.scene import compile_scene


def test_overlaps_are_compiled_and_lie_inside_both_rooms():
    path = next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == "osm-way27917482")
    building = Building.load(path.parent)
    overlaps = compile_scene(building)["overlaps"]
    assert len(overlaps) >= 10
    for o in overlaps[:20]:
        shared = Polygon(o["polygon"]).buffer(0)
        for sid in (o["a"], o["b"]):
            room = Polygon(building.spaces[sid]["polygon"]).buffer(0)
            assert room.buffer(0.01).contains(shared), sid
        assert building.spaces[o["a"]]["floor_id"] == building.spaces[o["b"]]["floor_id"] == o["floor_id"]
