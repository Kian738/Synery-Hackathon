"""Unit tests for Milestone 2: Multi-Floor Routing & Constraint Engine.

Covers graph construction, step-free filtering, door clearance filtering,
dynamic closures, multi-floor shortest paths, errand routing, reachable room counting,
what-if door simulation, and all 41 routing benchmark questions in `data/dev/`.

Executable directly:
    uv run python tests/unit/test_routing_engine.py
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import networkx as nx
from shapely.geometry import Polygon

from benchmark.score import score_reply
from spatial_engine import load_building
from spatial_engine.graph import (
    OUTSIDE_NODE,
    build_routing_graph,
)
from spatial_engine.models import (
    Asset,
    Building,
    BuildingMetadata,
    Connector,
    Floor,
    Opening,
    Space,
)
from spatial_engine.router import (
    ErrandResult,
    RouteResult,
    count_reachable_rooms,
    directions,
    evaluate_what_if_door,
    find_route,
    resolve_space,
    shortest_path,
    solve_errand,
)

DEV_DIR = Path("data/dev")
BUILDING_FACTORY_003 = DEV_DIR / "proc-factory-dev-003"
BUILDING_FACTORY_012 = DEV_DIR / "proc-factory-dev-012"
BUILDING_OSM_22744230 = DEV_DIR / "osm-way22744230"
BUILDING_OSM_27917482 = DEV_DIR / "osm-way27917482"
BUILDING_RESPLAN_3832 = DEV_DIR / "resplan-3832"


def create_synthetic_building() -> Building:
    """Construct a clean 2-floor synthetic building with known dimensions and connectors."""
    meta = BuildingMetadata(id="synth-bldg", name="Synthetic Building", source="unit_test")
    f0 = Floor(id="F0", level=0, name="Ground Floor", elevation_m=0.0, height_m=3.0)
    f1 = Floor(id="F1", level=1, name="First Floor", elevation_m=3.0, height_m=3.0)
    floors = {"F0": f0, "F1": f1}
    floors_by_level = {0: f0, 1: f1}

    # Floor 0:
    # S1: (0,0) to (5,5) - Room
    # S2: (5,0) to (10,5) - Room
    # S3: (0,5) to (10,8) - Corridor
    p1 = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    p2 = Polygon([(5, 0), (10, 0), (10, 5), (5, 5)])
    p3 = Polygon([(0, 5), (10, 5), (10, 8), (0, 8)])

    s1 = Space(
        id="S1",
        floor_id="F0",
        type="room",
        room_type="office",
        name="Office 1",
        ref="O1",
        polygon_coords=list(p1.exterior.coords),
        polygon=p1,
        area=p1.area,
        centroid=(p1.centroid.x, p1.centroid.y),
        representative_point=(p1.representative_point().x, p1.representative_point().y),
        exterior_ring=p1.exterior,
    )
    s2 = Space(
        id="S2",
        floor_id="F0",
        type="room",
        room_type="storage",
        name="Storage 1",
        ref="ST1",
        polygon_coords=list(p2.exterior.coords),
        polygon=p2,
        area=p2.area,
        centroid=(p2.centroid.x, p2.centroid.y),
        representative_point=(p2.representative_point().x, p2.representative_point().y),
        exterior_ring=p2.exterior,
    )
    s3 = Space(
        id="S3",
        floor_id="F0",
        type="corridor",
        room_type="corridor",
        name="Corridor 0",
        ref="C0",
        polygon_coords=list(p3.exterior.coords),
        polygon=p3,
        area=p3.area,
        centroid=(p3.centroid.x, p3.centroid.y),
        representative_point=(p3.representative_point().x, p3.representative_point().y),
        exterior_ring=p3.exterior,
    )

    # Floor 1:
    # S4: (0,0) to (5,5) - Room (stacked above S1)
    # S5: (5,0) to (10,5) - Room
    p4 = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    p5 = Polygon([(5, 0), (10, 0), (10, 5), (5, 5)])

    s4 = Space(
        id="S4",
        floor_id="F1",
        type="room",
        room_type="office",
        name="Office 2",
        ref="O2",
        polygon_coords=list(p4.exterior.coords),
        polygon=p4,
        area=p4.area,
        centroid=(p4.centroid.x, p4.centroid.y),
        representative_point=(p4.representative_point().x, p4.representative_point().y),
        exterior_ring=p4.exterior,
    )
    s5 = Space(
        id="S5",
        floor_id="F1",
        type="room",
        room_type="office",
        name="Office 3",
        ref="O3",
        polygon_coords=list(p5.exterior.coords),
        polygon=p5,
        area=p5.area,
        centroid=(p5.centroid.x, p5.centroid.y),
        representative_point=(p5.representative_point().x, p5.representative_point().y),
        exterior_ring=p5.exterior,
    )

    spaces = {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5}

    # Openings:
    # D1: S1 <-> S3 (width 1.2m, step_free=True)
    # D2: S2 <-> S3 (width 0.8m, step_free=True - narrow)
    # D3: S3 <-> Outside (width 1.5m, step_free=True - entrance)
    # D4: S1 <-> S2 (width 1.0m, step_free=False - stepped door)
    # D5: S4 <-> S5 (width 1.2m, step_free=True)
    d1 = Opening(
        id="D1",
        floor_id="F0",
        space_ids=["S1", "S3"],
        kind="door",
        position=(2.5, 5.0),
        width_m=1.2,
        step_free=True,
    )
    d2 = Opening(
        id="D2",
        floor_id="F0",
        space_ids=["S2", "S3"],
        kind="door",
        position=(7.5, 5.0),
        width_m=0.8,
        step_free=True,
    )
    d3 = Opening(
        id="D3",
        floor_id="F0",
        space_ids=["S3", "outside"],
        kind="entrance",
        position=(5.0, 8.0),
        width_m=1.5,
        step_free=True,
    )
    d4 = Opening(
        id="D4",
        floor_id="F0",
        space_ids=["S1", "S2"],
        kind="door",
        position=(5.0, 2.5),
        width_m=1.0,
        step_free=False,
    )
    d5 = Opening(
        id="D5",
        floor_id="F1",
        space_ids=["S4", "S5"],
        kind="door",
        position=(5.0, 2.5),
        width_m=1.2,
        step_free=True,
    )
    openings = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5}

    # Connectors:
    # C1: Stairs S1 (F0) <-> S4 (F1)
    # C2: Lift S2 (F0) <-> S5 (F1)
    c1 = Connector(
        id="C1",
        kind="stairs",
        name="Main Stairs",
        floor_ids=["F0", "F1"],
        space_ids=["S1", "S4"],
        step_free=False,
    )
    c2 = Connector(
        id="C2",
        kind="lift",
        name="Service Lift",
        floor_ids=["F0", "F1"],
        space_ids=["S2", "S5"],
        step_free=True,
    )
    connectors = {"C1": c1, "C2": c2}

    # Asset:
    # A1: Fire extinguisher in S2
    a1 = Asset(
        id="A1",
        name="Extinguisher 1",
        category="safety",
        type="fire_extinguisher",
        space_id="S2",
        floor_id="F0",
        position=(6.0, 2.0),
    )
    assets = {"A1": a1}

    return Building(
        metadata=meta,
        floors=floors,
        spaces=spaces,
        openings=openings,
        connectors=connectors,
        assets=assets,
        floors_by_level=floors_by_level,
        spaces_by_floor={"F0": [s1, s2, s3], "F1": [s4, s5]},
        spaces_by_floor_and_room_type={
            ("F0", "office"): [s1],
            ("F0", "storage"): [s2],
            ("F0", "corridor"): [s3],
            ("F1", "office"): [s4, s5],
        },
        openings_by_space={"S1": [d1, d4], "S2": [d2, d4], "S3": [d1, d2, d3], "S4": [d5], "S5": [d5]},
        openings_by_floor={"F0": [d1, d2, d3, d4], "F1": [d5]},
        connectors_by_floor={"F0": [c1, c2], "F1": [c1, c2]},
        assets_by_space={"S2": [a1]},
        assets_by_type={"fire_extinguisher": [a1]},
    )


class TestSyntheticRoutingGraph(unittest.TestCase):
    """Unit tests on synthetic building testing graph mechanics and filters."""

    def setUp(self):
        self.b = create_synthetic_building()

    def test_01_graph_construction_nodes_and_edges(self):
        """Graph contains space nodes, door nodes, outside node, and correct edges."""
        g = build_routing_graph(self.b)
        # Spaces: S1..S5 (5)
        for s in ("S1", "S2", "S3", "S4", "S5"):
            self.assertIn(s, g)
        # Doors: door:D1..door:D5 (5)
        for d in ("D1", "D2", "D3", "D4", "D5"):
            self.assertIn(f"door:{d}", g)
        # Outside node
        self.assertIn(OUTSIDE_NODE, g)
        # Exterior door D3 connects to outside with weight 0.0
        edge_data = g.get_edge_data("door:D3", OUTSIDE_NODE)
        self.assertIsNotNone(edge_data)
        self.assertEqual(edge_data[0]["weight"], 0.0)

    def test_02_stair_weight_formula(self):
        """Stairs weight = 12.0 * span."""
        g = build_routing_graph(self.b, step_free=False)
        edge_data = g.get_edge_data("S1", "S4")
        self.assertIsNotNone(edge_data)
        stair_edge = next(e for e in edge_data.values() if e["kind"] == "stairs")
        self.assertEqual(stair_edge["weight"], 12.0 * 1)  # span 1 floor

    def test_03_lift_weight_formula(self):
        """Lift weight = 15.0 wait + 6.0 * span."""
        g = build_routing_graph(self.b, step_free=False)
        edge_data = g.get_edge_data("S2", "S5")
        self.assertIsNotNone(edge_data)
        lift_edge = next(e for e in edge_data.values() if e["kind"] == "lift")
        self.assertEqual(lift_edge["weight"], 15.0 + 6.0 * 1)  # 21.0

    def test_04_step_free_excludes_stairs_and_stepped_doors(self):
        """step_free=True removes stairs C1 and stepped door D4."""
        g = build_routing_graph(self.b, step_free=True)
        # No stairs between S1 and S4
        self.assertFalse(g.has_edge("S1", "S4"))
        # Stepped door D4 excluded
        self.assertNotIn("door:D4", g)
        # Lift C2 preserved
        self.assertTrue(g.has_edge("S2", "S5"))
        # Accessible doors preserved
        self.assertIn("door:D1", g)

    def test_05_door_clearance_filtering(self):
        """min_door_width filters narrow openings."""
        # D2 has width 0.8m. With min_door_width=1.0m, D2 must be dropped.
        g = build_routing_graph(self.b, min_door_width=1.0)
        self.assertNotIn("door:D2", g)
        # D1 has width 1.2m, must remain
        self.assertIn("door:D1", g)

    def test_06_exact_door_clearance_boundary(self):
        """Opening with width exactly equal to min_door_width is retained."""
        # D4 has width 1.0m
        g = build_routing_graph(self.b, min_door_width=1.0)
        self.assertIn("door:D4", g)

    def test_07_dynamic_closures(self):
        """Closing spaces, openings, or connectors isolates them."""
        # Close space S3
        g_s3 = build_routing_graph(self.b, closed={"S3"})
        self.assertNotIn("S3", g_s3)

        # Close opening D1
        g_d1 = build_routing_graph(self.b, closed={"D1"})
        self.assertNotIn("door:D1", g_d1)

        # Close lift C2
        g_c2 = build_routing_graph(self.b, closed={"C2"})
        self.assertFalse(g_c2.has_edge("S2", "S5"))

    def test_08_reopen_restores_all_edges(self):
        """Reopening closed elements restores the base graph topology."""
        g_base = build_routing_graph(self.b)
        g_reopened = build_routing_graph(self.b, closed=set())
        self.assertEqual(g_base.number_of_nodes(), g_reopened.number_of_nodes())
        self.assertEqual(g_base.number_of_edges(), g_reopened.number_of_edges())


class TestMultiFloorRoutingOperations(unittest.TestCase):
    """Functional routing tests on dev buildings."""

    @classmethod
    def setUpClass(cls):
        cls.b3 = load_building(BUILDING_FACTORY_003)
        cls.b12 = load_building(BUILDING_FACTORY_012)

    def test_01_shortest_path_result_structure(self):
        """shortest_path returns valid RouteResult and supports tuple unpacking."""
        g = build_routing_graph(self.b3)
        res = shortest_path(g, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S014")
        self.assertIsInstance(res, RouteResult)
        self.assertGreater(res.distance, 100.0)
        self.assertIn("proc-factory-dev-003-F1-S014", res.path)

        # Test tuple unpacking
        length, path = res
        self.assertEqual(length, res.distance)
        self.assertEqual(path, res.path)

    def test_02_same_start_and_end_node(self):
        """Distance from a node to itself is 0.0."""
        g = build_routing_graph(self.b3)
        res = shortest_path(g, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0-S013")
        self.assertEqual(res.distance, 0.0)
        self.assertEqual(res.path, ["proc-factory-dev-003-F0-S013"])

    def test_03_nonexistent_node_raises_error(self):
        """Nonexistent nodes raise nx.NodeNotFound."""
        g = build_routing_graph(self.b3)
        with self.assertRaises(nx.NodeNotFound):
            shortest_path(g, "proc-factory-dev-003-F0-S013", "NONEXISTENT_NODE")

    def test_04_step_free_reroutes_via_lift(self):
        """Step-free routing takes longer or equal distance due to avoiding stairs."""
        g_all = build_routing_graph(self.b3, step_free=False)
        g_step = build_routing_graph(self.b3, step_free=True)
        res_all = shortest_path(g_all, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S014")
        res_step = shortest_path(g_step, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S014")
        self.assertGreaterEqual(res_step.distance, res_all.distance)

    def test_05_directions_generation(self):
        """directions() produces structured human-readable steps."""
        g = build_routing_graph(self.b3)
        res = shortest_path(g, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S014")
        steps = directions(g, res.path, self.b3)
        self.assertGreater(len(steps), 1)
        self.assertTrue(steps[0].startswith("Start in"))
        self.assertTrue(steps[-1].startswith("You have arrived"))

    def test_06_high_level_find_route(self):
        """find_route solves multi-stop routes with via waypoints."""
        res = find_route(
            self.b3,
            start="proc-factory-dev-003-F0-S013",
            destination="proc-factory-dev-003-F1-S014",
            via=["proc-factory-dev-003-F0-S028"],
        )
        self.assertIsInstance(res, RouteResult)
        self.assertIn("proc-factory-dev-003-F0-S028", res.space_path)

    def test_07_resolve_space(self):
        """resolve_space resolves direct ID, asset ID, or room name."""
        # Direct ID
        self.assertEqual(
            resolve_space(self.b3, "proc-factory-dev-003-F0-S013"),
            "proc-factory-dev-003-F0-S013",
        )
        # Room ref or name
        s = self.b3.spaces["proc-factory-dev-003-F0-S013"]
        if s.name:
            resolved = resolve_space(self.b3, s.name)
            self.assertEqual(resolved, s.id)


class TestReachableRoomsCounter(unittest.TestCase):
    """Tests for count_reachable_rooms under varied constraints."""

    @classmethod
    def setUpClass(cls):
        cls.b3 = load_building(BUILDING_FACTORY_003)
        cls.b_osm = load_building(BUILDING_OSM_22744230)
        cls.b_res = load_building(BUILDING_RESPLAN_3832)

    def test_01_wide_delivery_factory_003(self):
        """Wide delivery reachability count is 7 in factory 003."""
        cnt = count_reachable_rooms(
            self.b3,
            start_id="proc-factory-dev-003-F0-S013",
            target_floor_id="proc-factory-dev-003-F1",
            step_free=True,
            min_width=1.1,
        )
        self.assertEqual(cnt, 7)

    def test_02_wide_delivery_resplan_3832(self):
        """Wide delivery reachability count is 5 in resplan 3832."""
        cnt = count_reachable_rooms(
            self.b_res,
            start_id="resplan-3832-F0-S001",
            target_floor_id="resplan-3832-F0",
            step_free=True,
            min_width=1.1,
        )
        self.assertEqual(cnt, 5)

    def test_03_step_free_closed_lift_osm(self):
        """Step-free reachability count with closed lift in osm-way22744230 is 30."""
        cnt = count_reachable_rooms(
            self.b_osm,
            start_id="osm-way22744230-F0-S029",
            target_floor_id="osm-way22744230-F2",
            step_free=True,
            closed={"osm-way22744230-V07"},
        )
        self.assertEqual(cnt, 30)

    def test_04_unreachable_floor_returns_zero(self):
        """Reachable count on invalid or disconnected floor returns 0."""
        cnt = count_reachable_rooms(
            self.b3,
            start_id="proc-factory-dev-003-F0-S013",
            target_floor_id="NONEXISTENT_FLOOR",
            step_free=True,
        )
        self.assertEqual(cnt, 0)

    def test_05_monotonic_reduction_with_clearance(self):
        """Reachable rooms decrease monotonically with increasing min_width."""
        widths = [0.8, 1.0, 1.1, 1.3]
        counts = [
            count_reachable_rooms(
                self.b3,
                start_id="proc-factory-dev-003-F0-S013",
                target_floor_id="proc-factory-dev-003-F1",
                step_free=True,
                min_width=w,
            )
            for w in widths
        ]
        for c1, c2 in zip(counts[:-1], counts[1:]):
            self.assertGreaterEqual(c1, c2)


class TestErrandSolver(unittest.TestCase):
    """Tests for solve_errand (start -> nearest asset -> largest target room)."""

    @classmethod
    def setUpClass(cls):
        cls.b3 = load_building(BUILDING_FACTORY_003)
        cls.b12 = load_building(BUILDING_FACTORY_012)

    def test_01_errand_factory_003(self):
        """Errand in factory 003 retrieves stove in S028 then goes to kitchen S014."""
        res = solve_errand(
            self.b3,
            start_id="proc-factory-dev-003-F0-S038",
            asset_type="stove",
            target_room_type="kitchen",
            target_floor_id="proc-factory-dev-003-F1",
        )
        self.assertIsInstance(res, ErrandResult)
        self.assertAlmostEqual(res.total_distance, 132.35, delta=1.0)
        self.assertEqual(res.via, "proc-factory-dev-003-F0-S028")
        self.assertEqual(res.target, "proc-factory-dev-003-F1-S014")

        # Test tuple unpacking
        dist, via, target = res
        self.assertEqual(dist, res.total_distance)
        self.assertEqual(via, res.via_space_id)
        self.assertEqual(target, res.target_space_id)

    def test_02_errand_factory_012(self):
        """Errand in factory 012 retrieves dining table in S030 then goes to meeting room S006."""
        res = solve_errand(
            self.b12,
            start_id="proc-factory-dev-012-F0-S036",
            asset_type="dining_table",
            target_room_type="meeting_room",
            target_floor_id="proc-factory-dev-012-F1",
        )
        self.assertAlmostEqual(res.total_distance, 165.75, delta=1.0)
        self.assertEqual(res.via, "proc-factory-dev-012-F0-S030")
        self.assertEqual(res.target, "proc-factory-dev-012-F1-S006")

    def test_03_errand_triangle_inequality(self):
        """Errand distance >= direct shortest path to target."""
        g = build_routing_graph(self.b3, step_free=False)
        errand_res = solve_errand(
            self.b3,
            start_id="proc-factory-dev-003-F0-S038",
            asset_type="stove",
            target_room_type="kitchen",
            target_floor_id="proc-factory-dev-003-F1",
        )
        direct_res = shortest_path(g, "proc-factory-dev-003-F0-S038", errand_res.target)
        self.assertGreaterEqual(errand_res.total_distance, direct_res.distance - 1e-6)

    def test_04_missing_asset_type_raises_value_error(self):
        """Requesting an asset type not in the building raises ValueError."""
        with self.assertRaises(ValueError):
            solve_errand(
                self.b3,
                start_id="proc-factory-dev-003-F0-S038",
                asset_type="anti_matter_reactor",
                target_room_type="kitchen",
                target_floor_id="proc-factory-dev-003-F1",
            )


class TestWhatIfDoorSimulation(unittest.TestCase):
    """Tests for evaluate_what_if_door counterfactual simulation."""

    @classmethod
    def setUpClass(cls):
        cls.b_osm = load_building(BUILDING_OSM_27917482)

    def test_01_what_if_door_osm_27917482_f2(self):
        """Adding door between S115 and S402 on F2 improves 6 rooms on F3."""
        cnt = evaluate_what_if_door(
            self.b_osm,
            space_a_id="osm-way27917482-F2-S115",
            space_b_id="osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        self.assertEqual(cnt, 6)

    def test_02_what_if_door_osm_27917482_f0(self):
        """Adding door between S170 and S174 on F0 improves 2 rooms on F-1."""
        cnt = evaluate_what_if_door(
            self.b_osm,
            space_a_id="osm-way27917482-F0-S170",
            space_b_id="osm-way27917482-F0-S174",
            target_floor_id="osm-way27917482-F-1",
            threshold=1.0,
        )
        self.assertEqual(cnt, 2)

    def test_03_distant_rooms_raise_value_error(self):
        """Rooms separated by > 0.6m cannot be joined by a door."""
        spaces = list(self.b_osm.spaces.keys())
        with self.assertRaises(ValueError):
            evaluate_what_if_door(
                self.b_osm,
                space_a_id=spaces[0],
                space_b_id=spaces[-1],
                target_floor_id="osm-way27917482-F3",
            )

    def test_04_strict_threshold_monotonicity(self):
        """Higher improvement threshold yields <= count."""
        cnt_1m = evaluate_what_if_door(
            self.b_osm,
            space_a_id="osm-way27917482-F2-S115",
            space_b_id="osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        cnt_5m = evaluate_what_if_door(
            self.b_osm,
            space_a_id="osm-way27917482-F2-S115",
            space_b_id="osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=5.0,
        )
        self.assertGreaterEqual(cnt_1m, cnt_5m)


class TestDevBenchmarkRoutingQuestions(unittest.TestCase):
    """Comprehensive evaluation against all 41 routing benchmark questions in `data/dev/`."""

    def test_01_all_41_dev_routing_questions_pass_100_percent(self):
        """Solve and score all 41 benchmark routing questions across all 40 dev buildings."""
        dev_dir = Path("data/dev")
        total_questions = 0
        passed_questions = 0
        failures: list[str] = []

        for qfile in sorted(dev_dir.glob("*/questions.jsonl")):
            building_dir = qfile.parent
            building = load_building(building_dir)

            with open(qfile, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    kind = item.get("kind")
                    if kind not in ("errand", "wide_delivery_count", "step_free_reachable_count", "what_if_door"):
                        continue

                    total_questions += 1
                    qid = item["id"]
                    inputs = item["inputs"]
                    ans_spec = item["answer"]
                    predicted_ans: str = ""

                    if kind == "wide_delivery_count":
                        count = count_reachable_rooms(
                            building,
                            start_id=inputs["start"],
                            target_floor_id=inputs["floor_id"],
                            step_free=True,
                            min_width=inputs.get("min_width"),
                        )
                        predicted_ans = f"Answer: {count}"

                    elif kind == "step_free_reachable_count":
                        closed_set = {inputs["closed"]} if "closed" in inputs else set()
                        count = count_reachable_rooms(
                            building,
                            start_id=inputs["start"],
                            target_floor_id=inputs["floor_id"],
                            step_free=True,
                            closed=closed_set,
                        )
                        predicted_ans = f"Answer: {count}"

                    elif kind == "errand":
                        errand_res = solve_errand(
                            building,
                            start_id=inputs["start"],
                            asset_type=inputs["asset_type"],
                            target_room_type=inputs["room_type"],
                            target_floor_id=inputs["floor_id"],
                        )
                        predicted_ans = f"Answer: {errand_res.total_distance:.2f}"

                    elif kind == "what_if_door":
                        count = evaluate_what_if_door(
                            building,
                            space_a_id=inputs["first"],
                            space_b_id=inputs["second"],
                            target_floor_id=inputs["floor_id"],
                            threshold=1.0,
                        )
                        predicted_ans = f"Answer: {count}"

                    if score_reply(ans_spec, predicted_ans):
                        passed_questions += 1
                    else:
                        failures.append(f"{qid} ({kind}): predicted='{predicted_ans}', expected={ans_spec}")

        self.assertEqual(
            total_questions,
            41,
            f"Expected exactly 41 routing questions in data/dev, found {total_questions}",
        )
        self.assertEqual(
            len(failures),
            0,
            f"Benchmark failures detected ({len(failures)}/{total_questions}):\n" + "\n".join(failures),
        )
        self.assertEqual(
            passed_questions,
            41,
            f"Expected 41/41 questions to pass, passed {passed_questions}",
        )


class TestDataInteroperability(unittest.TestCase):
    """Verify router functions support both Building instances and raw JSON dicts."""

    def test_01_dict_input_support(self):
        """Routing graph builder and queries accept raw dictionary input."""
        b_dict = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0, "height_m": 3.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "room_type": "storage", "polygon": [[3,0],[5,0],[5,2],[3,2]]},
            ],
            "openings": [
                {"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 1.0, "step_free": True},
            ],
            "vertical_connectors": [],
            "assets": [
                {"id": "A1", "type": "box", "space_id": "S2", "floor_id": "F0", "position": [4.0, 1.0]},
            ],
        }

        g = build_routing_graph(b_dict)
        self.assertEqual(g.number_of_nodes(), 3)  # S1, S2, door:D1

        res = shortest_path(g, "S1", "S2")
        self.assertGreater(res.distance, 0.0)

        cnt = count_reachable_rooms(b_dict, "S1", "F0", step_free=True)
        self.assertEqual(cnt, 2)

        errand_res = solve_errand(b_dict, "S1", "box", "storage", "F0")
        self.assertEqual(errand_res.via, "S2")
        self.assertEqual(errand_res.target, "S2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
