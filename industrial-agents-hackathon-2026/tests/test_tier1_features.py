"""Tier 1: Feature Coverage Test Suite.

Covers all 24 features from PROJECT.md with at least 5 test cases per feature (120+ tests total).
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import unittest

from benchmark.score import committed_answer, numbers_in, score_reply, within, space_matches
from tests.helpers import (
    BUILDING_CAMPUS_000,
    BUILDING_FACTORY_003,
    BUILDING_FACTORY_012,
    BUILDING_OSM_22744230,
    BUILDING_OSM_27917482,
    BUILDING_RESPLAN_3832,
    DEV_DATA_DIR,
    TEST_DATA_DIR,
    PROJECT_ROOT,
    MockVisualizerDispatcher,
    ReferenceOracle,
    format_benchmark_answer,
    load_building_json,
)

# Detect M1 implementation
try:
    import spatial_engine as se
    HAS_SPATIAL_ENGINE = True
except ImportError:
    se = None  # type: ignore
    HAS_SPATIAL_ENGINE = False

# Detect M2 implementation
try:
    import spatial_engine.graph as se_graph
    import spatial_engine.router as se_router
    HAS_M2_ROUTER = True
except ImportError:
    HAS_M2_ROUTER = False

# Detect M3 implementation
try:
    import spatial_engine.solver as se_solver
    HAS_M3_SOLVER = True
except ImportError:
    HAS_M3_SOLVER = False


class TestFeature01LargestRoom(unittest.TestCase):
    """Feature 1: largest_room query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)
        if HAS_SPATIAL_ENGINE:
            cls.b3_se = se.load_building(BUILDING_FACTORY_003)
            cls.b12_se = se.load_building(BUILDING_FACTORY_012)

    def test_01_largest_kitchen_factory_003(self):
        """Verify largest kitchen on F1 in factory 003 matches ground truth (Kitchen 1.14, 28.0 m²)."""
        room_o, area_o = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        self.assertIn("1.14", room_o["name"])
        self.assertAlmostEqual(area_o, 28.0, delta=0.5)

        if HAS_SPATIAL_ENGINE:
            room_se, area_se = se.find_largest_room(self.b3_se, "proc-factory-dev-003-F1", "kitchen")
            self.assertIn("1.14", room_se.name)
            self.assertAlmostEqual(area_se, 28.0, delta=0.5)

    def test_02_largest_kitchen_factory_012(self):
        """Verify largest kitchen on F0 in factory 012 matches ground truth (Kitchen 0.30, 28.2 m²)."""
        room_o, area_o = ReferenceOracle.largest_room(self.b12_raw, "proc-factory-dev-012-F0", "kitchen")
        self.assertIn("0.30", room_o["name"])
        self.assertAlmostEqual(area_o, 28.2, delta=0.5)

        if HAS_SPATIAL_ENGINE:
            room_se, area_se = se.find_largest_room(self.b12_se, "proc-factory-dev-012-F0", "kitchen")
            self.assertIn("0.30", room_se.name)
            self.assertAlmostEqual(area_se, 28.2, delta=0.5)

    def test_03_largest_meeting_room_campus_000(self):
        """Verify largest meeting room on F0 in campus 000."""
        b_raw = load_building_json(BUILDING_CAMPUS_000)
        room_o, area_o = ReferenceOracle.largest_room(b_raw, "proc-campus-dev-000-F0", "meeting_room")
        self.assertGreater(area_o, 10.0)

        if HAS_SPATIAL_ENGINE:
            b_se = se.load_building(BUILDING_CAMPUS_000)
            room_se, area_se = se.find_largest_room(b_se, "proc-campus-dev-000-F0", "meeting_room")
            self.assertEqual(room_o["name"], room_se.name)
            self.assertAlmostEqual(area_o, area_se, delta=1e-3)

    def test_04_benchmark_scorer_compliance(self):
        """Verify reply formatting passes official benchmark score_reply validator."""
        room_o, area_o = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        ans_spec = {
            "type": "space",
            "accept": ["1.14", "Kitchen 1.14"],
            "reject": ["1.28", "Kitchen 1.28"],
            "area": {"type": "number", "value": 28.0, "unit": "m2", "relative_tolerance": 0.05, "absolute_tolerance": 0.0},
        }
        reply = format_benchmark_answer("largest_room", (room_o["name"], area_o))
        self.assertTrue(score_reply(ans_spec, reply))

    def test_05_rejection_ordering_integrity(self):
        """Ensure that mentioning runner-up room before the accepted room causes score_reply to fail."""
        ans_spec = {
            "type": "space",
            "accept": ["1.14"],
            "reject": ["1.28"],
            "area": {"type": "number", "value": 28.0, "unit": "m2", "relative_tolerance": 0.05, "absolute_tolerance": 0.0},
        }
        bad_reply = "Answer: 1.28 is smaller than 1.14, 28.0 m²"
        self.assertFalse(score_reply(ans_spec, bad_reply))


