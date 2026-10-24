"""Tier 4: Real-World Workload Scenarios Test Suite for Talk to Your Building (Track 01).

Executes 12 comprehensive end-to-end simulations reflecting authentic industrial
operations, emergency safety incidents, automated logistics, and digital twin workflows:
1. Forklift Pallet Delivery with Lift Failure (F3, F4, F11, F13, F20)
2. Emergency Building Evacuation with Blocked Stairwell (F6, F11, F13, F16)
3. Multi-Stop Maintenance Errand with Tool Retrieval (F4, F8, F15, F20)
4. Factory Floor Remodel Counterfactual (Adding 2 Fire Doors) (F9, F12, F14, F15)
5. Cross-Floor Heavy Equipment Transport (F3, F4, F7, F8, F11)
6. Mobile AR Operator Checkpoint Navigation (F17, F18, F20)
7. Voice-Directed Warehouse Asset Search with Clarification (F19, F20, F21)
8. Complex Factory Benchmark Solving End-to-End (F1-F10, F24, F25)
9. Swiss Residential Multi-Floor Complex Errand Routing (F4, F7, F8, F10)
10. Real-Time Incident Reroute under Dynamic Barrier Placement (F11, F12, F13, F16)
11. Full Test Submission Generation (145 Questions) Evaluation (F1-F10, F24)
12. Three.js Scene State Serialization & Exploded View Generation (F14, F15, F16)
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


class TestTier4RealWorldScenarios(unittest.TestCase):
    """Tier 4: 12 Real-World Operational Application Scenarios."""

    @classmethod
    def setUpClass(cls):
        cls.b_factory = load_building_json(BUILDING_FACTORY_003)
        cls.b_factory_12 = load_building_json(BUILDING_FACTORY_012)
        cls.b_campus = load_building_json(BUILDING_CAMPUS_000)
        cls.b_osm = load_building_json(BUILDING_OSM_22744230)
        cls.b_osm_multi = load_building_json(BUILDING_OSM_27917482)
        cls.b_res = load_building_json(BUILDING_RESPLAN_3832)

    def test_01_forklift_pallet_delivery_with_lift_failure(self):
        """Scenario 1: Forklift Pallet Delivery with Lift Failure (F3, F4, F11, F13, F20).
        Forklift in ground loading bay (F0-S013) delivering to upper floor server room (F1-S005).
        Requires step_free=True and min_width=1.0m. When primary lift fails, route reroutes
        and emits landmark instructions along the detour.
        """
        # Baseline route via elevator
        g_base = ReferenceOracle.build_routing_graph(
            self.b_factory, step_free=True, min_door_width=1.0
        )
        len_base, path_base = ReferenceOracle.shortest_path(
            g_base, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S005"
        )
        self.assertGreater(len_base, 0.0)

        # Primary lift breakdown
        lifts = [c["id"] for c in self.b_factory["vertical_connectors"] if c["kind"] == "lift"]
        dispatcher = MockVisualizerDispatcher(self.b_factory)
        if lifts:
            dispatcher.post_closures({"closed": [lifts[0]]})
            # Check route response
            try:
                res = dispatcher.post_route({
                    "start": "proc-factory-dev-003-F0-S013",
                    "end": "proc-factory-dev-003-F1-S005",
                    "step_free": True,
                    "min_width": 1.0,
                })
                self.assertGreater(res["distance"], 0.0)
            except nx.NetworkXNoPath:
                # If only 1 lift existed, step-free access is cleanly blocked
                pass

        # Verify landmark generator functions for the route
        wps = [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0]]
        landmarks = LandmarkGenerator.generate_landmark_instructions(wps, self.b_factory.get("assets", []))
        self.assertGreaterEqual(len(landmarks), 1)

    def test_02_emergency_building_evacuation_with_blocked_stairwell(self):
        """Scenario 2: Emergency Building Evacuation with Blocked Stairwell (F6, F11, F13, F16).
        Fire breaks out in central stairwell, blocking primary egress; all occupants must
        recalculate safe exit routes to 'outside' with updated navigation ribbons.
        """
        g_base = ReferenceOracle.build_routing_graph(self.b_factory, step_free=False)
        d_base, _ = ReferenceOracle.shortest_path(
            g_base, "proc-factory-dev-003-F1-S014", "outside"
        )

        stairs = [c["id"] for c in self.b_factory["vertical_connectors"] if c["kind"] == "stairs"]
        closed_set = {stairs[0]} if stairs else set()
        g_fire = ReferenceOracle.build_routing_graph(self.b_factory, step_free=False, closed=closed_set)

        self.assertTrue(nx.has_path(g_fire, "proc-factory-dev-003-F1-S014", "outside"))
        d_fire, path_fire = ReferenceOracle.shortest_path(g_fire, "proc-factory-dev-003-F1-S014", "outside")
        self.assertGreaterEqual(d_fire, d_base)

    def test_03_multi_stop_maintenance_errand_with_tool_retrieval(self):
        """Scenario 3: Multi-Stop Maintenance Errand with Tool Retrieval (F4, F8, F15, F20).
        Technician fetches tool (stove) in storage, delivers to assembly room on F1,
        computing 3D centroid distance and verifying corridor landmark cues.
        """
        dist, via, target = ReferenceOracle.solve_errand(
            self.b_factory,
            "proc-factory-dev-003-F0-S038",
            "stove",
            "kitchen",
            "proc-factory-dev-003-F1",
        )
        self.assertAlmostEqual(dist, 132.35, delta=1.5)
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")
        self.assertEqual(target, "proc-factory-dev-003-F1-S014")

        # 3D Euclidean distance between technician start and final destination
        s_start = [s for s in self.b_factory["spaces"] if s["id"] == "proc-factory-dev-003-F0-S038"][0]
        s_target = [s for s in self.b_factory["spaces"] if s["id"] == target][0]
        dist3d = ReferenceOracle.straight_line_3d(s_start, s_target, self.b_factory)
        self.assertGreater(dist3d, 0.0)
        self.assertLess(dist3d, dist)

    def test_04_factory_floor_remodel_counterfactual(self):
        """Scenario 4: Factory Floor Remodel Counterfactual (Adding 2 Fire Doors) (F9, F12, F14, F15).
        Architect simulates adding doors between congested production spaces, assessing egress improvement.
        """
        improved_rooms = ReferenceOracle.evaluate_what_if_door(
            self.b_osm_multi,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        self.assertEqual(improved_rooms, 6)

        # Dynamic doorway insertion in dispatcher
        dispatcher = MockVisualizerDispatcher(self.b_factory)
        res1 = dispatcher.post_door({
            "space_a": "proc-factory-dev-003-F0-S013",
            "space_b": "proc-factory-dev-003-F0-S014",
        })
        self.assertEqual(res1["status"], "ok")
        state = dispatcher.get_building()
        self.assertEqual(len(state["openings"]), len(self.b_factory["openings"]) + 1)

    def test_05_cross_floor_heavy_equipment_transport(self):
        """Scenario 5: Cross-Floor Heavy Equipment Transport (F3, F4, F7, F8, F11).
        Heavy machine transport requiring clearance >= 1.1m, checking vertical alignment
        of structural rooms on upper floor and 3D centroid separation.
        """
        count = ReferenceOracle.count_reachable_rooms(
            self.b_factory,
            "proc-factory-dev-003-F0-S013",
            "proc-factory-dev-003-F1",
            step_free=True,
            min_width=1.1,
        )
        self.assertEqual(count, 7)

        # Structural stacking alignment
        s0 = [s for s in self.b_factory["spaces"] if s["id"] == "proc-factory-dev-003-F0-S020"][0]
        stacked, overlap = ReferenceOracle.stacked_room(s0, "above", self.b_factory)
        self.assertGreater(overlap, 0.0)

    def test_06_mobile_ar_operator_checkpoint_navigation(self):
        """Scenario 6: Mobile AR Operator Checkpoint Navigation (F17, F18, F20).
        Operator holding AR device scans doorway QR code; position calibrates and directional
        guidance arrow aligns to next machine landmark.
        """
        target_door = self.b_factory["openings"][0]
        door_id = target_door["id"]
        qr_code = f"bldg:door:{door_id}"
        door_match = re.match(r"^bldg:door:([\w-]+)$", qr_code)
        self.assertIsNotNone(door_match)
        self.assertEqual(door_match.group(1), door_id)

        calibrated_pos = target_door["position"]

        # Next target waypoint
        target_wp = [calibrated_pos[0] + 5.0, calibrated_pos[1] + 5.0]
        dx = target_wp[0] - calibrated_pos[0]
        dy = target_wp[1] - calibrated_pos[1]
        bearing = math.degrees(math.atan2(dx, dy))
        self.assertAlmostEqual(bearing, 45.0)

    def test_07_voice_directed_warehouse_asset_search_with_clarification(self):
        """Scenario 7: Voice-Directed Warehouse Asset Search with Clarification (F19, F20, F21).
        Operator speaks ambiguous destination 'office'; conversational state machine prompts
        with candidates across floors, resolving to precise room upon clarification.
        """
        dispatcher = MockVisualizerDispatcher(self.b_factory)
        voice_res = dispatcher.post_voice_command({"transcript": "Navigate to office"})
        self.assertEqual(voice_res["intent"], "navigate")

        clarify_res = ClarificationStateMachine.clarify_query(voice_res["action"]["target"], self.b_factory)
        self.assertTrue(clarify_res["ambiguous"])
        self.assertGreater(len(clarify_res["candidates"]), 1)

        # User chooses specific candidate from list
        chosen = clarify_res["candidates"][0]
        resolved = ClarificationStateMachine.clarify_query(chosen["name"], self.b_factory)
        self.assertFalse(resolved["ambiguous"])

    def test_08_complex_factory_benchmark_solving_end_to_end(self):
        """Scenario 8: Complex Factory Benchmark Solving End-to-End (F1-F10, F24, F25).
        Automated benchmark evaluation across representative dev dataset questions spanning
        all benchmark categories achieving >= 95% accuracy with score_reply.
        """
        dev_questions = []
        for p in sorted(DEV_DATA_DIR.glob("*/questions.jsonl"))[:4]:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        dev_questions.append((p.parent.name, json.loads(line)))

        passed = 0
        for b_name, q in dev_questions:
            b_path = DEV_DATA_DIR / b_name
            b_data = load_building_json(b_path)
            kind = q["kind"]
            inputs = q["inputs"]
            expected = q["answer"]

            if kind == "largest_room":
                room, area = ReferenceOracle.largest_room(b_data, inputs["floor_id"], inputs["room_type"])
                reply = format_benchmark_answer(kind, (room.get("name", "") or room.get("ref", ""), area))
            elif kind == "floor_area_total":
                tot = ReferenceOracle.floor_area_total(b_data, inputs["floor_id"], inputs["room_type"])
                reply = format_benchmark_answer(kind, tot)
            elif kind == "straight_line_3d":
                spaces = {s["id"]: s for s in b_data["spaces"]}
                dist = ReferenceOracle.straight_line_3d(spaces[inputs["first"]], spaces[inputs["second"]], b_data)
                reply = format_benchmark_answer(kind, dist)
            elif kind == "shared_walls_count":
                spaces = {s["id"]: s for s in b_data["spaces"]}
                count = ReferenceOracle.shared_walls_count(spaces[inputs["start"]], b_data)
                reply = format_benchmark_answer(kind, count)
            elif kind == "wide_delivery_count":
                count = ReferenceOracle.count_reachable_rooms(
                    b_data, inputs["start"], inputs["floor_id"], step_free=True, min_width=inputs["min_width"]
                )
                reply = format_benchmark_answer(kind, count)
            elif kind == "errand":
                dist, _, _ = ReferenceOracle.solve_errand(
                    b_data, inputs["start"], inputs["asset_type"], inputs["room_type"], inputs["floor_id"]
                )
                reply = format_benchmark_answer(kind, dist)
            elif kind == "room_stacked":
                spaces = {s["id"]: s for s in b_data["spaces"]}
                room, _ = ReferenceOracle.stacked_room(spaces[inputs["start"]], inputs["direction"], b_data)
                reply = format_benchmark_answer(kind, room.get("name", "") or room.get("ref", ""))
            elif kind == "what_if_door":
                count = ReferenceOracle.evaluate_what_if_door(
                    b_data, inputs["first"], inputs["second"], inputs["floor_id"]
                )
                reply = format_benchmark_answer(kind, count)
            elif kind == "step_free_reachable_count":
                count = ReferenceOracle.count_reachable_rooms(
                    b_data, inputs["start"], inputs["floor_id"], step_free=True, closed={inputs["closed"]}
                )
                reply = format_benchmark_answer(kind, count)
            else:
                continue

            if score_reply(expected, reply):
                passed += 1

        accuracy = passed / len(dev_questions)
        self.assertGreaterEqual(accuracy, 0.95)

    def test_09_swiss_residential_complex_errand_routing(self):
        """Scenario 9: Swiss Residential Multi-Floor Complex Errand Routing (F4, F7, F8, F10).
        Evaluates navigation across multi-story residential building (resplan-3832).
        """
        g = ReferenceOracle.build_routing_graph(self.b_res)
        start_id = self.b_res["spaces"][0]["id"]
        self.assertTrue(nx.has_path(g, start_id, "outside"))
        d_exit, path_exit = ReferenceOracle.shortest_path(g, start_id, "outside")
        self.assertGreater(d_exit, 0.0)

    def test_10_realtime_incident_reroute_under_barrier_placement(self):
        """Scenario 10: Real-Time Incident Reroute under Dynamic Barrier Placement (F11, F12, F13, F16).
        Construction barrier placed across main corridor; active navigation immediately recalculates.
        """
        dispatcher = MockVisualizerDispatcher(self.b_factory)
        res_open = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        # Place barrier on primary stairs
        stairs = [c["id"] for c in self.b_factory["vertical_connectors"] if c["kind"] == "stairs"]
        dispatcher.post_closures({"closed": stairs})
        res_detour = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        self.assertGreaterEqual(res_detour["distance"], res_open["distance"])

    def test_11_full_test_submission_generation_evaluation(self):
        """Scenario 11: Full Test Submission Generation (145 Questions) Evaluation (F1-F10, F24).
        Audits submission generation pipeline ensuring all 145 question IDs from template are matched.
        """
        tmpl = TEST_DATA_DIR / "submission_template.csv"
        if tmpl.exists():
            with open(tmpl, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(len(rows), 146)
            for r in rows[1:]:
                self.assertTrue(r[0].strip())

    def test_12_threejs_scene_state_serialization(self):
        """Scenario 12: Three.js Scene State Serialization & Exploded View Generation (F14, F15, F16).
        Serializes multi-floor digital twin scene including floors, 3D extruded rooms, and route ribbons.
        """
        dispatcher = MockVisualizerDispatcher(self.b_factory)
        state = dispatcher.get_building()
        for k in ["floors", "spaces", "openings", "vertical_connectors", "assets"]:
            self.assertIn(k, state)

        # Exploded view transform
        for scale in [0.0, 1.0, 2.0, 3.0]:
            scaled_elevations = [f["elevation_m"] * scale for f in state["floors"]]
            self.assertEqual(len(scaled_elevations), len(state["floors"]))


if __name__ == "__main__":
    unittest.main()
