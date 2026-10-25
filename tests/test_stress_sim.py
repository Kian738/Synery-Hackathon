"""The evacuation stress test: invariants that must hold on any building, and the door-flow check against the SFPE rule."""
import networkx as nx
import pytest

from eval.common import building_paths
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import OUTSIDE, Building
from floorwise.stress.sim import Spec, door_capacity, estimate_occupants, run

NAMES = ["proc-factory-dev-003", "swiss-1785", "proc-campus-dev-000", "resplan-15793"]


def load(name: str) -> Building:
    return Building.load(next(p for p in building_paths(["train", "dev", "test"]) if p.parent.name == name).parent)


@pytest.mark.parametrize("name", NAMES)
def test_every_person_is_accounted_for_and_nobody_beats_free_flow(name):
    b = load(name)
    spec = Spec(seed=3)
    result = run(b, spec, keep_people=True)
    k = result.kpis
    assert k["evacuated"] + k["stranded"] == k["people"]
    graph = RouteGraph(b, Constraints(outside="exits", no_lifts=True)).graph
    dist = nx.single_source_dijkstra_path_length(graph, OUTSIDE, weight="weight")
    for pid, room, speed, ready, t_out in result.people:
        assert t_out >= ready + dist[room] / speed - 1e-6, (room, t_out, ready, dist[room], speed)


@pytest.mark.parametrize("name", NAMES[:3])
def test_same_seed_same_result_and_more_people_never_finish_earlier(name):
    b = load(name)
    a1, a2 = run(b, Spec(seed=5)), run(b, Spec(seed=5))
    assert a1.kpis == a2.kpis and a1.doors == a2.doors
    counts, _ = estimate_occupants(b)
    doubled = run(b, Spec(seed=5, occupants={sid: n * 2 for sid, n in counts.items()}))
    assert doubled.kpis["p95_s"] >= a1.kpis["p95_s"] - 1e-6
    assert doubled.kpis["max_s"] >= a1.kpis["max_s"] - 1e-6


@pytest.mark.parametrize("name", NAMES[:3])
def test_closing_a_busy_exit_never_helps(name):
    b = load(name)
    base = run(b, Spec(seed=2))
    exits = [d for d in base.doors if "outside" in d["between"]]
    assert exits
    closed = run(b, Spec(seed=2, closed=frozenset({exits[0]["id"]})))
    assert closed.kpis["stranded"] >= base.kpis["stranded"]
    if closed.kpis["stranded"] == base.kpis["stranded"]:
        assert closed.kpis["max_s"] >= base.kpis["max_s"] - 1e-6


def test_one_metre_door_passes_about_point_nine_two_people_a_second():
    """IMO MSC.1/Circ.1533 test 4 in spirit: 100 people through one 1.0 m door take about 100 / 0.92 s (the SFPE rule with a 15 cm boundary)."""
    import copy

    assert door_capacity(1.0) == pytest.approx(0.92, abs=0.01)
    source = load("proc-factory-dev-003")
    entrance = next(o for o in source.openings.values() if OUTSIDE in o["space_ids"] and o["kind"] == "entrance")
    sid = next(s for s in entrance["space_ids"] if s != OUTSIDE)
    data = copy.deepcopy(source.data)
    data["spaces"] = [s for s in data["spaces"] if s["id"] == sid]
    data["openings"] = [{**entrance, "width_m": 1.0}]
    data["connectors"], data["assets"] = [], []
    b = Building(data, source.directory)
    result = run(b, Spec(occupants={sid: 100}, pre_movement_median_s=0.01, seed=1))
    expected = 100 / door_capacity(1.0)          # about 109 s
    assert result.kpis["evacuated"] == 100
    assert expected <= result.kpis["max_s"] <= expected * 1.1 + 25, (expected, result.kpis["max_s"])
    assert result.doors[0]["peak_queue"] >= 50
    two = copy.deepcopy(data)                    # IMO test 9 in spirit: a second identical exit halves the time (here: a 2 m door)
    two["openings"] = [{**entrance, "width_m": 2.0 - 0.3 + 0.3}]
    wider = run(Building(two, source.directory), Spec(occupants={sid: 100}, pre_movement_median_s=0.01, seed=1))
    assert wider.kpis["max_s"] < result.kpis["max_s"] * 0.65


def test_step_free_evacuation_never_uses_stairs_and_may_strand():
    b = load("swiss-1785")
    plain, stepfree = run(b, Spec(seed=4)), run(b, Spec(kind="step_free_evacuation", seed=4))
    assert not [d for d in stepfree.doors if d["kind"] == "stair"]
    assert stepfree.kpis["stranded"] >= plain.kpis["stranded"]