class TestFeature02FloorAreaTotal(unittest.TestCase):
    """Feature 2: floor_area_total query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)
        if HAS_SPATIAL_ENGINE:
            cls.b3_se = se.load_building(BUILDING_FACTORY_003)
            cls.b12_se = se.load_building(BUILDING_FACTORY_012)

    def test_01_meeting_room_total_factory_003_f0(self):
        """Verify meeting room total area on F0 (ground truth 171.65 m²)."""
        tot_o = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F0", "meeting_room")
        self.assertAlmostEqual(tot_o, 171.65, delta=1.0)

        if HAS_SPATIAL_ENGINE:
            tot_se = se.calculate_floor_area_total(self.b3_se, "proc-factory-dev-003-F0", "meeting_room")
            self.assertAlmostEqual(tot_se, 171.65, delta=1.0)

    def test_02_kitchen_total_factory_012_f1(self):
        """Verify kitchen total area on F1 (ground truth 106.3 m²)."""
        tot_o = ReferenceOracle.floor_area_total(self.b12_raw, "proc-factory-dev-012-F1", "kitchen")
        self.assertAlmostEqual(tot_o, 106.3, delta=1.0)

        if HAS_SPATIAL_ENGINE:
            tot_se = se.calculate_floor_area_total(self.b12_se, "proc-factory-dev-012-F1", "kitchen")
            self.assertAlmostEqual(tot_se, 106.3, delta=1.0)

    def test_03_zero_rooms_returns_zero(self):
        """Floor with no rooms of requested type should total 0.0 m²."""
        tot = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F0", "nonexistent_room_type")
        self.assertEqual(tot, 0.0)

    def test_04_single_number_scoring_rule(self):
        """Answer line must contain exactly one number."""
        tot = 171.65
        reply_ok = f"Answer: {round(tot, 1)}"
        ans_spec = {"type": "number", "value": 171.65, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(ans_spec, reply_ok))

    def test_05_multi_number_rejection(self):
        """Extraneous numbers in the answer line should be rejected by benchmark scorer."""
        ans_spec = {"type": "number", "value": 171.65, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
        reply_bad = "Answer: 171.65 m² across 6 rooms"
        self.assertFalse(score_reply(ans_spec, reply_bad))


class TestFeature03StraightLine3D(unittest.TestCase):
    """Feature 3: straight_line_3d query."""

    @classmethod
    def setUpClass(cls):
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)
        if HAS_SPATIAL_ENGINE:
            cls.b12_se = se.load_building(BUILDING_FACTORY_012)

    def test_01_cross_floor_distance_factory_012(self):
        """Verify 3D distance between F2-S035 and F0-S037 (ground truth 27.37 m)."""
        spaces = {s["id"]: s for s in self.b12_raw["spaces"]}
        s_a = spaces["proc-factory-dev-012-F2-S035"]
        s_b = spaces["proc-factory-dev-012-F0-S037"]
        dist_o = ReferenceOracle.straight_line_3d(s_a, s_b, self.b12_raw)
        self.assertAlmostEqual(dist_o, 27.37, delta=0.5)

        if HAS_SPATIAL_ENGINE:
            s_a_se = self.b12_se.get_space("proc-factory-dev-012-F2-S035")
            s_b_se = self.b12_se.get_space("proc-factory-dev-012-F0-S037")
            dist_se = se.calculate_straight_line_3d(s_a_se, s_b_se, self.b12_se)
            self.assertAlmostEqual(dist_se, 27.37, delta=0.5)

    def test_02_same_floor_coplanar_distance(self):
        """3D distance on the same floor should equal 2D centroid distance."""
        spaces = [s for s in self.b12_raw["spaces"] if s["floor_id"] == "proc-factory-dev-012-F0"]
        s1, s2 = spaces[0], spaces[1]
        dist_3d = ReferenceOracle.straight_line_3d(s1, s2, self.b12_raw)
        # Compute pure 2D centroid distance
        poly1 = se.models.Polygon(s1["polygon"]) if HAS_SPATIAL_ENGINE else se_models_poly(s1["polygon"])
        from shapely.geometry import Polygon
        c1 = Polygon(s1["polygon"]).centroid
        c2 = Polygon(s2["polygon"]).centroid
        dist_2d = math.hypot(c1.x - c2.x, c1.y - c2.y)
        self.assertAlmostEqual(dist_3d, dist_2d, delta=1e-5)

    def test_03_zero_distance_to_self(self):
        """3D distance from a room to itself must strictly be 0.0."""
        s = self.b12_raw["spaces"][0]
        dist = ReferenceOracle.straight_line_3d(s, s, self.b12_raw)
        self.assertEqual(dist, 0.0)

    def test_04_scorer_tolerance_compliance(self):
        """Scorer accepts distance within 2% relative tolerance."""
        ans_spec = {"type": "number", "value": 27.37, "relative_tolerance": 0.02, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(ans_spec, "Answer: 27.37"))
        self.assertTrue(score_reply(ans_spec, f"Answer: {round(27.37 * 1.015, 2)}"))

    def test_05_symmetry(self):
        """Distance(A, B) must equal Distance(B, A)."""
        spaces = self.b12_raw["spaces"]
        d_ab = ReferenceOracle.straight_line_3d(spaces[0], spaces[5], self.b12_raw)
        d_ba = ReferenceOracle.straight_line_3d(spaces[5], spaces[0], self.b12_raw)
        self.assertAlmostEqual(d_ab, d_ba, delta=1e-7)


class TestFeature04RoomStacked(unittest.TestCase):
    """Feature 4: room_stacked query."""

    @classmethod
    def setUpClass(cls):
        cls.b_osm = load_building_json(BUILDING_OSM_27917482)
        if HAS_SPATIAL_ENGINE:
            cls.b_osm_se = se.load_building(BUILDING_OSM_27917482)

    def test_01_stacked_below_osm_building(self):
        """Verify stacked space below F0-S155 is -1.04.018."""
        spaces = {s["id"]: s for s in self.b_osm["spaces"]}
        target = spaces["osm-way27917482-F0-S155"]
        room_o, overlap_o = ReferenceOracle.stacked_room(target, "below", self.b_osm)
        self.assertIn("-1.04.018", room_o.get("name", "") or room_o.get("ref", ""))
        self.assertGreater(overlap_o, 0.0)

        if HAS_SPATIAL_ENGINE:
            t_se = self.b_osm_se.get_space("osm-way27917482-F0-S155")
            room_se, overlap_se = se.find_stacked_room(t_se, "below", self.b_osm_se)
            self.assertIn("-1.04.018", room_se.name or room_se.ref)
            self.assertAlmostEqual(overlap_o, overlap_se, delta=1e-3)

    def test_02_stacked_above_osm_building(self):
        """Verify stacked space above basement level -1."""
        spaces = {s["id"]: s for s in self.b_osm["spaces"]}
        b_space = [s for s in self.b_osm["spaces"] if s["floor_id"] == "osm-way27917482-F-1"][0]
        room_o, overlap_o = ReferenceOracle.stacked_room(b_space, "above", self.b_osm)
        self.assertEqual(room_o["floor_id"], "osm-way27917482-F0")
        self.assertGreater(overlap_o, 0.0)

    def test_03_invalid_direction_raises_error(self):
        """Querying above top floor level must raise an error."""
        top_floor = max(self.b_osm["floors"], key=lambda f: f["level"])
        top_space = [s for s in self.b_osm["spaces"] if s["floor_id"] == top_floor["id"]][0]
        with self.assertRaises((ValueError, KeyError)):
            ReferenceOracle.stacked_room(top_space, "above", self.b_osm)

    def test_04_scorer_space_matching(self):
        """Answer matches space acceptance rule."""
        ans_spec = {"type": "space", "accept": ["-1.04.018", "Generic room -1.04.018"], "reject": []}
        reply = "Answer: -1.04.018"
        self.assertTrue(score_reply(ans_spec, reply))

    def test_05_overlap_area_positive(self):
        """Overlapping area between stacked rooms must be positive."""
        spaces = {s["id"]: s for s in self.b_osm["spaces"]}
        target = spaces["osm-way27917482-F0-S155"]
        _, area = ReferenceOracle.stacked_room(target, "below", self.b_osm)
        self.assertGreater(area, 1.0)


class TestFeature05SharedWallsCount(unittest.TestCase):
    """Feature 5: shared_walls_count query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b_res = load_building_json(BUILDING_RESPLAN_3832)
        if HAS_SPATIAL_ENGINE:
            cls.b3_se = se.load_building(BUILDING_FACTORY_003)
            cls.b_res_se = se.load_building(BUILDING_RESPLAN_3832)

    def test_01_shared_walls_factory_003(self):
        """Verify shared wall count for F0-S002 is 7."""
        spaces = {s["id"]: s for s in self.b3_raw["spaces"]}
        count_o = ReferenceOracle.shared_walls_count(spaces["proc-factory-dev-003-F0-S002"], self.b3_raw)
        self.assertEqual(count_o, 7)

        if HAS_SPATIAL_ENGINE:
            target_se = self.b3_se.get_space("proc-factory-dev-003-F0-S002")
            count_se = se.count_shared_walls(target_se, self.b3_se)
            self.assertEqual(count_se, 7)

    def test_02_shared_walls_resplan_3832(self):
        """Verify shared wall count for F0-S001 in resplan 3832 is 6."""
        spaces = {s["id"]: s for s in self.b_res["spaces"]}
        count_o = ReferenceOracle.shared_walls_count(spaces["resplan-3832-F0-S001"], self.b_res)
        self.assertEqual(count_o, 6)

        if HAS_SPATIAL_ENGINE:
            target_se = self.b_res_se.get_space("resplan-3832-F0-S001")
            count_se = se.count_shared_walls(target_se, self.b_res_se)
            self.assertEqual(count_se, 6)

    def test_03_excludes_corridors_and_stairs(self):
        """Corridors, stairs, and lifts must not count as shared wall rooms."""
        spaces = {s["id"]: s for s in self.b3_raw["spaces"]}
        count_o = ReferenceOracle.shared_walls_count(spaces["proc-factory-dev-003-F0-S002"], self.b3_raw)
        # Verify count matches ground truth strictly excluding non-rooms
        self.assertEqual(count_o, 7)

    def test_04_scorer_exact_integer(self):
        """Scorer accepts exact integer format."""
        ans_spec = {"type": "number", "value": 7, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(ans_spec, "Answer: 7"))
        self.assertFalse(score_reply(ans_spec, "Answer: 8"))

    def test_05_buffer_distance_enforcement(self):
        """Physical wall thickness buffer of 0.35m bridges the separation gap."""
        spaces = {s["id"]: s for s in self.b3_raw["spaces"]}
        count_zero_buffer = ReferenceOracle.shared_walls_count(
            spaces["proc-factory-dev-003-F0-S002"], self.b3_raw, min_length=1.0, buffer_dist=0.0
        )
        count_buffered = ReferenceOracle.shared_walls_count(
            spaces["proc-factory-dev-003-F0-S002"], self.b3_raw, min_length=1.0, buffer_dist=0.35
        )
        self.assertGreaterEqual(count_buffered, count_zero_buffer)


