"""The Sunday answers file must carry every reading of "route as ordered node ids", and each must be real."""
import pytest

from floorwise.agent.solve import solve
from floorwise.cli import structured
from floorwise.core.graph import DOOR_PREFIX, Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building
from floorwise.paths import DATA

TOLERANCE_M = 0.01


def node_path(result: dict) -> list[str]:
    """Every graph node of the route, legs joined without repeating the shared stop."""
    return [n for i, leg in enumerate(result["legs"]) for n in (leg["nodes"] if i == 0 else leg["nodes"][1:])]


@pytest.fixture(scope="module")
def campus() -> Building:
    return Building.load(DATA / "dev" / "proc-campus-dev-000")


def space_id(building: Building, name: str) -> str:
    return next(space["id"] for space in building.spaces.values() if space["name"] == name)


@pytest.fixture(scope="module")
def route(campus):
    start, end = space_id(campus, "Main lobby"), space_id(campus, "Print room 0.16")
    result, reply = solve(campus, "route", {"start": start, "destination": end})
    return start, end, result, reply


def test_node_path_is_a_real_walk_through_the_route_graph(campus, route):
    start, end, result, _ = route
    nodes, graph = node_path(result), RouteGraph(campus, Constraints())
    assert nodes[0] == start and nodes[-1] == end
    assert any(node.startswith(DOOR_PREFIX) for node in nodes)
    walked = sum(graph.edge_via(a, b)["weight"] for a, b in zip(nodes, nodes[1:], strict=False))
    assert abs(walked - result["length_m"]) <= TOLERANCE_M


def test_space_path_is_the_node_path_without_door_nodes(route):
    _, _, result, _ = route
    assert result["space_path"] == [n for n in node_path(result) if not n.startswith(DOOR_PREFIX)]


def test_answers_entry_carries_all_route_readings(route):
    start, end, result, reply = route
    entry = structured("q1", reply, {"kind": "route", "result": result})
    assert entry["route"][0] == start and entry["route"][-1] == end
    assert entry["route_nodes"] == node_path(result)
    assert entry["route_elements"] == [e for leg in result["legs"] for e in leg["element_path"]]
    assert OUTSIDE not in entry["route"] or entry["route"].count(OUTSIDE) == 1
