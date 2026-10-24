"""The organisers' forklift rule: openings of 3 m or more, production bays are destinations and never shortcuts."""
import itertools

import pytest

from floorwise.core.graph import Constraints
from floorwise.core.model import Building
from floorwise.core.profiles import FORKLIFT_MIN_OPENING_M, PRODUCTION_BAY_ROOM_TYPE, forklift
from floorwise.core.routing import NoRoute, plan_route
from floorwise.paths import DATA


@pytest.fixture(scope="module")
def factory() -> Building:
    return Building.load(DATA / "dev" / "proc-factory-dev-003")


def spaces_of(building: Building, room_type: str, floor_level: int = 0) -> list[str]:
    return [s["id"] for s in building.spaces.values()
            if s["room_type"] == room_type and building.level(s["floor_id"]) == floor_level]


def forklift_routes(building: Building):
    """Every reachable pair of ground-floor logistics and warehouse bays."""
    bays = spaces_of(building, "logistics_zone") + spaces_of(building, "warehouse_zone")
    for start, end in itertools.permutations(bays, 2):
        try:
            yield start, end, plan_route(building, [start, end], forklift())
        except NoRoute:
            continue


def test_forklift_routes_only_cross_wide_openings(factory):
    checked = 0
    for _, _, route in forklift_routes(factory):
        for leg in route.legs:
            widths = [factory.openings[e]["width_m"] for e in leg.element_path if e in factory.openings]
            assert widths and min(widths) >= FORKLIFT_MIN_OPENING_M
        checked += 1
    assert checked >= 5


def test_a_production_bay_is_never_a_shortcut(factory):
    for start, end, route in forklift_routes(factory):
        passed = route.legs[0].space_path[1:-1]
        assert not [s for s in passed if factory.spaces[s]["room_type"] == PRODUCTION_BAY_ROOM_TYPE], (start, end)


def test_a_production_bay_is_still_a_destination(factory):
    bay = spaces_of(factory, PRODUCTION_BAY_ROOM_TYPE)[0]
    aisle = next(s["id"] for s in factory.spaces.values() if s["room_type"] == "corridor" and s["name"].startswith("Main aisle"))
    try:
        route = plan_route(factory, [aisle, bay], forklift())
    except NoRoute:
        pytest.skip("no wide-opening route from this aisle to this bay in this building")
    assert route.legs[0].space_path[-1] == bay


def test_forklift_never_beats_the_unrestricted_route(factory):
    for start, end, route in itertools.islice(forklift_routes(factory), 6):
        assert route.length_m >= plan_route(factory, [start, end], Constraints()).length_m - 0.011