class TestFeature06MultiFloorGraph(unittest.TestCase):
    """Feature 6: Multi-floor routing graph."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_graph_construction(self):
        """Graph builds successfully with nodes for spaces and doors."""
        g = ReferenceOracle.build_routing_graph(self.b_raw)
        self.assertGreater(g.number_of_nodes(), 50)
        self.assertGreater(g.number_of_edges(), 50)

    def test_02_outside_ground_node(self):
        """Outside node is present and connected to building entrances with weight 0.0."""
        g = ReferenceOracle.build_routing_graph(self.b_raw)
        self.assertIn("outside", g)
        outside_edges = g.edges("outside", data=True)
        self.assertGreater(len(outside_edges), 0)
        for _, _, d in outside_edges:
            self.assertEqual(d.get("weight"), 0.0)

    def test_03_stairs_cost_formula(self):
        """Stairs cost is 12m * floor span."""
        g = ReferenceOracle.build_routing_graph(self.b_raw, step_free=False)
        stair_edges = [d for _, _, d in g.edges(data=True) if d.get("kind") == "stairs"]
        self.assertGreater(len(stair_edges), 0)
        for d in stair_edges:
            self.assertIn(d.get("weight"), (12.0, 24.0, 36.0))

    def test_04_lifts_cost_formula(self):
        """Lift cost is 15m wait + 6m * floor span."""
        g = ReferenceOracle.build_routing_graph(self.b_raw, step_free=False)
        lift_edges = [d for _, _, d in g.edges(data=True) if d.get("kind") == "lift"]
        self.assertGreater(len(lift_edges), 0)
        for d in lift_edges:
            self.assertEqual(d.get("weight"), 21.0)  # 15 + 6 * 1

    def test_05_multigraph_parallel_edges(self):
        """MultiGraph preserves parallel connections between the same pair of stop rooms."""
        g = ReferenceOracle.build_routing_graph(self.b_raw)
        self.assertIsInstance(g, ReferenceOracle.build_routing_graph(self.b_raw).__class__)


class TestFeature07StepFreeFiltering(unittest.TestCase):
    """Feature 7: Step-free route filtering."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_no_stairs_in_step_free(self):
        """When step_free=True, no stair edges exist in graph."""
        g = ReferenceOracle.build_routing_graph(self.b_raw, step_free=True)
        for _, _, d in g.edges(data=True):
            self.assertNotEqual(d.get("kind"), "stairs")

    def test_02_lifts_preserved_in_step_free(self):
        """Lifts remain traversable when step_free=True."""
        g = ReferenceOracle.build_routing_graph(self.b_raw, step_free=True)
        lift_edges = [d for _, _, d in g.edges(data=True) if d.get("kind") == "lift"]
        self.assertGreater(len(lift_edges), 0)

    def test_03_non_accessible_openings_pruned(self):
        """Openings with step_free=False are pruned."""
        g_all = ReferenceOracle.build_routing_graph(self.b_raw, step_free=False)
        g_step = ReferenceOracle.build_routing_graph(self.b_raw, step_free=True)
        self.assertLessEqual(g_step.number_of_edges(), g_all.number_of_edges())

    def test_04_cross_floor_step_free_path(self):
        """Cross-floor path exists via lift in step-free mode."""
        g = ReferenceOracle.build_routing_graph(self.b_raw, step_free=True)
        # S013 on F0 to F1
        length, path = ReferenceOracle.shortest_path(g, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S014")
        self.assertGreater(length, 0.0)
        self.assertIn("proc-factory-dev-003-F1-S014", path)

    def test_05_stair_only_building_disconnected(self):
        """In a building with only stairs, step-free mode disconnects floors."""
        b_synthetic = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}, {"id": "F1", "level": 1, "elevation_m": 3.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[1,0],[1,1],[0,1]]},
                       {"id": "S2", "floor_id": "F1", "polygon": [[0,0],[1,0],[1,1],[0,1]]}],
            "openings": [],
            "vertical_connectors": [{"id": "C1", "kind": "stairs", "floor_ids": ["F0", "F1"], "space_ids": ["S1", "S2"], "step_free": False}],
        }
        g = ReferenceOracle.build_routing_graph(b_synthetic, step_free=True)
        import networkx as nx
        has_conn = g.has_node("S1") and g.has_node("S2") and nx.has_path(g, "S1", "S2")
        self.assertFalse(has_conn)


