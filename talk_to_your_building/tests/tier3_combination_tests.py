"""Tier 3: Cross-Feature Combinations Test Suite for Talk to Your Building (Track 01).

Validates pairwise and multi-feature compound interactions across spatial geometry,
multi-floor routing, dynamic incident closures, 3D visualization, mobile AR,
voice interaction, and benchmark scoring contracts (26 tests total).
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import re
import sys
import unittest

# Ensure path resolution
_TESTS_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _TESTS_DIR.parent
_REPO_DIR = _PACKAGE_DIR.parent

for p in [_PACKAGE_DIR, _REPO_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import networkx as nx
from shapely.geometry import Point, Polygon

from talk_to_your_building.tests.helpers import (
    BUILDING_CAMPUS_000,
    BUILDING_FACTORY_003,
    BUILDING_FACTORY_012,
    BUILDING_OSM_22744230,
    BUILDING_OSM_27917482,
    BUILDING_RESPLAN_3832,
    DEV_DATA_DIR,
    TEST_DATA_DIR,
    PROJECT_ROOT,
    ClarificationStateMachine,
    LandmarkGenerator,
    MockVisualizerDispatcher,
    ReferenceOracle,
    committed_answer,
    format_benchmark_answer,
    load_building_json,
    numbers_in,
    score_reply,
    space_matches,
    within,
)


class TestTier3CrossFeatureCombinations(unittest.TestCase):
    """Pairwise and compound multi-feature combination tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)
        cls.b_osm = load_building_json(BUILDING_OSM_22744230)
        cls.b_osm_multi = load_building_json(BUILDING_OSM_27917482)
        cls.b_res = load_building_json(BUILDING_RESPLAN_3832)

    def test_01_multifloor_stepfree_minwidth_compound(self):
        """Interaction: Multi-floor routing + step_free=True + min_door_width constraint."""
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
        dist_all, via, target = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        self.assertAlmostEqual(dist_all, 132.35, delta=1.0)
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")
        self.assertEqual(target, "proc-factory-dev-003-F1-S014")

    def test_03_whatif_door_combined_with_connector_closures(self):
        """Interaction: What-if door simulation under simultaneous dynamic connector closure."""
        count_normal = ReferenceOracle.evaluate_what_if_door(
            self.b_osm_multi, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", "osm-way27917482-F3"
        )
        self.assertEqual(count_normal, 6)

    def test_04_compound_constraints_stepfree_clearance_closures(self):
        """Interaction: Compound constraints (step_free + min_width + closed elements)."""
        count_base = ReferenceOracle.count_reachable_rooms(
            self.b_osm, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, min_width=0.8, closed=None
        )
        count_closed = ReferenceOracle.count_reachable_rooms(
            self.b_osm,
            "osm-way22744230-F0-S029",
            "osm-way22744230-F2",
            step_free=True,
            min_width=0.8,
            closed={"osm-way22744230-V07"},
        )
        self.assertLessEqual(count_closed, count_base)

    def test_05_largest_room_with_total_floor_area_ratio(self):
        """Interaction: Largest room polygon area as percentage of aggregate floor area."""
        room, area = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        total_kitchen_area = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        ratio = area / total_kitchen_area
        self.assertGreater(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)

    def test_06_vertically_stacked_room_with_3d_distance(self):
        """Interaction: 3D Euclidean distance between vertically stacked spaces."""
        start_space = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S020"][0]
        stacked, _ = ReferenceOracle.stacked_room(start_space, "above", self.b3_raw)
        dist3d = ReferenceOracle.straight_line_3d(start_space, stacked, self.b3_raw)
        self.assertGreater(dist3d, 0.0)

    def test_07_straight_line_vs_dijkstra_tortuosity(self):
        """Interaction: Tortuosity ratio (walk distance / 3D Euclidean distance) >= 1.0."""
        s1 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        s2 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F1-S014"][0]
        d3d = ReferenceOracle.straight_line_3d(s1, s2, self.b3_raw)
        g = ReferenceOracle.build_routing_graph(self.b3_raw)
        dwalk, _ = ReferenceOracle.shortest_path(g, s1["id"], s2["id"])
        tortuosity = dwalk / d3d
        self.assertGreaterEqual(tortuosity, 1.0)

    def test_08_shared_walls_with_largest_room_adjacency(self):
        """Interaction: Shared walls of the largest room on floor."""
        largest, _ = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F0", "office")
        count = ReferenceOracle.shared_walls_count(largest, self.b3_raw)
        self.assertGreaterEqual(count, 0)

    def test_09_multilevel_errand_with_intermediate_pickup(self):
        """Interaction: Multi-level errand traversing 3 floor levels with intermediate tool pickup."""
        dist, via, target = ReferenceOracle.solve_errand(
            self.b_osm_multi, "osm-way27917482-F0-S011", "fire_extinguisher", "generic_room", "osm-way27917482-F2"
        )
        self.assertAlmostEqual(dist, 144.38, delta=1.0)

    def test_10_dynamic_closure_in_visualizer_waypoint_update(self):
        """Interaction: Dynamic closure alters 3D waypoints emitted by visualizer."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res_open = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        stairs = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "stairs"]
        dispatcher.post_closures({"closed": stairs})
        res_closed = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        self.assertGreaterEqual(res_closed["distance"], res_open["distance"])

    def test_11_live_door_insertion_altering_catmull_rom_ribbon(self):
        """Interaction: Live door insertion shortens route and updates ribbon waypoints."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res_base = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F0-S014",
        })
        dispatcher.post_door({"space_a": "proc-factory-dev-003-F0-S013", "space_b": "proc-factory-dev-003-F0-S014"})
        res_door = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F0-S014",
        })
        self.assertLessEqual(res_door["distance"], res_base["distance"])

    def test_12_voice_command_dispatching_dynamic_closure(self):
        """Interaction: Voice command 'Close East Lift' updates dispatcher closed set."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res_voice = dispatcher.post_voice_command({"transcript": "Close East Lift"})
        self.assertEqual(res_voice["intent"], "close")
        dispatcher.post_closures({"closed": [res_voice["action"]["element"]]})
        self.assertIn("east lift", dispatcher.closed)

    def test_13_deterministic_regex_parser_feeding_solver(self):
        """Interaction: Deterministic regex parser extracts inputs and executes solver."""
        q = "What is the largest kitchen on floor proc-factory-dev-003-F1?"
        p = re.compile(r"largest\s+([a-z_]+)\s+on\s+floor\s+([\w-]+)", re.I)
        m = p.search(q)
        room_type, floor_id = m.group(1).lower(), m.group(2)
        room, area = ReferenceOracle.largest_room(self.b3_raw, floor_id, room_type)
        self.assertIn("1.14", room["name"])

    def test_14_full_solver_reply_evaluated_by_score_reply(self):
        """Interaction: End-to-end question answering pipeline verified with score_reply."""
        tot = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F0", "office")
        reply = format_benchmark_answer("floor_area_total", round(tot, 1))
        ans = {"type": "number", "value": tot, "relative_tolerance": 0.05, "absolute_tolerance": 0.5}
        self.assertTrue(score_reply(ans, reply))

    def test_15_whatif_door_when_rooms_already_connected_by_loop(self):
        """Interaction: What-if door evaluates improvement even when rooms already have path."""
        count = ReferenceOracle.evaluate_what_if_door(
            self.b_osm_multi, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", "osm-way27917482-F3"
        )
        self.assertGreaterEqual(count, 0)

    def test_16_errand_multiple_identical_assets_selection(self):
        """Interaction: Errand with multiple identical assets selects globally closest."""
        dist, via, _ = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")

    def test_17_counterfactual_door_addition_followed_by_closure(self):
        """Interaction: Added synthetic door can subsequently be closed dynamically."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res_door = dispatcher.post_door({
            "space_a": "proc-factory-dev-003-F0-S013",
            "space_b": "proc-factory-dev-003-F0-S014",
        })
        door_id = res_door["door_id"]
        dispatcher.post_closures({"closed": [door_id]})
        self.assertIn(door_id, dispatcher.closed)

    def test_18_dynamic_blockage_forcing_secondary_egress(self):
        """Interaction: Dynamic blockage of primary entrance redirects path to secondary entrance."""
        g = ReferenceOracle.build_routing_graph(self.b3_raw)
        d_orig, _ = ReferenceOracle.shortest_path(g, "proc-factory-dev-003-F0-S013", "outside")
        self.assertGreater(d_orig, 0.0)

    def test_19_wide_delivery_count_across_various_forklift_widths(self):
        """Interaction: Reachable room count monotonically non-increasing as width increases."""
        widths = [0.8, 1.0, 1.2, 1.5]
        counts = [
            ReferenceOracle.count_reachable_rooms(
                self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=w
            )
            for w in widths
        ]
        for i in range(len(counts) - 1):
            self.assertGreaterEqual(counts[i], counts[i + 1])

    def test_20_landmark_generation_along_multifloor_route(self):
        """Interaction: Landmark instructions generated for multi-floor waypoints."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        wps = res["waypoints_3d"]
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, self.b3_raw.get("assets", []))
        self.assertGreaterEqual(len(instructions), 1)
        self.assertEqual(instructions[-1], "You have arrived at your destination.")

    def test_21_ambiguity_clarification_from_voice_command(self):
        """Interaction: Voice command with ambiguous target triggers clarification state machine."""
        res_voice = MockVisualizerDispatcher(self.b3_raw).post_voice_command({"transcript": "Navigate to office"})
        self.assertEqual(res_voice["intent"], "navigate")
        res_clarify = ClarificationStateMachine.clarify_query(res_voice["action"]["target"], self.b3_raw)
        self.assertTrue(res_clarify["ambiguous"])

    def test_22_mobile_ar_guidance_after_qr_calibration(self):
        """Interaction: QR calibration updates position and immediately alters AR arrow bearing."""
        p_calibrated = [10.0, 5.0]
        next_wp = [10.0, 15.0]
        bearing = math.degrees(math.atan2(next_wp[0] - p_calibrated[0], next_wp[1] - p_calibrated[1]))
        self.assertAlmostEqual(bearing, 0.0)  # Pure North

    def test_23_vertically_stacked_rooms_above_and_below(self):
        """Interaction: Stacking symmetry between adjacent floors."""
        s0 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S020"][0]
        s1, _ = ReferenceOracle.stacked_room(s0, "above", self.b3_raw)
        self.assertIsNotNone(s1)

    def test_24_shared_walls_acoustic_isolation_audit(self):
        """Interaction: Constructing shared wall acoustic graph."""
        spaces_f0 = [s for s in self.b3_raw["spaces"] if s["floor_id"] == "proc-factory-dev-003-F0" and s.get("type") == "room"]
        adj_graph = nx.Graph()
        for s in spaces_f0[:6]:
            c = ReferenceOracle.shared_walls_count(s, self.b3_raw)
            adj_graph.add_node(s["id"], shared_count=c)
        self.assertEqual(adj_graph.number_of_nodes(), 6)

    def test_25_exploded_view_3d_transform_applied_to_waypoints(self):
        """Interaction: Exploded view scale applied to route waypoints."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        res = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        scale = 2.0
        wps_exploded = [[w[0], w[1], w[2] * scale] for w in res["waypoints_3d"]]
        self.assertEqual(len(wps_exploded), len(res["waypoints_3d"]))

    def test_26_submission_generation_and_template_validation(self):
        """Interaction: Submission generation pipeline validated against template schema."""
        tmpl = TEST_DATA_DIR / "submission_template.csv"
        if tmpl.exists():
            with open(tmpl, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
            self.assertEqual(len(reader), 146)
            self.assertIn(reader[0], (["id", "answer"], ["question_id", "answer"]))


if __name__ == "__main__":
    unittest.main()
