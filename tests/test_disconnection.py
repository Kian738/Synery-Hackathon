"""A route that cannot exist because the two places are in separate parts of the building says so and offers the nearest reachable place."""
import networkx as nx

from eval.common import building_paths
from floorwise.agent.session import Session, main_entrance
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building


def test_separate_parts_are_explained():
    path = next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == "swiss-1785")
    session = Session.for_building(Building.load(path.parent))
    b = session.building
    graph = RouteGraph(b, Constraints()).graph
    parts = sorted((c for c in nx.connected_components(graph)), key=len, reverse=True)
    start = main_entrance(b)
    mine = next(c for c in parts if start in c)
    other = next(c for c in parts if c is not mine and any(s in b.spaces and b.spaces[s]["type"] == "room" for s in c))
    target = next(s for s in sorted(other) if s in b.spaces and b.spaces[s]["type"] == "room")
    result = session.route(start, target)
    assert result["error"].startswith("No route from")
    info = result["disconnected"]
    assert "separate parts" in info["text"] and info["rooms_reachable_from_start"] == len([s for s in mine if s in b.spaces and b.spaces[s]["type"] != "outdoor"])
    assert info.get("nearest_reachable_place")