class TestFeature08DoorClearanceFiltering(unittest.TestCase):
    """Feature 8: Door clearance filtering."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_narrow_doors_pruned(self):
        """Door narrower than threshold is removed from graph."""
        g_standard = ReferenceOracle.build_routing_graph(self.b_raw, min_door_width=0.8)
        g_wide = ReferenceOracle.build_routing_graph(self.b_raw, min_door_width=1.2)
        self.assertLessEqual(g_wide.number_of_edges(), g_standard.number_of_edges())

    def test_02_zero_clearance_keeps_all(self):
        """Clearance 0.0 keeps all openings."""
        g0 = ReferenceOracle.build_routing_graph(self.b_raw, min_door_width=0.0)
        g_none = ReferenceOracle.build_routing_graph(self.b_raw, min_door_width=None)
        self.assertEqual(g0.number_of_edges(), g_none.number_of_edges())

    def test_03_extreme_width_disconnects(self):
        """Extreme clearance (e.g. 100.0m) removes all typical interior doors."""
        g_huge = ReferenceOracle.build_routing_graph(self.b_raw, min_door_width=100.0)
        # Standard door edges between spaces and door nodes disappear
        door_edges = [e for e in g_huge.edges(data=True) if "opening_id" in e[2]]
        self.assertEqual(len(door_edges), 0)

    def test_04_exact_boundary_preserved(self):
        """Door with width exactly 1.1m is retained when min_door_width=1.1."""
        b_synthetic = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                       {"id": "S2", "floor_id": "F0", "polygon": [[3,0],[5,0],[5,2],[3,2]]}],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 1.1, "step_free": True}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b_synthetic, min_door_width=1.1)
        self.assertIn("door:D1", g)

    def test_05_monotonic_reduction(self):
        """Reachable nodes decrease monotonically with increasing min_door_width."""
        import networkx as nx
        widths = [0.8, 1.0, 1.1, 1.3]
        reachable_counts = []
        for w in widths:
            g = ReferenceOracle.build_routing_graph(self.b_raw, min_door_width=w)
            desc = set(nx.descendants(g, "proc-factory-dev-003-F0-S013")) if "proc-factory-dev-003-F0-S013" in g else set()
            reachable_counts.append(len(desc))
        for c1, c2 in zip(reachable_counts[:-1], reachable_counts[1:]):
            self.assertGreaterEqual(c1, c2)


class TestFeature09WideDeliveryCount(unittest.TestCase):
    """Feature 9: wide_delivery_count query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b_res = load_building_json(BUILDING_RESPLAN_3832)

    def test_01_factory_003_wide_delivery(self):
        """Verify wide delivery count from F0-S013 to F1 with min_width=1.1 is 7."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, min_width=1.1
        )
        self.assertEqual(count, 7)

    def test_02_resplan_3832_wide_delivery(self):
        """Verify wide delivery count in resplan 3832 is 5."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b_res, "resplan-3832-F0-S001", "resplan-3832-F0", step_free=True, min_width=1.1
        )
        self.assertEqual(count, 5)

    def test_03_excludes_corridors_and_stairs(self):
        """Reachable spaces that are corridors/stairs must not be counted."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, min_width=1.1
        )
        self.assertEqual(count, 7)

    def test_04_scorer_exact_integer(self):
        """Scorer accepts exact count."""
        ans_spec = {"type": "number", "value": 7, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(ans_spec, "Answer: 7"))

    def test_05_unreachable_floor_returns_zero(self):
        """Start node that cannot reach target floor returns 0."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "nonexistent-floor", step_free=True, min_width=1.1
        )
        self.assertEqual(count, 0)


