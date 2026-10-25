"""Open-air bridges and stairs get fences (1.1 m), not room walls; nothing on the lowest floor, no room, and no roof closes over them."""
from shapely.geometry import Point, Polygon

from eval.common import building_paths
from floorwise.core.model import Building
from floorwise.core.scene import compile_scene


def load(name: str) -> Building:
    return Building.load(next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == name).parent)


def test_cit_bridges_and_open_stairs_are_fenced():
    b = load("osm-way27917482")
    scene = compile_scene(b)
    rails = [w for w in scene["walls"] if w.get("rail")]
    assert len(rails) >= 50
    lowest = min(b.data["floors"], key=lambda f: f["level"])["id"]
    for w in rails:
        space = b.spaces[w["space_id"]]
        assert space["type"] in ("corridor", "stair")
        assert space["floor_id"] != lowest
        assert w["height_m"] <= 1.1 + 1e-9
    # full-height walls remain for rooms
    room_walls = [w for w in scene["walls"] if w.get("space_id") in b.spaces and b.spaces[w["space_id"]]["type"] == "room"]
    assert room_walls and all(w["height_m"] >= 2.5 for w in room_walls[:200])


def test_no_roof_over_a_fenced_walkway():
    b = load("osm-way27917482")
    scene = compile_scene(b)
    railed = {w["space_id"] for w in scene["walls"] if w.get("rail")}
    for roof in scene["roofs"]:
        triangles = [roof["vertices"][i:i + 3] for i in range(0, len(roof["vertices"]), 3)]
        for sid in railed:
            space = b.spaces[sid]
            if space["floor_id"] != roof["floor_id"]:
                continue
            centre = Polygon(space["polygon"]).buffer(0).representative_point()
            assert not any(Polygon(t).buffer(0).contains(Point(centre)) for t in triangles if len(t) == 3), sid


def test_ordinary_buildings_keep_their_walls():
    b = load("swiss-1785")
    assert not [w for w in compile_scene(b)["walls"] if w.get("rail")]
