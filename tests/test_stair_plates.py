"""No floor stands inside a staircase: the arrival floor's plates never cover a drawn flight's footprint, on any building."""
from shapely.geometry import Polygon
from shapely.ops import unary_union

from eval.common import building_paths
from floorwise.core.model import Building
from floorwise.core.scene import compile_scene


def plate_union(building, scene, floor_id):
    pieces = []
    for sid, space in building.spaces.items():
        if space["floor_id"] != floor_id or space.get("type") in ("stair", "lift") or len(space["polygon"]) < 3:
            continue
        if sid in scene["plates"]:
            pieces += [Polygon(p["exterior"], p["holes"]) for p in scene["plates"][sid]]
        else:
            pieces.append(Polygon(space["polygon"]).buffer(0))
    return unary_union(pieces) if pieces else Polygon()


def test_plates_leave_every_flight_footprint_open_and_change_nothing_else():
    checked = touched = 0
    for path in building_paths(["train", "dev", "test"])[::7]:
        building = Building.load(path.parent)
        scene = compile_scene(building)
        for shaft in scene["stair_shafts"]:
            if not shaft["footprint"]:
                continue
            checked += 1
            footprint = Polygon(shaft["footprint"])
            assert plate_union(building, scene, shaft["to_floor"]).intersection(footprint).area < 1e-3, (building.id, shaft["connector_id"])
        for sid, pieces in scene["plates"].items():
            touched += 1
            original = Polygon(building.spaces[sid]["polygon"]).buffer(0)
            drawn = unary_union([Polygon(p["exterior"], p["holes"]) for p in pieces])
            assert drawn.area <= original.area + 1e-6 and drawn.difference(original.buffer(1e-6)).area < 1e-6, "plates only remove floor, never add"
    assert checked > 20 and touched > 0