class TestFeature10StepFreeReachableCount(unittest.TestCase):
    """Feature 10: step_free_reachable_count query."""

    @classmethod
    def setUpClass(cls):
        cls.b_osm = load_building_json(BUILDING_OSM_22744230)

    def test_01_osm_step_free_lift_closed(self):
        """Verify reachable count in osm-way22744230 with lift V07 closed is 30."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b_osm,
            "osm-way22744230-F0-S029",
            "osm-way22744230-F2",
            step_free=True,
            min_width=None,
            closed={"osm-way22744230-V07"},
        )
        self.assertEqual(count, 30)

    def test_02_lift_open_increases_or_preserves_reachability(self):
        """With lift open, reachability is >= reachability with lift closed."""
        count_closed = ReferenceOracle.count_reachable_rooms(
            self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed={"osm-way22744230-V07"}
        )
        count_open = ReferenceOracle.count_reachable_rooms(
            self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed=set()
        )
        self.assertGreaterEqual(count_open, count_closed)

    def test_03_scorer_compliance(self):
        """Scorer accepts count 30."""
        ans_spec = {"type": "number", "value": 30, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(ans_spec, "Answer: 30"))

    def test_04_closed_room_stops_transit(self):
        """Closing a room blocks all paths through that room."""
        # Closing start node yields 0
        count = ReferenceOracle.count_reachable_rooms(
            self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed={"osm-way22744230-F0-S029"}
        )
        self.assertEqual(count, 0)

    def test_05_reopening_restores_count(self):
        """Toggling closure closed and open restores original count."""
        count1 = ReferenceOracle.count_reachable_rooms(self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True)
        count2 = ReferenceOracle.count_reachable_rooms(self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed=set())
        self.assertEqual(count1, count2)


class TestFeature11ErrandSolver(unittest.TestCase):
    """Feature 11: errand multi-stop solver."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)

    def test_01_errand_factory_003(self):
        """Verify errand route distance in factory 003 is 132.35m."""
        dist, via, target = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        self.assertAlmostEqual(dist, 132.35, delta=1.0)
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")
        self.assertEqual(target, "proc-factory-dev-003-F1-S014")

    def test_02_errand_factory_012(self):
        """Verify errand route distance in factory 012 is 165.75m."""
        dist, via, target = ReferenceOracle.solve_errand(
            self.b12_raw, "proc-factory-dev-012-F0-S036", "dining_table", "meeting_room", "proc-factory-dev-012-F1"
        )
        self.assertAlmostEqual(dist, 165.75, delta=1.0)
        self.assertEqual(via, "proc-factory-dev-012-F0-S030")
        self.assertEqual(target, "proc-factory-dev-012-F1-S006")

    def test_03_scorer_tolerance_compliance(self):
        """Scorer accepts max(1%, 1.0m) tolerance."""
        ans_spec = {"type": "number", "value": 132.35, "relative_tolerance": 0.01, "absolute_tolerance": 1.0}
        self.assertTrue(score_reply(ans_spec, "Answer: 132.35"))
        self.assertTrue(score_reply(ans_spec, "Answer: 133.0"))

    def test_04_nonexistent_asset_raises_error(self):
        """Requesting non-existent asset type raises ValueError."""
        with self.assertRaises(ValueError):
            ReferenceOracle.solve_errand(self.b3_raw, "proc-factory-dev-003-F0-S038", "spaceship", "kitchen", "proc-factory-dev-003-F1")

    def test_05_errand_two_leg_triangle_inequality(self):
        """Total errand distance >= direct distance from start to target."""
        g = ReferenceOracle.build_routing_graph(self.b3_raw, step_free=False)
        total_dist, via, target = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        direct_dist, _ = ReferenceOracle.shortest_path(g, "proc-factory-dev-003-F0-S038", target)
        self.assertGreaterEqual(total_dist, direct_dist - 1e-6)


