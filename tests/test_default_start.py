"""The default start must be an entrance that reaches the building, not a side door into a few rooms (eval.connectivity found 25 such buildings)."""
import networkx as nx
import pytest

from eval.common import building_paths
from floorwise.agent.session import main_entrance
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building


def _part_sizes(building):
    graph = RouteGraph(building, Constraints()).graph
    return {sid: len(c) for c in nx.connected_components(graph) for sid in c if sid in building.spaces}


@pytest.mark.parametrize("name", ["swiss-1785", "swiss-100", "osm-way58216509", "swiss-1689"])
def test_default_start_reaches_the_largest_entrance_part(name):
    path = next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == name)
    building = Building.load(path.parent)
    start = main_entrance(building)
    sizes = _part_sizes(building)
    entrances = {next(s for s in o["space_ids"] if s != "outside") for o in building.openings.values() if "outside" in o["space_ids"]}
    assert start in entrances
    assert sizes[start] == max(sizes[e] for e in entrances)
