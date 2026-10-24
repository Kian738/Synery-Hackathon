"""The judges' route rules (kit 1.1.0 README section 3 and Synera's channel notes), pinned on small buildings whose
answers can be worked out by hand. The full-dataset checks are eval.routes (gold answers), eval.differential (the kit's
own implementation) and eval.rules (every rule as a property on every building)."""

import copy

import pytest

from eval import judge
from floorwise.core import spacewalk
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building
from floorwise.core.routing import NoRoute, plan_route


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def space(sid, polygon, kind="room", room_type="office", floor="F0"):
    return {"id": sid, "floor_id": floor, "type": kind, "room_type": room_type, "name": sid, "ref": sid, "polygon": polygon}


def door(oid, a, b, x, y, width=0.9, kind="door", step_free=True, floor="F0"):
    return {"id": oid, "floor_id": floor, "space_ids": [a, b], "kind": kind, "position": [x, y], "width_m": width, "step_free": step_free}


def building(spaces, openings, connectors=(), floors=None):
    floors = floors or [{"id": "F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 3.8}]
    return Building({"building": {"id": "synthetic", "name": "Synthetic", "source": "test"}, "floors": floors, "spaces": spaces,
                     "openings": openings, "vertical_connectors": list(connectors), "assets": []})


def test_a_door_lands_30cm_inside_and_the_walk_is_straight_in_a_convex_room():
    b = building([space("A", rect(0, 0, 10, 10)), space("B", rect(10, 0, 20, 10))], [door("O1", "A", "B", 10, 5)])
    graph = RouteGraph(b).graph
    # A's centre (5, 5) to the door: 4.7 m to the landing at (9.7, 5) plus the 0.3 m step to the door itself
    assert graph["A"]["door:O1"][0]["weight"] == pytest.approx(5.0, abs=1e-3)
    assert graph["B"]["door:O1"][0]["weight"] == pytest.approx(5.0, abs=1e-3)
    assert plan_route(b, ["A", "B"]).length_m == pytest.approx(10.0, abs=1e-2)


def test_walks_go_round_corners_and_stay_off_the_walls():
    l_shape = [[0, 0], [10, 0], [10, 2], [2, 2], [2, 10], [0, 10]]
    b = building([space("L", l_shape, kind="corridor", room_type="corridor"), space("E", rect(10, 0, 14, 2)), space("N", rect(0, 10, 2, 14))],
                 [door("E1", "L", "E", 10, 1), door("N1", "L", "N", 1, 10)])
    graph = RouteGraph(b).graph
    through_corner = graph["door:E1"]["door:N1"][0]["weight"]
    assert through_corner > ((10 - 1) ** 2 + (1 - 10) ** 2) ** 0.5  # longer than the straight line through the wall
    line = spacewalk.path_inside(b.spaces["L"], list(b.openings.values()), "door:E1", "door:N1")
    walkable = spacewalk.outline(l_shape).buffer(-0.15).buffer(0.02)
    from shapely.geometry import LineString
    assert walkable.covers(LineString(line[1:-1]))
    assert sum(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 for p, q in zip(line, line[1:])) == pytest.approx(through_corner, abs=1e-3)


def two_floor_building(connector_kind="stairs", stops=2):
    floors = [{"id": f"F{i}", "level": i, "name": f"Floor {i}", "elevation_m": 3.8 * i, "height_m": 3.8} for i in range(stops)]
    spaces = [space(f"C{i}", rect(0, 0, 4, 4), kind="stair" if connector_kind == "stairs" else "lift", room_type="stairwell", floor=f"F{i}") for i in range(stops)]
    connector = {"id": "V1", "kind": connector_kind, "name": "Core", "floor_ids": [f"F{i}" for i in range(stops)],
                 "space_ids": [f"C{i}" for i in range(stops)], "step_free": connector_kind == "lift"}
    return building(spaces, [], [connector], floors)


def test_stairs_cost_two_metres_per_metre_climbed():
    graph = RouteGraph(two_floor_building("stairs")).graph
    assert graph["C0"]["C1"][0]["weight"] == pytest.approx(2 * 3.8)


def test_a_lift_ride_costs_fifteen_once_plus_one_per_metre_and_joins_every_pair():
    b = two_floor_building("lift", stops=3)
    graph = RouteGraph(b).graph
    assert graph["C0"]["C1"][0]["weight"] == pytest.approx(15 + 3.8)
    assert graph["C0"]["C2"][0]["weight"] == pytest.approx(15 + 7.6)  # one fee for two floors, not two
    assert plan_route(b, ["C0", "C2"]).length_m == pytest.approx(22.6)


def test_there_is_no_way_round_the_outside():
    # Two wings that only meet outside: an entrance leads out of the building, not into the other wing.
    b = building([space("W1", rect(0, 0, 10, 10)), space("W2", rect(30, 0, 40, 10))],
                 [door("X1", "outside", "W1", 0, 5, kind="entrance"), door("X2", "outside", "W2", 40, 5, kind="entrance")])
    with pytest.raises(NoRoute):
        plan_route(b, ["W1", "W2"])
    assert RouteGraph(b, Constraints(outside="exits")).distances_from("outside")["W2"] > 0  # exit analyses still see both entrances


def test_exit_distance_is_the_walk_to_the_nearest_entrance_door():
    b = building([space("A", rect(0, 0, 10, 10)), space("B", rect(10, 0, 20, 10))],
                 [door("E", "outside", "A", 0, 5, kind="entrance"), door("O1", "A", "B", 10, 5)])
    exits = RouteGraph(b, Constraints(outside="exits")).distances_from("outside")
    assert exits["A"] == pytest.approx(5.0, abs=1e-3)  # from the entrance door to A's centre
    assert exits["B"] == pytest.approx(5.0 + 5.0 + 5.0, abs=1e-2)


def test_parallel_connections_are_both_kept():
    b = building([space("A", rect(0, 0, 10, 10)), space("B", rect(10, 0, 20, 10))],
                 [door("O1", "A", "B", 10, 2), door("O2", "A", "B", 10, 8)])
    assert len(RouteGraph(b).graph.edges) >= 6  # two doors between the same rooms stay two door nodes


def factory():
    """Aisle (corridor) along the south, three bays above it joined by wide openings; bay 2 is also open to bay 1 and 3."""
    spaces = [space("AISLE", rect(0, 0, 60, 6), kind="corridor", room_type="corridor"),
              space("BAY1", rect(0, 6, 20, 26), kind="hall", room_type="production_zone"),
              space("BAY2", rect(20, 6, 40, 26), kind="hall", room_type="assembly_zone"),
              space("BAY3", rect(40, 6, 60, 26), kind="hall", room_type="warehouse_zone"),
              space("OFFICE", rect(60, 0, 66, 6))]
    openings = [door("A1", "AISLE", "BAY1", 10, 6, 5.0, "opening"), door("A2", "AISLE", "BAY2", 30, 6, 5.0, "opening"),
                door("A3", "AISLE", "BAY3", 50, 6, 5.0, "opening"), door("B12", "BAY1", "BAY2", 20, 16, 4.0, "opening"),
                door("B23", "BAY2", "BAY3", 40, 16, 4.0, "opening"), door("OD", "AISLE", "OFFICE", 60, 3, 0.9)]
    return building(spaces, openings)


def test_production_bays_can_be_a_destination_but_never_a_shortcut():
    b = factory()
    free = plan_route(b, ["BAY1", "BAY3"], Constraints())
    assert "BAY2" in free.legs[0].space_path or free.length_m < plan_route(b, ["BAY1", "BAY3"], Constraints(bays_are_destinations=True)).length_m + 1e-9
    rule = plan_route(b, ["BAY1", "BAY3"], Constraints(bays_are_destinations=True))
    assert "BAY2" not in rule.legs[0].space_path          # goes out to the aisle and back in instead
    assert rule.legs[0].space_path == ["BAY1", "AISLE", "BAY3"]
    assert plan_route(b, ["AISLE", "BAY2"], Constraints(bays_are_destinations=True)).legs[0].space_path == ["AISLE", "BAY2"]
    tour = plan_route(b, ["BAY1", "BAY2", "BAY3"], Constraints(bays_are_destinations=True))  # stops are destinations in turn
    assert [leg.space_path[0] for leg in tour.legs] == ["BAY1", "BAY2"]


def test_a_forklift_uses_only_aisles_and_openings_of_three_metres_or_more():
    b = factory()
    assert plan_route(b, ["BAY1", "BAY3"], Constraints(forklift=True)).legs[0].space_path == ["BAY1", "AISLE", "BAY3"]
    with pytest.raises(NoRoute):
        plan_route(b, ["BAY1", "OFFICE"], Constraints(forklift=True))  # the office door is 0.9 m: not a forklift opening
    assert plan_route(b, ["BAY1", "OFFICE"], Constraints()).length_m > 0


def test_closed_places_are_never_used_and_step_free_drops_steps():
    data = copy.deepcopy(factory().data)
    data["openings"].append(door("STEP", "BAY1", "BAY3", 30, 25, 3.0, "door", step_free=False))
    b = Building(data)
    direct = plan_route(b, ["BAY1", "BAY3"], Constraints())
    assert "STEP" in direct.legs[0].element_path or direct.length_m > 0
    stepfree = plan_route(b, ["BAY1", "BAY3"], Constraints(step_free=True))
    assert "STEP" not in stepfree.legs[0].element_path
    closed = plan_route(b, ["BAY1", "BAY3"], Constraints(closed=frozenset({"B12"})))
    assert "B12" not in closed.legs[0].element_path
    with pytest.raises(NoRoute):
        plan_route(b, ["BAY1", "BAY3"], Constraints(closed=frozenset({"BAY1"})))


def test_furniture_is_not_an_obstacle():
    b = factory()
    cluttered = copy.deepcopy(b.data)
    cluttered["assets"] = [{"id": "M1", "name": "Machine", "category": "machine", "type": "cnc_mill", "space_id": "BAY2", "floor_id": "F0",
                            "position": [30, 16], "footprint": {"width_m": 10, "depth_m": 10, "rotation_deg": 0}}]
    assert plan_route(Building(cluttered), ["BAY1", "BAY3"]).length_m == plan_route(b, ["BAY1", "BAY3"]).length_m


def test_our_graph_equals_the_kits_graph_edge_for_edge_on_a_hand_built_building():
    for b in (factory(), two_floor_building("lift", 3)):
        official = judge.kit_map(copy.deepcopy(b.data)).graph(False)
        theirs = sorted((tuple(sorted((u, v))), round(d["weight"], 3)) for u, v, d in official.edges(data=True))
        ours = sorted((tuple(sorted((u, v))), round(d["weight"], 3)) for u, v, d in RouteGraph(b).graph.edges(data=True))
        assert ours == theirs


def test_the_judge_replica_scores_like_the_channel_describes():
    b = factory()
    bm = judge.kit_map(copy.deepcopy(b.data))
    best = plan_route(b, ["BAY1", "BAY3"]).length_m
    good = judge.measure(bm, ["BAY1", "BAY2", "BAY3"])
    assert good.valid and judge.score(best, good, False) == 1.0               # within 1% of the best is full marks
    detour = judge.measure(bm, ["BAY1", "AISLE", "BAY3"])
    assert detour.valid and judge.score(best, detour, False) == pytest.approx(best / detour.length_m)
    assert not judge.measure(bm, ["BAY1", "OFFICE"]).valid                    # no door between them: invalid scores 0
    assert judge.score(best, judge.measure(bm, ["BAY1", "OFFICE"]), False) == 0.0
    assert judge.score(None, None, True) == 1.0 and judge.score(None, good, False) == 0.0   # "no route" is right only when there is none
    assert judge.parse_answer("A -> B -> C") == ["A", "B", "C"] and judge.parse_answer("no route") is None


def test_the_rules_travel_from_the_question_text_to_the_answer_line():
    from floorwise.agent.parse_rules import parse_rules
    from floorwise.agent.solve import solve
    from floorwise.agent.spec import resolve_spec

    b = factory()
    for s in b.data["spaces"]:  # names carry the floor like the dataset's labels do
        s["name"] = s["id"]
    b = Building(b.data)
    text = "How do I get from BAY1 (Ground floor) to BAY3 (Ground floor)? Production bays are destinations, never a shortcut."
    spec = parse_rules(text)
    assert spec.bays_destinations is True
    inputs = resolve_spec(b, spec)
    assert inputs["bays_are_destinations"] is True
    result, reply = solve(b, "route", inputs)
    assert result["space_path"] == ["BAY1", "AISLE", "BAY3"]
    assert reply.splitlines()[-1] == "Answer: BAY1 -> AISLE -> BAY3"  # the ordered spaces, as the judges read it
    inputs["closed_ids"] = ["AISLE"]
    result, reply = solve(b, "route", inputs)
    assert result["reachable"] is False and reply.splitlines()[-1] == "Answer: no route"
    assert parse_rules("Hello, forklift route from BAY1 (Ground floor) to OFFICE (Ground floor)?") is None  # unknown shapes go to the LLM parser