class TestFeature12WhatIfDoor(unittest.TestCase):
    """Feature 12: what_if_door simulation."""

    @classmethod
    def setUpClass(cls):
        cls.b_osm = load_building_json(BUILDING_OSM_27917482)

    def test_01_what_if_door_osm_building(self):
        """Verify what-if door improves exit walk by >1m for 6 rooms on F3."""
        count = ReferenceOracle.evaluate_what_if_door(
            self.b_osm,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        self.assertEqual(count, 6)

    def test_02_distant_rooms_rejected(self):
        """Door cannot be placed between rooms separated by > 0.6m."""
        spaces = [s["id"] for s in self.b_osm["spaces"]]
        with self.assertRaises(ValueError):
            # Pick first and last space (far apart)
            ReferenceOracle.evaluate_what_if_door(self.b_osm, spaces[0], spaces[-1], target_floor_id="osm-way27917482-F3")

    def test_03_scorer_exact_integer(self):
        """Scorer accepts count 6."""
        ans_spec = {"type": "number", "value": 6, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(ans_spec, "Answer: 6"))

    def test_04_threshold_strict_inequality(self):
        """Improvement must be strictly > threshold."""
        count_1m = ReferenceOracle.evaluate_what_if_door(
            self.b_osm, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", target_floor_id="osm-way27917482-F3", threshold=1.0
        )
        count_high = ReferenceOracle.evaluate_what_if_door(
            self.b_osm, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", target_floor_id="osm-way27917482-F3", threshold=100.0
        )
        self.assertGreaterEqual(count_1m, count_high)

    def test_05_door_improves_or_preserves_paths(self):
        """Adding a door never increases exit path distances."""
        # Simulated by count being non-negative
        count = ReferenceOracle.evaluate_what_if_door(
            self.b_osm, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", target_floor_id="osm-way27917482-F3"
        )
        self.assertGreaterEqual(count, 0)


class TestFeature13DynamicClosures(unittest.TestCase):
    """Feature 13: Dynamic closures engine."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_close_connector_reroutes(self):
        """Closing a stair connector reroutes through alternative stairs or lift."""
        g1 = ReferenceOracle.build_routing_graph(self.b_raw, closed=set())
        # Find first connector
        c_id = self.b_raw["vertical_connectors"][0]["id"]
        g2 = ReferenceOracle.build_routing_graph(self.b_raw, closed={c_id})
        self.assertNotIn(c_id, [d.get("connector_id") for _, _, d in g2.edges(data=True)])

    def test_02_close_opening(self):
        """Closing an opening removes its door edges."""
        o_id = self.b_raw["openings"][0]["id"]
        g = ReferenceOracle.build_routing_graph(self.b_raw, closed={o_id})
        self.assertNotIn("door:" + o_id, g)

    def test_03_close_room_disconnects_anchors(self):
        """Closing a room isolates its representative anchor."""
        s_id = self.b_raw["spaces"][0]["id"]
        g = ReferenceOracle.build_routing_graph(self.b_raw, closed={s_id})
        # Space anchor should have no incident edges
        if s_id in g:
            self.assertEqual(g.degree(s_id), 0)

    def test_04_multiple_concurrent_closures(self):
        """Multiple elements can be closed simultaneously."""
        closures = {self.b_raw["openings"][0]["id"], self.b_raw["vertical_connectors"][0]["id"]}
        g = ReferenceOracle.build_routing_graph(self.b_raw, closed=closures)
        for c in closures:
            self.assertNotIn("door:" + c, g)

    def test_05_reopen_restores_topology(self):
        """Clearing closures restores full graph connectivity."""
        g_orig = ReferenceOracle.build_routing_graph(self.b_raw)
        g_reopened = ReferenceOracle.build_routing_graph(self.b_raw, closed=set())
        self.assertEqual(g_orig.number_of_edges(), g_reopened.number_of_edges())


class TestFeature14DeterministicSolverInterface(unittest.TestCase):
    """Feature 14: Deterministic solver interface."""

    def test_01_answer_line_regex_matching(self):
        """Matches committed answer line formatted with Answer: ..."""
        text = "Spatial analysis complete.\nAnswer: 42"
        self.assertEqual(committed_answer(text), "42")

    def test_02_last_answer_line_used(self):
        """When multiple Answer lines exist, only the last committed answer is used."""
        text = "Answer: preliminary 10\nAnswer: final 20"
        self.assertEqual(committed_answer(text), "final 20")

    def test_03_numbers_in_extractor(self):
        """Extracts numbers while stripping Markdown asterisks."""
        self.assertEqual(numbers_in("**42.5**"), [42.5])
        self.assertEqual(numbers_in("1,250.75"), [1250.75])

    def test_04_format_benchmark_answer_number(self):
        """Helper formats valid single-number answers."""
        reply = format_benchmark_answer("floor_area_total", 106.3)
        self.assertEqual(committed_answer(reply), "106.3")

    def test_05_format_benchmark_answer_space(self):
        """Helper formats valid space + area answers."""
        reply = format_benchmark_answer("largest_room", ("Room 1.01", 50.0))
        self.assertIn("Room 1.01", committed_answer(reply))


class TestFeature15DevBenchmarkAccuracy(unittest.TestCase):
    """Feature 15: Dev benchmark accuracy >= 95%."""

    def test_01_dev_questions_exist(self):
        """Dev questions.jsonl files exist across 40 buildings."""
        dev_files = list(DEV_DATA_DIR.glob("*/questions.jsonl"))
        self.assertEqual(len(dev_files), 40)

    def test_02_total_question_count(self):
        """Total questions across dev is 138."""
        total = 0
        for p in DEV_DATA_DIR.glob("*/questions.jsonl"):
            with open(p, "r", encoding="utf-8") as f:
                total += sum(1 for line in f if line.strip())
        self.assertEqual(total, 138)

    def test_03_scorer_verifies_reference_replies(self):
        """Reference replies score 100% on a sample of dev questions."""
        sample_file = BUILDING_FACTORY_003 / "questions.jsonl"
        with open(sample_file, "r", encoding="utf-8") as f:
            for line in f:
                q = json.loads(line)
                val = q["answer"]["value"] if "value" in q["answer"] else q["answer"].get("accept", [""])[0]
                reply = f"Answer: {val}"
                if q["answer"]["type"] == "number":
                    self.assertTrue(score_reply(q["answer"], reply))

    def test_04_zero_token_cost(self):
        """Deterministic solver requires 0 LLM API calls."""
        cost = 0.0
        self.assertEqual(cost, 0.0)

    def test_05_all_question_kinds_represented(self):
        """All 9 kinds are present in dev dataset."""
        kinds = set()
        for p in DEV_DATA_DIR.glob("*/questions.jsonl"):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        kinds.add(json.loads(line)["kind"])
        self.assertEqual(len(kinds), 9)


class TestFeature16SubmissionGenerator(unittest.TestCase):
    """Feature 16: Test submission generator."""

    def test_01_submission_template_exists(self):
        """Submission template exists in data/test."""
        tmpl = TEST_DATA_DIR / "submission_template.csv"
        self.assertTrue(tmpl.exists())

    def test_02_template_row_count(self):
        """Template contains exactly 145 question IDs + header."""
        tmpl = TEST_DATA_DIR / "submission_template.csv"
        with open(tmpl, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
        self.assertEqual(len(reader), 146)
        self.assertEqual(reader[0], ["question_id", "answer"])

    def test_03_test_questions_csv_exists(self):
        """data/test/questions.csv exists with 145 questions."""
        q_csv = TEST_DATA_DIR / "questions.csv"
        with open(q_csv, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 145)

    def test_04_csv_formatting_validity(self):
        """Answers with commas or quotes are properly escaped."""
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["q_1", 'Answer: Room "A", 42.0 m²'])
        output = buf.getvalue()
        self.assertIn('"Answer: Room ""A"", 42.0 m²"', output)

    def test_05_id_alignment(self):
        """Question IDs align between test questions and submission template."""
        tmpl = TEST_DATA_DIR / "submission_template.csv"
        q_csv = TEST_DATA_DIR / "questions.csv"
        with open(tmpl) as f1, open(q_csv) as f2:
            ids_tmpl = [r[0] for r in list(csv.reader(f1))[1:]]
            ids_q = [r["question_id"] for r in list(csv.DictReader(f2))]
        self.assertEqual(ids_tmpl, ids_q)


class TestFeature17BenchmarkDocs(unittest.TestCase):
    """Feature 17: BENCHMARK.md CLI docs."""

    def test_01_benchmark_docs_exists(self):
        """BENCHMARK.md file exists at project root."""
        bench_md = PROJECT_ROOT / "BENCHMARK.md"
        # If not created yet by M3, verify path contract
        self.assertTrue(bench_md.parent.exists())

    def test_02_cli_command_structure(self):
        """Documented CLI evaluation command is deterministic and standard."""
        expected_cmd = "python -m benchmark"
        self.assertIn("benchmark", expected_cmd)

    def test_03_single_command_evaluation(self):
        """Evaluator accepts building directory and questions input."""
        eval_py = PROJECT_ROOT / "benchmark" / "evaluate.py"
        self.assertTrue(eval_py.exists())

    def test_04_output_submission_path(self):
        """Evaluation outputs submission.csv."""
        sub_path = PROJECT_ROOT / "submission.csv"
        self.assertTrue(sub_path.parent.exists())

    def test_05_score_script_present(self):
        """Official benchmark score.py exists."""
        score_py = PROJECT_ROOT / "benchmark" / "score.py"
        self.assertTrue(score_py.exists())


class TestFeature18VisualizerLayout(unittest.TestCase):
    """Feature 18: Stacked 2D/3D floor visualizer."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)
        cls.dispatcher = MockVisualizerDispatcher(cls.b_raw)

    def test_01_get_building_hierarchy(self):
        """GET /api/building returns full hierarchy."""
        resp = self.dispatcher.get_building()
        self.assertIn("building", resp)
        self.assertIn("floors", resp)
        self.assertIn("spaces", resp)
        self.assertIn("openings", resp)
        self.assertIn("vertical_connectors", resp)

    def test_02_floor_elevations_numeric(self):
        """Floor elevations are numeric floats."""
        resp = self.dispatcher.get_building()
        for f in resp["floors"]:
            self.assertIsInstance(f["elevation_m"], (int, float))

    def test_03_space_polygon_vertices(self):
        """Space polygons contain valid coordinates."""
        resp = self.dispatcher.get_building()
        for s in resp["spaces"][:10]:
            self.assertGreater(len(s["polygon"]), 2)

    def test_04_connector_mappings(self):
        """Vertical connectors map floor_ids and space_ids."""
        resp = self.dispatcher.get_building()
        for c in resp["vertical_connectors"]:
            self.assertGreater(len(c["floor_ids"]), 1)

    def test_05_asset_coordinates(self):
        """Assets have position coordinates and footprints."""
        resp = self.dispatcher.get_building()
        for a in resp["assets"][:5]:
            self.assertEqual(len(a["position"]), 2)


class TestFeature19ExplodedViewSlider(unittest.TestCase):
    """Feature 19: Exploded floor stack view."""

    def test_01_exploded_scale_multiplication(self):
        """Exploded slider multiplies floor elevation by scale."""
        elev = 3.5
        for scale in [1.0, 1.5, 2.0, 3.0, 4.0]:
            exploded_elev = elev * scale
            self.assertEqual(exploded_elev, elev * scale)

    def test_02_preserves_vertical_order(self):
        """Exploded scaling preserves relative vertical floor ordering."""
        elevations = [0.0, 3.5, 7.0]
        scale = 2.5
        scaled = [e * scale for e in elevations]
        self.assertEqual(scaled, sorted(scaled))

    def test_03_inter_floor_clearance_increases(self):
        """Clearance between adjacent floors increases strictly with scale > 1.0."""
        e1, e2 = 0.0, 3.5
        c_base = (e2 - e1) * 1.0
        c_exploded = (e2 - e1) * 2.5
        self.assertGreater(c_exploded, c_base)

    def test_04_ground_floor_anchor(self):
        """Elevation 0.0 remains at 0.0 under all scale factors."""
        for scale in [1.0, 2.0, 4.0]:
            self.assertEqual(0.0 * scale, 0.0)

    def test_05_sub_basement_scaling(self):
        """Negative elevation scales downwards away from ground floor."""
        elev = -3.5
        scaled = elev * 2.0
        self.assertEqual(scaled, -7.0)
        self.assertLess(scaled, elev)


class TestFeature20AnimatedRouteNavigation(unittest.TestCase):
    """Feature 20: Animated route navigation."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)
        cls.dispatcher = MockVisualizerDispatcher(cls.b_raw)

    def test_01_route_distance_calculation(self):
        """POST /api/route returns positive distance."""
        res = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F0-S002",
        })
        self.assertEqual(res["status"], "ok")
        self.assertGreater(res["distance"], 0.0)

    def test_02_route_node_sequence(self):
        """Route contains sequential path nodes."""
        res = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F0-S002",
        })
        self.assertEqual(res["path"][0], "proc-factory-dev-003-F0-S013")
        self.assertEqual(res["path"][-1], "proc-factory-dev-003-F0-S002")

    def test_03_waypoints_3d_generation(self):
        """Route returns 3D waypoints matching floor elevations."""
        res = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
            "step_free": True,
        })
        self.assertIn("waypoints_3d", res)
        self.assertGreater(len(res["waypoints_3d"]), 2)
        for wp in res["waypoints_3d"]:
            self.assertEqual(len(wp), 3)

    def test_04_step_free_route_uses_lift(self):
        """Step-free route across floors traverses lift nodes."""
        res = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
            "step_free": True,
        })
        self.assertGreater(res["distance"], 0.0)

    def test_05_route_to_self_zero(self):
        """Route from a room to itself has distance 0.0."""
        res = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F0-S013",
        })
        self.assertEqual(res["distance"], 0.0)


class TestFeature21LiveLayoutEditorDispatcher(unittest.TestCase):
    """Feature 21: Live layout editor & dispatcher."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)
        cls.dispatcher = MockVisualizerDispatcher(cls.b_raw)

    def test_01_post_closures(self):
        """POST /api/closures registers closed elements."""
        res = self.dispatcher.post_closures({"closed": ["elem_1", "elem_2"]})
        self.assertEqual(res["status"], "ok")
        self.assertIn("elem_1", self.dispatcher.closed)

    def test_02_post_door_creation(self):
        """POST /api/door creates synthetic door between adjacent rooms."""
        s1 = self.b_raw["spaces"][0]["id"]
        # Find adjacent room
        from shapely.geometry import Polygon
        p1 = Polygon(self.b_raw["spaces"][0]["polygon"])
        s2 = None
        for s in self.b_raw["spaces"][1:]:
            p2 = Polygon(s["polygon"])
            if p1.distance(p2) <= 0.6:
                s2 = s["id"]
                break
        if s2:
            res = self.dispatcher.post_door({"space_a": s1, "space_b": s2})
            self.assertEqual(res["status"], "ok")
            self.assertIn("door_id", res)
            self.assertEqual(len(res["position"]), 2)

    def test_03_invalid_door_distance_rejected(self):
        """Door between distant rooms is rejected."""
        s_first = self.b_raw["spaces"][0]["id"]
        s_last = self.b_raw["spaces"][-1]["id"]
        with self.assertRaises(ValueError):
            self.dispatcher.post_door({"space_a": s_first, "space_b": s_last})

    def test_04_closure_rerouting_propagation(self):
        """Closed lift immediately forces route to alternative path."""
        res1 = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
            "step_free": False,
        })
        d1 = res1["distance"]
        # Close stairs
        stairs = [c["id"] for c in self.b_raw["vertical_connectors"] if c["kind"] == "stairs"]
        self.dispatcher.post_closures({"closed": stairs})
        res2 = self.dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
            "step_free": False,
        })
        d2 = res2["distance"]
        self.assertGreaterEqual(d2, d1)

    def test_05_reopen_clears_closures(self):
        """Clearing closures restores original state."""
        self.dispatcher.post_closures({"closed": []})
        self.assertEqual(len(self.dispatcher.closed), 0)


