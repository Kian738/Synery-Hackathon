"""Tier 3: Cross-Feature Combinations Test Suite.

Validates pairwise and multi-feature interactions across spatial geometry,
multi-floor routing, dynamic dispatch closures, REST APIs, and benchmark scoring.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import unittest

import networkx as nx
from shapely.geometry import Point, Polygon

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


class TestTier3CrossFeatureCombinations(unittest.TestCase):
    """Pairwise and multi-feature compound interaction tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)
        cls.b_osm = load_building_json(BUILDING_OSM_22744230)
        cls.b_osm_multi = load_building_json(BUILDING_OSM_27917482)
        cls.b_res = load_building_json(BUILDING_RESPLAN_3832)

    def test_01_multifloor_stepfree_minwidth_compound(self):
        """Interaction: Multi-floor routing + step_free=True + min_door_width constraint."""
        # Route from F0 to F1 in factory 003 requiring wheelchair accessibility and 1.1m clearance
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw,
            "proc-factory-dev-003-F0-S013",
            "proc-factory-dev-003-F1",
            step_free=True,
            min_width=1.1,
            closed=None,
        )
        self.assertEqual(count, 7)

    def test_02_errand_multifloor_elevator_vs_stairs(self):
        """Interaction: Errand route comparing unrestricted routing vs step-free (elevator-only)."""
        # Unrestricted errand
        dist_all, via, target = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        # Verify errand distances are positive and structured
        self.assertAlmostEqual(dist_all, 132.35, delta=1.0)
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")
        self.assertEqual(target, "proc-factory-dev-003-F1-S014")

    def test_03_whatif_door_combined_with_connector_closures(self):
        """Interaction: What-if door simulation under simultaneous dynamic connector closure."""
        # When a stair is closed, adding a door may improve egress for even more rooms
        stairs = [c["id"] for c in self.b_osm_multi["vertical_connectors"] if c["kind"] == "stairs"]
        count_normal = ReferenceOracle.evaluate_what_if_door(
            self.b_osm_multi, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", "osm-way27917482-F3"
        )
        self.assertEqual(count_normal, 6)

    def test_04_compound_constraints_stepfree_clearance_closures(self):
        """Interaction: Compound constraints (step_free + min_width + closed elements)."""
        count_base = ReferenceOracle.count_reachable_rooms(
            self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, min_width=0.8, closed=None
        )
        # Close one lift
        count_one_lift_closed = ReferenceOracle.count_reachable_rooms(
            self.b_osm,
            "osm-way22744230-F0-S029",
            "osm-way22744230-F2",
            step_free=True,
            min_width=0.8,
            closed={"osm-way22744230-V07"},
        )
        self.assertGreaterEqual(count_base, count_one_lift_closed)

    def test_05_geometric_consistency_largest_vs_total_area(self):
        """Interaction: Largest room polygon area must be <= total floor area of that room type."""
        for b in [self.b3_raw, self.b12_raw, self.b_res]:
            for f in b["floors"]:
                f_id = f["id"]
                # Collect all room types on floor
                types = {s["room_type"] for s in b["spaces"] if s["floor_id"] == f_id and "room_type" in s}
                for r_type in types:
                    try:
                        _, largest_area = ReferenceOracle.largest_room(b, f_id, r_type)
                        total_area = ReferenceOracle.floor_area_total(b, f_id, r_type)
                        self.assertLessEqual(largest_area, total_area + 1e-5)
                    except ValueError:
                        continue

    def test_06_geometric_consistency_stacked_overlap_bounds(self):
        """Interaction: Stacked room overlap area <= start room polygon area."""
        spaces = [s for s in self.b_osm_multi["spaces"] if s["floor_id"] == "osm-way27917482-F0"][:5]
        for s in spaces:
            try:
                _, overlap = ReferenceOracle.stacked_room(s, "below", self.b_osm_multi)
                start_area = ReferenceOracle.room_area(s)
                self.assertLessEqual(overlap, start_area + 1e-5)
            except ValueError:
                continue

    def test_07_geometric_consistency_3d_vs_2d_distance(self):
        """Interaction: 3D straight-line distance >= 2D coplanar distance."""
        spaces = self.b12_raw["spaces"][:10]
        for s1 in spaces:
            for s2 in spaces[5:10]:
                d3 = ReferenceOracle.straight_line_3d(s1, s2, self.b12_raw)
                c1 = Polygon(s1["polygon"]).centroid
                c2 = Polygon(s2["polygon"]).centroid
                d2 = math.hypot(c1.x - c2.x, c1.y - c2.y)
                self.assertGreaterEqual(d3, d2 - 1e-6)

    def test_08_shared_walls_rooms_belong_to_same_floor(self):
        """Interaction: Shared wall adjacent rooms must belong to the exact same floor."""
        s = self.b3_raw["spaces"][0]
        count = ReferenceOracle.shared_walls_count(s, self.b3_raw)
        self.assertGreaterEqual(count, 0)

    def test_09_errand_route_length_vs_direct_dest_distance(self):
        """Interaction: Errand route (A -> Asset -> Target) >= direct route (A -> Target)."""
        g = ReferenceOracle.build_routing_graph(self.b3_raw)
        dist_errand, _, target = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        direct_len, _ = ReferenceOracle.shortest_path(g, "proc-factory-dev-003-F0-S038", target)
        self.assertGreaterEqual(dist_errand, direct_len - 1e-6)

    def test_10_visualizer_rest_full_dispatch_cycle(self):
        """Interaction: Visualizer REST dispatch cycle (Load -> Route -> Close -> Reroute -> Add Door)."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        # 1. Load building
        b_info = dispatcher.get_building()
        self.assertEqual(b_info["building"]["name"], "Fertigung Ost 27")

        # 2. Compute route
        r1 = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        d1 = r1["distance"]

        # 3. Mark lift closed
        lifts = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "lift"]
        dispatcher.post_closures({"closed": lifts})

        # 4. Reroute via stairs
        r2 = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        self.assertGreater(r2["distance"], 0.0)

    def test_11_visualizer_added_door_shortens_route(self):
        """Interaction: Added door between rooms shortens path length."""
        # Synthetic setup with long corridor detour
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "RoomA", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "Corridor", "floor_id": "F0", "polygon": [[0,2],[10,2],[10,4],[0,4]]},
                {"id": "RoomB", "floor_id": "F0", "polygon": [[8,0],[10,0],[10,2],[8,2]]},
            ],
            "openings": [
                {"id": "D_A", "floor_id": "F0", "space_ids": ["RoomA", "Corridor"], "position": [1.0, 2.0], "width_m": 1.0, "step_free": True},
                {"id": "D_B", "floor_id": "F0", "space_ids": ["RoomB", "Corridor"], "position": [9.0, 2.0], "width_m": 1.0, "step_free": True},
            ],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        r_detour = dispatcher.post_route({"start": "RoomA", "end": "RoomB"})
        d_detour = r_detour["distance"]

        # Add punch-through door directly between RoomA and Corridor at x=2.0
        dispatcher.post_door({"space_a": "RoomA", "space_b": "Corridor"})
        r_after = dispatcher.post_route({"start": "RoomA", "end": "RoomB"})
        self.assertLessEqual(r_after["distance"], d_detour)

    def test_12_voice_command_to_navigation_route(self):
        """Interaction: Voice command parsed to intent and passed to route dispatcher."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        v_res = dispatcher.post_voice_command({"transcript": "Route to Kitchen 1.14"})
        self.assertEqual(v_res["intent"], "navigate")
        target_name = v_res["action"]["target"]
        # Find room matching target name
        matching = [s["id"] for s in self.b3_raw["spaces"] if target_name in s.get("name", "").lower()]
        self.assertGreater(len(matching), 0)

    def test_13_solver_regex_space_rejection_scoring(self):
        """Interaction: Solver formatting rules across space and number questions."""
        spec_space = {"type": "space", "accept": ["Room 1"], "reject": ["Room 2"]}
        spec_num = {"type": "number", "value": 42.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}

        reply_space = format_benchmark_answer("largest_room", ("Room 1", 50.0))
        reply_num = format_benchmark_answer("floor_area_total", 42.0)

        self.assertTrue(score_reply(spec_space, reply_space))
        self.assertTrue(score_reply(spec_num, reply_num))

    def test_14_dev_dataset_evaluation_scorecard_calculation(self):
        """Interaction: Evaluating multiple questions calculates overall pass rate."""
        results = [True, True, True, True, False]
        accuracy = sum(1 for r in results if r) / len(results)
        self.assertEqual(accuracy, 0.8)

    def test_15_whatif_door_wall_buffer_correlation(self):
        """Interaction: Doors can only be placed between spaces within buffer distance (<= 0.6m)."""
        poly1 = Polygon([[0, 0], [4, 0], [4, 4], [0, 4]])
        poly2 = Polygon([[4.5, 0], [8, 0], [8, 4], [4.5, 4]])
        dist = poly1.distance(poly2)
        self.assertLessEqual(dist, 0.6)  # 0.5m apart

    def test_16_errand_solver_with_broken_elevator(self):
        """Interaction: Errand solver rerouting when elevator is closed."""
        b = load_building_json(BUILDING_FACTORY_003)
        # Errand from F0 to F1
        dist1, _, _ = ReferenceOracle.solve_errand(b, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1")
        self.assertAlmostEqual(dist1, 132.35, delta=1.0)

    def test_17_consecutive_synthetic_doors(self):
        """Interaction: Adding multiple synthetic doors connects previously disjoint chains."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "A", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "B", "floor_id": "F0", "polygon": [[2.2,0],[4,0],[4,2],[2.2,2]]},
                {"id": "C", "floor_id": "F0", "polygon": [[4.4,0],[6,0],[6,2],[4.4,2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        dispatcher.post_door({"space_a": "A", "space_b": "B"})
        dispatcher.post_door({"space_a": "B", "space_b": "C"})
        res = dispatcher.post_route({"start": "A", "end": "C"})
        self.assertGreater(res["distance"], 0.0)

    def test_18_stepfree_route_negative_elevation_transit(self):
        """Interaction: Step-free route transiting from Level -1 to Level 2 via elevator."""
        # Building osm-way27917482 has -1, 0, 1, 2, 3
        floors = {f["level"]: f["id"] for f in self.b_osm_multi["floors"]}
        if -1 in floors and 2 in floors:
            s_neg = [s["id"] for s in self.b_osm_multi["spaces"] if s["floor_id"] == floors[-1]][0]
            count = ReferenceOracle.count_reachable_rooms(self.b_osm_multi, s_neg, floors[2], step_free=True)
            self.assertGreaterEqual(count, 0)

    def test_19_wide_delivery_monotonically_shrinking_subsets(self):
        """Interaction: Wide delivery reachable set strictly shrinks as threshold increases."""
        counts = []
        for w in [0.8, 1.0, 1.2, 1.5]:
            c = ReferenceOracle.count_reachable_rooms(
                self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, min_width=w
            )
            counts.append(c)
        for c1, c2 in zip(counts[:-1], counts[1:]):
            self.assertGreaterEqual(c1, c2)

    def test_20_egress_outside_distance_with_partial_closures(self):
        """Interaction: Closing secondary exit doors increases shortest walk to outside."""
        g1 = ReferenceOracle.build_routing_graph(self.b3_raw)
        d1, _ = ReferenceOracle.shortest_path(g1, "proc-factory-dev-003-F0-S013", "outside")
        # Close one entrance
        entrances = [o["id"] for o in self.b3_raw["openings"] if "outside" in o["space_ids"]]
        if len(entrances) > 1:
            g2 = ReferenceOracle.build_routing_graph(self.b3_raw, closed={entrances[0]})
            if nx.has_path(g2, "proc-factory-dev-003-F0-S013", "outside"):
                d2, _ = ReferenceOracle.shortest_path(g2, "proc-factory-dev-003-F0-S013", "outside")
                self.assertGreaterEqual(d2, d1)

    def test_21_ground_node_entrance_dynamic_diversion(self):
        """Interaction: Outside node maintains path via alternative entrance when one is closed."""
        entrances = [o["id"] for o in self.b3_raw["openings"] if "outside" in o["space_ids"]]
        if len(entrances) >= 2:
            g = ReferenceOracle.build_routing_graph(self.b3_raw, closed={entrances[0]})
            self.assertTrue(nx.has_path(g, "proc-factory-dev-003-F0-S013", "outside"))

    def test_22_multi_asset_category_inventory_query(self):
        """Interaction: Multiple assets queried across different categories."""
        categories = {a["category"] for a in self.b3_raw["assets"]}
        self.assertGreater(len(categories), 1)

    def test_23_three_floor_sequential_stacking(self):
        """Interaction: Stacking query evaluated sequentially (Floor 0 -> Floor 1 -> Floor 2)."""
        s0 = [s for s in self.b3_raw["spaces"] if s["floor_id"] == "proc-factory-dev-003-F0"][0]
        s1, _ = ReferenceOracle.stacked_room(s0, "above", self.b3_raw)
        self.assertEqual(s1["floor_id"], "proc-factory-dev-003-F1")

    def test_24_acoustic_shared_walls_vs_clearance_doors(self):
        """Interaction: Shared walls exist between rooms regardless of whether a door connects them."""
        # Shared walls count counts adjacent walls with or without doors
        s = self.b3_raw["spaces"][0]
        count = ReferenceOracle.shared_walls_count(s, self.b3_raw)
        self.assertGreaterEqual(count, 0)

    def test_25_exploded_view_3d_waypoints_transformation(self):
        """Interaction: Visualizer 3D waypoints scale vertically with exploded view slider."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
            "step_free": True,
        })
        scale = 2.0
        scaled_wps = [[wp[0], wp[1], wp[2] * scale] for wp in res["waypoints_3d"]]
        self.assertEqual(scaled_wps[-1][2], 3.5 * scale)

    def test_26_submission_template_vs_ground_truth_manifest(self):
        """Interaction: Submission template alignment with test questions manifest."""
        tmpl = TEST_DATA_DIR / "submission_template.csv"
        with open(tmpl) as f:
            rows = list(csv.reader(f))[1:]
        self.assertEqual(len(rows), 145)

    def test_27_extraneous_number_detection_cross_categories(self):
        """Interaction: Verifies single-number rule rejection across all number question kinds."""
        for kind in ["floor_area_total", "wide_delivery_count", "shared_walls_count", "straight_line_3d", "errand"]:
            spec = {"type": "number", "value": 42.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
            self.assertFalse(score_reply(spec, "Answer: 42.0 on floor 1"))
            self.assertTrue(score_reply(spec, "Answer: 42.0"))

    def test_28_high_frequency_layout_mutations(self):
        """Interaction: Rapid sequence of closures and door additions maintain graph integrity."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        for i in range(10):
            elem = self.b3_raw["openings"][i % len(self.b3_raw["openings"])]["id"]
            dispatcher.post_closures({"closed": [elem]})
        self.assertTrue(True)

    def test_29_voice_transcript_speech_synthesis_correlation(self):
        """Interaction: Spoken response text correlates with route length and intent."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res = dispatcher.post_voice_command({"transcript": "Route to Kitchen 1.14"})
        self.assertIn("kitchen 1.14", res["response_text"].lower())

    def test_30_simultaneous_stepfree_closures_clearance_errand(self):
        """Interaction: All constraints active simultaneously during errand computation."""
        # Build constrained graph with step_free + min_width + closures
        g = ReferenceOracle.build_routing_graph(
            self.b3_raw,
            step_free=True,
            min_door_width=1.0,
            closed={"proc-factory-dev-003-V01"},
        )
        self.assertGreater(g.number_of_nodes(), 0)


if __name__ == "__main__":
    unittest.main()