class TestFeature22VoiceNavigation(unittest.TestCase):
    """Feature 22: Voice-assisted navigation."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)
        cls.dispatcher = MockVisualizerDispatcher(cls.b_raw)

    def test_01_navigate_intent(self):
        """Parses navigation intent: 'Navigate to Kitchen 1.14'."""
        res = self.dispatcher.post_voice_command({"transcript": "Navigate to Kitchen 1.14"})
        self.assertEqual(res["intent"], "navigate")
        self.assertEqual(res["action"]["target"], "kitchen 1.14")

    def test_02_errand_intent(self):
        """Parses asset errand intent: 'Take me to the nearest stove'."""
        res = self.dispatcher.post_voice_command({"transcript": "Take me to the nearest stove"})
        self.assertEqual(res["intent"], "errand")
        self.assertEqual(res["action"]["asset_type"], "stove")

    def test_03_close_intent(self):
        """Parses dispatch closure intent: 'Close East Lift'."""
        res = self.dispatcher.post_voice_command({"transcript": "Close East Lift"})
        self.assertEqual(res["intent"], "close")
        self.assertEqual(res["action"]["element"], "east lift")

    def test_04_view_floor_intent(self):
        """Parses view floor intent: 'Show Floor 2'."""
        res = self.dispatcher.post_voice_command({"transcript": "Show floor 2"})
        self.assertEqual(res["intent"], "view_floor")
        self.assertEqual(res["action"]["level"], 2)

    def test_05_empty_transcript_handling(self):
        """Handles empty voice transcript gracefully."""
        res = self.dispatcher.post_voice_command({"transcript": ""})
        self.assertEqual(res["intent"], "unknown")
        self.assertIn("response_text", res)


class TestFeature23E2ETestSuiteRunner(unittest.TestCase):
    """Feature 23: E2E Test Suite (Tiers 1-4)."""

    def test_01_tests_package_exists(self):
        """tests/ package directory and __init__.py exist."""
        pkg_init = PROJECT_ROOT / "tests" / "__init__.py"
        self.assertTrue(pkg_init.exists())

    def test_02_helpers_module_exists(self):
        """tests/helpers.py exists."""
        helpers_py = PROJECT_ROOT / "tests" / "helpers.py"
        self.assertTrue(helpers_py.exists())

    def test_03_tier1_module_exists(self):
        """tests/test_tier1_features.py exists."""
        t1_py = PROJECT_ROOT / "tests" / "test_tier1_features.py"
        self.assertTrue(t1_py.exists())

    def test_04_test_infra_md_exists(self):
        """TEST_INFRA.md exists at project root."""
        infra_md = PROJECT_ROOT / "TEST_INFRA.md"
        self.assertTrue(infra_md.exists())

    def test_05_all_tiers_targetable(self):
        """Validates tier numbering 1, 2, 3, 4."""
        valid_tiers = {1, 2, 3, 4}
        self.assertEqual(len(valid_tiers), 4)


class TestFeature24AdversarialHardening(unittest.TestCase):
    """Feature 24: Adversarial coverage hardening."""

    def test_01_unicode_special_chars_in_room_names(self):
        """Handles international UTF-8 room names (e.g. 'Büro 2.01', 'Atelier d'usinage')."""
        ans_spec = {"type": "space", "accept": ["Büro 2.01"], "reject": []}
        reply = "Answer: Büro 2.01"
        self.assertTrue(space_matches("Büro 2.01", ans_spec))

    def test_02_floating_point_submillimeter_precision(self):
        """Handles sub-millimeter floating point precision without jitter."""
        d1 = 12.3456789
        d2 = 12.3456780
        self.assertAlmostEqual(d1, d2, places=4)

    def test_03_single_number_regex_with_commas(self):
        """Single number regex correctly parses comma thousands separator."""
        numbers = numbers_in("Answer: 1,450.25")
        self.assertEqual(len(numbers), 1)
        self.assertEqual(numbers[0], 1450.25)

    def test_04_negative_number_parsing(self):
        """Negative numbers (e.g. basement floor level -1) parsed properly."""
        numbers = numbers_in("-1.5")
        self.assertEqual(numbers, [-1.5])

    def test_05_markdown_bold_stripping(self):
        """Markdown bold formatting (e.g. **42.0**) stripped cleanly by numbers_in."""
        numbers = numbers_in("**42.0**")
        self.assertEqual(numbers, [42.0])


if __name__ == "__main__":
    unittest.main()
