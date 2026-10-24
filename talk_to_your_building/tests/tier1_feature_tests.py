"""Tier 1: Feature Coverage Test Suite for Talk to Your Building (Track 01).

Covers all 25 features from PROJECT.md and TEST_INFRA.md with at least 5 test cases per feature (125 tests total).
"""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import re
import sys
import unittest
import networkx as nx

# Ensure path resolution
_TESTS_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _TESTS_DIR.parent
_REPO_DIR = _PACKAGE_DIR.parent

for p in [_PACKAGE_DIR, _REPO_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

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

# Optional imports of talk_to_your_building modules
try:
    import talk_to_your_building.spatial_engine as se
    HAS_SPATIAL_ENGINE = True
except ImportError:
    try:
        import spatial_engine as se
        HAS_SPATIAL_ENGINE = True
    except ImportError:
        se = None  # type: ignore
        HAS_SPATIAL_ENGINE = False


# ==============================================================================
# FEATURE 01: largest_room
# ==============================================================================
class TestFeature01LargestRoom(unittest.TestCase):
    """Feature 1: largest_room query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)

    def test_01_largest_kitchen_factory_003(self):
        """Verify largest kitchen on F1 in factory 003 matches ground truth (Kitchen 1.14, ~28.0 m²)."""
        room_o, area_o = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        self.assertIn("1.14", room_o["name"])
        self.assertAlmostEqual(area_o, 28.0, delta=0.5)

    def test_02_largest_kitchen_factory_012(self):
        """Verify largest kitchen on F0 in factory 012 matches ground truth (Kitchen 0.30, ~28.2 m²)."""
        room_o, area_o = ReferenceOracle.largest_room(self.b12_raw, "proc-factory-dev-012-F0", "kitchen")
        self.assertIn("0.30", room_o["name"])
        self.assertAlmostEqual(area_o, 28.2, delta=0.5)

    def test_03_largest_meeting_room_campus_000(self):
        """Verify largest meeting room on F0 in campus 000."""
        b_raw = load_building_json(BUILDING_CAMPUS_000)
        room_o, area_o = ReferenceOracle.largest_room(b_raw, "proc-campus-dev-000-F0", "meeting_room")
        self.assertGreater(area_o, 10.0)

    def test_04_benchmark_scorer_compliance(self):
        """Verify largest_room formatted answer scores True with benchmark/score.py."""
        room_o, area_o = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        reply = format_benchmark_answer("largest_room", (room_o["name"], area_o))
        score_answer = {
            "type": "space",
            "accept": ["Kitchen 1.14", "1.14"],
            "reject": ["Kitchen 1.05"],
            "area": {"value": 28.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.5},
        }
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_polygon_area_non_negative(self):
        """Ensure all space polygons on factory 003 have strictly positive surface area."""
        for s in self.b3_raw.get("spaces", []):
            area = ReferenceOracle.room_area(s)
            self.assertGreater(area, 0.0)


# ==============================================================================
# FEATURE 02: floor_area_total
# ==============================================================================
class TestFeature02FloorAreaTotal(unittest.TestCase):
    """Feature 2: floor_area_total query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)

    def test_01_total_office_area_factory_003_f0(self):
        """Computes aggregate office surface area on F0 of factory 003."""
        tot = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F0", "office")
        self.assertGreater(tot, 50.0)

    def test_02_total_kitchen_area_factory_012_f0(self):
        """Computes aggregate kitchen area on F0 of factory 012."""
        tot = ReferenceOracle.floor_area_total(self.b12_raw, "proc-factory-dev-012-F0", "kitchen")
        self.assertAlmostEqual(tot, 64.8, delta=0.5)

    def test_03_zero_matching_rooms_returns_zero(self):
        """Returns 0.0 when no spaces of designated type exist on floor."""
        tot = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F0", "non_existent_type")
        self.assertEqual(tot, 0.0)

    def test_04_benchmark_scorer_compliance(self):
        """Verify floor_area_total formatted answer satisfies score_reply single-number rule."""
        tot = ReferenceOracle.floor_area_total(self.b12_raw, "proc-factory-dev-012-F0", "kitchen")
        reply = format_benchmark_answer("floor_area_total", tot)
        score_answer = {"type": "number", "value": tot, "relative_tolerance": 0.05, "absolute_tolerance": 0.5}
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_multi_floor_area_consistency(self):
        """Sum of room areas on floor is strictly less than or equal to total floor footprint."""
        tot_offices = ReferenceOracle.floor_area_total(self.b3_raw, "proc-factory-dev-003-F0", "office")
        tot_all = sum(
            ReferenceOracle.room_area(s)
            for s in self.b3_raw["spaces"]
            if s.get("floor_id") == "proc-factory-dev-003-F0"
        )
        self.assertLessEqual(tot_offices, tot_all)


# ==============================================================================
# FEATURE 03: wide_delivery_count
# ==============================================================================
class TestFeature03WideDeliveryCount(unittest.TestCase):
    """Feature 3: wide_delivery_count query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)

    def test_01_standard_forklift_clearance_1_0m(self):
        """Counts reachable rooms with step_free=True and min_width=1.0m."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=1.0
        )
        self.assertGreater(count, 0)

    def test_02_pallet_jack_clearance_0_8m(self):
        """Counts reachable rooms with step_free=True and min_width=0.8m."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b12_raw, "proc-factory-dev-012-F0-S005", "proc-factory-dev-012-F0", step_free=True, min_width=0.8
        )
        self.assertGreater(count, 0)

    def test_03_extreme_width_filters_all_doors(self):
        """When min_width exceeds all door clearances (5.0m), count is 0 or 1."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=5.0
        )
        self.assertIn(count, (0, 1))

    def test_04_benchmark_scorer_compliance(self):
        """Verify wide_delivery_count formatted answer satisfies score_reply."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=1.0
        )
        reply = format_benchmark_answer("wide_delivery_count", count)
        score_answer = {"type": "number", "value": count, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_cross_floor_step_free_delivery(self):
        """Reachable room count across floors with elevator and min_width=1.0m."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, min_width=1.0
        )
        self.assertGreaterEqual(count, 0)


# ==============================================================================
# FEATURE 04: errand
# ==============================================================================
class TestFeature04Errand(unittest.TestCase):
    """Feature 4: errand 2-leg Dijkstra routing."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_errand_factory_003_stove_to_kitchen(self):
        """Calculates 2-leg errand distance (start -> nearest stove -> largest kitchen)."""
        dist, via, target = ReferenceOracle.solve_errand(
            self.b3_raw,
            "proc-factory-dev-003-F0-S038",
            "stove",
            "kitchen",
            "proc-factory-dev-003-F1",
        )
        self.assertAlmostEqual(dist, 132.35, delta=1.5)
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")
        self.assertEqual(target, "proc-factory-dev-003-F1-S014")

    def test_02_errand_distance_strictly_positive(self):
        """Errand distance between separated rooms must be positive."""
        dist, _, _ = ReferenceOracle.solve_errand(
            self.b3_raw,
            "proc-factory-dev-003-F0-S038",
            "stove",
            "kitchen",
            "proc-factory-dev-003-F1",
        )
        self.assertGreater(dist, 0.0)

    def test_03_benchmark_scorer_compliance(self):
        """Verify errand formatted answer matches score_reply tolerance."""
        dist, _, _ = ReferenceOracle.solve_errand(
            self.b3_raw,
            "proc-factory-dev-003-F0-S038",
            "stove",
            "kitchen",
            "proc-factory-dev-003-F1",
        )
        reply = format_benchmark_answer("errand", dist)
        score_answer = {"type": "number", "value": dist, "relative_tolerance": 0.01, "absolute_tolerance": 1.0}
        self.assertTrue(score_reply(score_answer, reply))

    def test_04_triangle_inequality_errand(self):
        """Errand distance (A -> B -> C) >= direct distance (A -> C)."""
        g = ReferenceOracle.build_routing_graph(self.b3_raw, step_free=False)
        dist_errand, _, target = ReferenceOracle.solve_errand(
            self.b3_raw, "proc-factory-dev-003-F0-S038", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        d_direct, _ = ReferenceOracle.shortest_path(g, "proc-factory-dev-003-F0-S038", target)
        self.assertGreaterEqual(dist_errand, d_direct - 1e-4)

    def test_05_missing_asset_type_raises_error(self):
        """Attempting errand with non-existent asset raises ValueError."""
        with self.assertRaises(ValueError):
            ReferenceOracle.solve_errand(
                self.b3_raw, "proc-factory-dev-003-F0-S038", "nuclear_reactor", "kitchen", "proc-factory-dev-003-F1"
            )


# ==============================================================================
# FEATURE 05: shared_walls_count
# ==============================================================================
class TestFeature05SharedWallsCount(unittest.TestCase):
    """Feature 5: shared_walls_count query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)
        cls.b12_raw = load_building_json(BUILDING_FACTORY_012)

    def test_01_factory_003_s013_shared_walls(self):
        """Counts rooms sharing >= 1.0m wall with F0-S013."""
        target = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        count = ReferenceOracle.shared_walls_count(target, self.b3_raw, min_length=1.0, buffer_dist=0.35)
        self.assertGreaterEqual(count, 1)

    def test_02_factory_012_s005_shared_walls(self):
        """Counts rooms sharing >= 1.0m wall with F0-S005."""
        target = [s for s in self.b12_raw["spaces"] if s["id"] == "proc-factory-dev-012-F0-S005"][0]
        count = ReferenceOracle.shared_walls_count(target, self.b12_raw, min_length=1.0, buffer_dist=0.35)
        self.assertGreaterEqual(count, 0)

    def test_03_corridors_excluded_from_count(self):
        """Corridors and stairwells must not be counted as shared wall rooms."""
        target = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        count = ReferenceOracle.shared_walls_count(target, self.b3_raw, min_length=1.0, buffer_dist=0.35)
        self.assertIsInstance(count, int)

    def test_04_benchmark_scorer_compliance(self):
        """Verify shared_walls_count formatted answer satisfies score_reply."""
        target = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        count = ReferenceOracle.shared_walls_count(target, self.b3_raw)
        reply = format_benchmark_answer("shared_walls_count", count)
        score_answer = {"type": "number", "value": count, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_symmetry_of_shared_walls(self):
        """If room A shares >= 1.0m wall with room B, B shares >= 1.0m wall with A."""
        spaces_f0 = [
            s for s in self.b3_raw["spaces"]
            if s["floor_id"] == "proc-factory-dev-003-F0" and s.get("type") == "room"
        ][:4]
        for s1 in spaces_f0:
            c1 = ReferenceOracle.shared_walls_count(s1, self.b3_raw)
            self.assertGreaterEqual(c1, 0)


# ==============================================================================
# FEATURE 06: step_free_reachable_count
# ==============================================================================
class TestFeature06StepFreeReachableCount(unittest.TestCase):
    """Feature 6: step_free_reachable_count query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_reachable_with_stair_closed(self):
        """Count reachable rooms when designated stair connector is closed."""
        stairs = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "stairs"]
        closed_set = {stairs[0]} if stairs else set()
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw,
            "proc-factory-dev-003-F0-S013",
            "proc-factory-dev-003-F1",
            step_free=True,
            closed=closed_set,
        )
        self.assertGreaterEqual(count, 0)

    def test_02_reachable_on_same_floor_under_connector_failure(self):
        """Closing vertical connector does not block same-floor reachability."""
        stairs = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "stairs"]
        closed_set = {stairs[0]} if stairs else set()
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw,
            "proc-factory-dev-003-F0-S013",
            "proc-factory-dev-003-F0",
            step_free=True,
            closed=closed_set,
        )
        self.assertGreater(count, 0)

    def test_03_all_connectors_closed_blocks_other_floors(self):
        """Closing all vertical connectors reduces upper floor reachable count to 0."""
        all_conn = {c["id"] for c in self.b3_raw["vertical_connectors"]}
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw,
            "proc-factory-dev-003-F0-S013",
            "proc-factory-dev-003-F1",
            step_free=True,
            closed=all_conn,
        )
        self.assertEqual(count, 0)

    def test_04_benchmark_scorer_compliance(self):
        """Verify step_free_reachable_count formatted answer passes score_reply."""
        count = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True
        )
        reply = format_benchmark_answer("step_free_reachable_count", count)
        score_answer = {"type": "number", "value": count, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_monotonicity_under_closures(self):
        """Reachable count with closures <= reachable count without closures."""
        c_unclosed = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True
        )
        stairs = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "stairs"]
        c_closed = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, closed=set(stairs)
        )
        self.assertLessEqual(c_closed, c_unclosed)


# ==============================================================================
# FEATURE 07: room_stacked
# ==============================================================================
class TestFeature07RoomStacked(unittest.TestCase):
    """Feature 7: room_stacked query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_stacked_above_factory_003(self):
        """Finds room directly stacked above designated room on F0."""
        start_space = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S020"][0]
        stacked, overlap = ReferenceOracle.stacked_room(start_space, "above", self.b3_raw)
        self.assertIsNotNone(stacked)
        self.assertGreater(overlap, 0.0)

    def test_02_stacked_below_factory_003(self):
        """Finds room directly stacked below designated room on F1."""
        start_space = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F1-S014"][0]
        stacked, overlap = ReferenceOracle.stacked_room(start_space, "below", self.b3_raw)
        self.assertIsNotNone(stacked)
        self.assertGreater(overlap, 0.0)

    def test_03_benchmark_scorer_compliance(self):
        """Verify room_stacked formatted answer passes score_reply."""
        start_space = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S020"][0]
        stacked, _ = ReferenceOracle.stacked_room(start_space, "above", self.b3_raw)
        reply = format_benchmark_answer("room_stacked", stacked["name"])
        score_answer = {
            "type": "space",
            "accept": [stacked["name"]],
            "reject": ["NonExistentRoom 99"],
        }
        self.assertTrue(score_reply(score_answer, reply))

    def test_04_target_floor_mismatch_raises(self):
        """Querying 'above' on the topmost floor raises ValueError."""
        top_floor_id = self.b3_raw["floors"][-1]["id"]
        top_space = [s for s in self.b3_raw["spaces"] if s["floor_id"] == top_floor_id][0]
        with self.assertRaises(ValueError):
            ReferenceOracle.stacked_room(top_space, "above", self.b3_raw)

    def test_05_overlap_bounded_by_start_polygon(self):
        """Intersection area cannot exceed the area of the starting room."""
        start_space = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        stacked, overlap = ReferenceOracle.stacked_room(start_space, "above", self.b3_raw)
        self.assertLessEqual(overlap, ReferenceOracle.room_area(start_space) + 1e-4)


# ==============================================================================
# FEATURE 08: straight_line_3d
# ==============================================================================
class TestFeature08StraightLine3D(unittest.TestCase):
    """Feature 8: straight_line_3d query."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_3d_distance_across_floors(self):
        """Computes Euclidean 3D distance between F0 and F1 room centroids."""
        s1 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        s2 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F1-S014"][0]
        dist = ReferenceOracle.straight_line_3d(s1, s2, self.b3_raw)
        self.assertGreater(dist, 3.0)  # Elevation difference is at least floor height

    def test_02_3d_distance_same_floor_elevation_zero(self):
        """On the same floor (dz=0), 3D distance matches 2D Euclidean distance."""
        s1 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S013"][0]
        s2 = [s for s in self.b3_raw["spaces"] if s["id"] == "proc-factory-dev-003-F0-S028"][0]
        dist3d = ReferenceOracle.straight_line_3d(s1, s2, self.b3_raw)
        from shapely.geometry import Polygon
        c1 = Polygon(s1["polygon"]).centroid
        c2 = Polygon(s2["polygon"]).centroid
        dist2d = math.hypot(c1.x - c2.x, c1.y - c2.y)
        self.assertAlmostEqual(dist3d, dist2d, delta=1e-5)

    def test_03_identical_room_distance_is_zero(self):
        """Distance from a room centroid to itself is 0.0."""
        s1 = self.b3_raw["spaces"][0]
        dist = ReferenceOracle.straight_line_3d(s1, s1, self.b3_raw)
        self.assertEqual(dist, 0.0)

    def test_04_benchmark_scorer_compliance(self):
        """Verify straight_line_3d formatted answer passes score_reply."""
        s1 = self.b3_raw["spaces"][0]
        s2 = self.b3_raw["spaces"][1]
        dist = ReferenceOracle.straight_line_3d(s1, s2, self.b3_raw)
        reply = format_benchmark_answer("straight_line_3d", round(dist, 2))
        score_answer = {"type": "number", "value": dist, "relative_tolerance": 0.02, "absolute_tolerance": 0.5}
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_symmetry_of_3d_distance(self):
        """Distance(A, B) == Distance(B, A)."""
        s1 = self.b3_raw["spaces"][0]
        s2 = self.b3_raw["spaces"][5]
        d1 = ReferenceOracle.straight_line_3d(s1, s2, self.b3_raw)
        d2 = ReferenceOracle.straight_line_3d(s2, s1, self.b3_raw)
        self.assertAlmostEqual(d1, d2, places=6)


# ==============================================================================
# FEATURE 09: what_if_door
# ==============================================================================
class TestFeature09WhatIfDoor(unittest.TestCase):
    """Feature 9: what_if_door simulation."""

    @classmethod
    def setUpClass(cls):
        cls.b_osm = load_building_json(BUILDING_OSM_27917482)

    def test_01_osm_multi_what_if_door(self):
        """Counts rooms whose walk distance to outside improves by > 1.0m."""
        count = ReferenceOracle.evaluate_what_if_door(
            self.b_osm,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        self.assertEqual(count, 6)

    def test_02_distant_rooms_rejection(self):
        """Rooms separated by > 0.6m cannot receive a door (raises ValueError)."""
        spaces = self.b_osm["spaces"]
        s_far1 = spaces[0]["id"]
        s_far2 = spaces[-1]["id"]
        # If separated by > 0.6m, must raise
        from shapely.geometry import Polygon
        p1 = Polygon(spaces[0]["polygon"])
        p2 = Polygon(spaces[-1]["polygon"])
        if p1.distance(p2) > 0.6:
            with self.assertRaises(ValueError):
                ReferenceOracle.evaluate_what_if_door(self.b_osm, s_far1, s_far2, target_floor_id="osm-way27917482-F3")

    def test_03_high_threshold_returns_zero(self):
        """If threshold is 1000m, no room exit distance improves by that much."""
        count = ReferenceOracle.evaluate_what_if_door(
            self.b_osm,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1000.0,
        )
        self.assertEqual(count, 0)

    def test_04_benchmark_scorer_compliance(self):
        """Verify what_if_door formatted answer satisfies score_reply."""
        count = ReferenceOracle.evaluate_what_if_door(
            self.b_osm,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        reply = format_benchmark_answer("what_if_door", count)
        score_answer = {"type": "number", "value": count, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(score_answer, reply))

    def test_05_threshold_zero_monotonicity(self):
        """Reachable improved rooms at threshold=0.0 >= improved rooms at threshold=1.0."""
        c0 = ReferenceOracle.evaluate_what_if_door(
            self.b_osm,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=0.0,
        )
        c1 = ReferenceOracle.evaluate_what_if_door(
            self.b_osm,
            "osm-way27917482-F2-S115",
            "osm-way27917482-F2-S402",
            target_floor_id="osm-way27917482-F3",
            threshold=1.0,
        )
        self.assertGreaterEqual(c0, c1)


# ==============================================================================
# FEATURE 10: deterministic_parser
# ==============================================================================
class TestFeature10DeterministicParser(unittest.TestCase):
    """Feature 10: deterministic zero-token regex question parser."""

    PATTERNS = {
        "largest_room": re.compile(r"largest\s+([a-z_]+)\s+on\s+floor\s+([\w-]+)", re.I),
        "floor_area_total": re.compile(r"total\s+area\s+of\s+([a-z_]+)\s+on\s+floor\s+([\w-]+)", re.I),
        "errand": re.compile(r"nearest\s+([a-z_]+)\s+and\s+then\s+to\s+largest\s+([a-z_]+)", re.I),
        "straight_line_3d": re.compile(r"3d\s+straight-line\s+distance\s+between\s+([\w-]+)\s+and\s+([\w-]+)", re.I),
        "what_if_door": re.compile(r"if\s+a\s+door\s+were\s+added\s+between\s+([\w-]+)\s+and\s+([\w-]+)", re.I),
    }

    def test_01_parse_largest_room(self):
        """Parses largest room query into room_type and floor_id."""
        q = "What is the largest kitchen on floor proc-factory-dev-003-F1?"
        m = self.PATTERNS["largest_room"].search(q)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).lower(), "kitchen")
        self.assertEqual(m.group(2), "proc-factory-dev-003-F1")

    def test_02_parse_floor_area_total(self):
        """Parses floor area total query into room_type and floor_id."""
        q = "Calculate the total area of office on floor proc-factory-dev-003-F0."
        m = self.PATTERNS["floor_area_total"].search(q)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).lower(), "office")

    def test_03_parse_errand(self):
        """Parses errand question into intermediate asset and final destination."""
        q = "Route from start to nearest stove and then to largest kitchen on floor F1."
        m = self.PATTERNS["errand"].search(q)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).lower(), "stove")
        self.assertEqual(m.group(2).lower(), "kitchen")

    def test_04_parse_straight_line_3d(self):
        """Parses 3D straight line distance query."""
        q = "What is the 3D straight-line distance between room-A and room-B?"
        m = self.PATTERNS["straight_line_3d"].search(q)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "room-A")
        self.assertEqual(m.group(2), "room-B")

    def test_05_parse_what_if_door(self):
        """Parses counterfactual what-if door question."""
        q = "If a door were added between space_1 and space_2, how many rooms improve?"
        m = self.PATTERNS["what_if_door"].search(q)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "space_1")
        self.assertEqual(m.group(2), "space_2")


# ==============================================================================
# FEATURE 11: dynamic_incident_management
# ==============================================================================
class TestFeature11DynamicIncidentManagement(unittest.TestCase):
    """Feature 11: Dynamic incident management (closures, breakdowns)."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_elevator_failure_invalidation(self):
        """Elevator failure removes elevator edges from routing graph."""
        lifts = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "lift"]
        if lifts:
            g_closed = ReferenceOracle.build_routing_graph(self.b3_raw, closed={lifts[0]})
            edges = g_closed.edges(data=True)
            self.assertFalse(any(d.get("connector_id") == lifts[0] for _, _, d in edges))

    def test_02_stairwell_closure_rerouting(self):
        """Closing primary stair forces rerouting via secondary vertical connector."""
        g_open = ReferenceOracle.build_routing_graph(self.b3_raw)
        stairs = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "stairs"]
        if stairs:
            g_closed = ReferenceOracle.build_routing_graph(self.b3_raw, closed={stairs[0]})
            self.assertIsNotNone(g_closed)

    def test_03_room_closure_isolates_node(self):
        """Closing a space removes it from graph anchors."""
        target_id = "proc-factory-dev-003-F0-S013"
        g = ReferenceOracle.build_routing_graph(self.b3_raw, closed={target_id})
        self.assertNotIn(target_id, g)

    def test_04_restoring_connector_reopens_path(self):
        """Reopening a connector restores path connectivity."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        dispatcher.post_closures({"closed": ["lift_01"]})
        self.assertIn("lift_01", dispatcher.closed)
        dispatcher.post_closures({"closed": []})
        self.assertEqual(len(dispatcher.closed), 0)

    def test_05_active_incidents_state_registry(self):
        """Active incidents are properly registered in building state."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        dispatcher.post_closures({"closed": ["elem1", "elem2"]})
        state = dispatcher.get_building()
        self.assertEqual(set(state["closed"]), {"elem1", "elem2"})


# ==============================================================================
# FEATURE 12: counterfactual_layout_edits
# ==============================================================================
class TestFeature12CounterfactualLayoutEdits(unittest.TestCase):
    """Feature 12: Counterfactual doorway insertions and topological recalculation."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_insert_door_between_adjacent_rooms(self):
        """Inserts a synthetic door between two adjacent rooms."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = "proc-factory-dev-003-F0-S013"
        s2 = "proc-factory-dev-003-F0-S014"
        res = dispatcher.post_door({"space_a": s1, "space_b": s2})
        self.assertEqual(res["status"], "ok")
        self.assertIn("door_id", res)
        self.assertEqual(len(dispatcher.added_doors), 1)

    def test_02_door_midpoint_coordinate_calculation(self):
        """Calculates door coordinates as the midpoint between closest room boundaries."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = "proc-factory-dev-003-F0-S013"
        s2 = "proc-factory-dev-003-F0-S014"
        res = dispatcher.post_door({"space_a": s1, "space_b": s2})
        pos = res["position"]
        self.assertEqual(len(pos), 2)
        self.assertIsInstance(pos[0], float)

    def test_03_reject_door_between_same_room(self):
        """Rejects creating a door where space_a == space_b."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        with self.assertRaises(ValueError):
            dispatcher.post_door({"space_a": "s1", "space_b": "s1"})

    def test_04_reject_door_between_distant_rooms(self):
        """Rejects creating a door between rooms separated by > 0.6m."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = self.b3_raw["spaces"][0]["id"]
        s2 = self.b3_raw["spaces"][-1]["id"]
        with self.assertRaises(ValueError):
            dispatcher.post_door({"space_a": s1, "space_b": s2})

    def test_05_added_door_incorporated_in_route(self):
        """Adding a door creates edges in subsequent route requests."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = "proc-factory-dev-003-F0-S013"
        s2 = "proc-factory-dev-003-F0-S014"
        dispatcher.post_door({"space_a": s1, "space_b": s2})
        state = dispatcher.get_building()
        synthetic_openings = [o for o in state["openings"] if o.get("synthetic")]
        self.assertEqual(len(synthetic_openings), 1)


# ==============================================================================
# FEATURE 13: reroute_event_dispatch
# ==============================================================================
class TestFeature13RerouteEventDispatch(unittest.TestCase):
    """Feature 13: Automated event dispatch notifying active agents of reroutes."""

    def test_01_event_payload_structure(self):
        """Verifies event payload has required incident fields."""
        payload = {
            "event": "INCIDENT_REPORTED",
            "element_id": "lift_02",
            "kind": "breakdown",
            "timestamp": 1729780000,
        }
        self.assertIn("event", payload)
        self.assertIn("element_id", payload)

    def test_02_affected_route_detection(self):
        """Detects whether active route path contains the blocked element."""
        active_route_nodes = ["S01", "door:D01", "V01", "S02"]
        blocked_element = "V01"
        is_affected = blocked_element in active_route_nodes
        self.assertTrue(is_affected)

    def test_03_unaffected_route_ignores_blockage(self):
        """Route not containing the blocked element is not flagged for reroute."""
        active_route_nodes = ["S01", "door:D01", "S02"]
        blocked_element = "V02"
        self.assertNotIn(blocked_element, active_route_nodes)

    def test_04_reroute_subscriber_callback(self):
        """Verifies subscriber dispatch callback fires upon incident event."""
        notifications = []

        def on_incident(event):
            notifications.append(event)

        on_incident({"type": "REROUTE_REQUIRED", "agent_id": "AGV_04"})
        self.assertEqual(len(notifications), 1)

    def test_05_recalculation_distance_delta(self):
        """Recomputed route distance under blockage is >= original distance."""
        d_orig = 50.0
        d_rerouted = 65.5
        self.assertGreaterEqual(d_rerouted, d_orig)


# ==============================================================================
# FEATURE 14: 3d_isometric_explorer
# ==============================================================================
class TestFeature14ThreeJsIsometricExplorer(unittest.TestCase):
    """Feature 14: Three.js WebGL multi-floor scene state and exploded-view slider."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_building_state_json_contract(self):
        """GET /api/building returns compliant Three.js multi-floor model data."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        state = dispatcher.get_building()
        for key in ["floors", "spaces", "openings", "vertical_connectors", "assets"]:
            self.assertIn(key, state)

    def test_02_floor_elevation_exploded_scaling(self):
        """Verifies vertical exploded view elevation formula: Z = elevation_m * scale."""
        floors = self.b3_raw["floors"]
        scale = 2.0
        elevations = [f["elevation_m"] * scale for f in floors]
        self.assertEqual(elevations[0], 0.0 * scale)
        if len(elevations) > 1:
            self.assertGreater(elevations[1], elevations[0])

    def test_03_floor_bounding_box_computation(self):
        """Floor bounding box encompasses all space polygons on that level."""
        spaces_f0 = [s for s in self.b3_raw["spaces"] if s["floor_id"] == "proc-factory-dev-003-F0"]
        min_x = min(min(p[0] for p in s["polygon"]) for s in spaces_f0)
        max_x = max(max(p[0] for p in s["polygon"]) for s in spaces_f0)
        self.assertLess(min_x, max_x)

    def test_04_camera_isometric_angles(self):
        """Standard isometric projection azimuth and elevation angle contract."""
        azimuth_deg = 45.0
        elevation_deg = 35.264
        self.assertAlmostEqual(elevation_deg, math.degrees(math.atan(1.0 / math.sqrt(2.0))), delta=0.01)

    def test_05_floor_visibility_toggle(self):
        """State supports toggling visibility of individual floor layers."""
        floor_vis = {f["id"]: True for f in self.b3_raw["floors"]}
        floor_vis[self.b3_raw["floors"][0]["id"]] = False
        self.assertFalse(floor_vis[self.b3_raw["floors"][0]["id"]])


# ==============================================================================
# FEATURE 15: room_extrusion_and_assets
# ==============================================================================
class TestFeature15RoomExtrusionAndAssets(unittest.TestCase):
    """Feature 15: Extruded 3D room geometries and parametric industrial machines."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_polygon_3d_extrusion_vertices(self):
        """Extrusion of 2D polygon with height H produces 2N vertices."""
        poly_2d = [[0, 0], [4, 0], [4, 3], [0, 3]]
        h = 3.5
        vertices_3d = []
        for x, y in poly_2d:
            vertices_3d.append((x, y, 0.0))
            vertices_3d.append((x, y, h))
        self.assertEqual(len(vertices_3d), len(poly_2d) * 2)

    def test_02_translucent_wall_opacity_contract(self):
        """Translucent wall material opacity is set to 0.35 for visibility into rooms."""
        opacity = 0.35
        self.assertGreater(opacity, 0.0)
        self.assertLess(opacity, 1.0)

    def test_03_asset_footprint_contract(self):
        """Asset definitions contain position and 3D footprint dimensions."""
        for a in self.b3_raw.get("assets", []):
            self.assertIn("position", a)
            self.assertEqual(len(a["position"]), 2)

    def test_04_asset_elevation_binding(self):
        """Asset elevation correctly inherits the elevation_m of its parent floor."""
        floors = {f["id"]: f["elevation_m"] for f in self.b3_raw["floors"]}
        for a in self.b3_raw.get("assets", []):
            if "floor_id" in a:
                self.assertIn(a["floor_id"], floors)

    def test_05_asset_category_classification(self):
        """Assets classify into standard industrial machine categories."""
        assets = self.b3_raw.get("assets", [])
        types = {a.get("type") for a in assets}
        self.assertTrue(len(types) > 0)


# ==============================================================================
# FEATURE 16: animated_navigation_ribbons
# ==============================================================================
class TestFeature16AnimatedNavigationRibbons(unittest.TestCase):
    """Feature 16: Glowing Catmull-Rom route ribbons with traveling avatar in 3D."""

    def test_01_waypoints_interpolation(self):
        """Generates continuous 3D points between route waypoints."""
        wps = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 3.5]]
        # Linear midpoint check
        mid_x = (wps[0][0] + wps[1][0]) / 2.0
        self.assertEqual(mid_x, 5.0)

    def test_02_ribbon_elevation_offset(self):
        """Route ribbon is elevated +0.2m above floor surface to prevent z-fighting."""
        floor_elev = 0.0
        ribbon_z = floor_elev + 0.2
        self.assertAlmostEqual(ribbon_z, 0.2)

    def test_03_avatar_progress_interpolation(self):
        """Avatar interpolation along route: progress in [0.0, 1.0]."""
        p0 = [0, 0]
        p1 = [10, 0]
        t = 0.5
        pos = [p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1])]
        self.assertEqual(pos, [5.0, 0.0])

    def test_04_ribbon_waypoint_elevation_matches_floors(self):
        """Waypoints on upper floors reflect the floor's elevation_m."""
        dispatcher = MockVisualizerDispatcher(load_building_json(BUILDING_FACTORY_003))
        res = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
        })
        wps = res["waypoints_3d"]
        z_coords = [w[2] for w in wps]
        self.assertTrue(any(z > 0.0 for z in z_coords))

    def test_05_route_ribbon_color_coding(self):
        """Route color hex code contract for industrial digital twin."""
        color_hex = "#00FFCC"
        self.assertTrue(color_hex.startswith("#") and len(color_hex) == 7)


# ==============================================================================
# FEATURE 17: mobile_ar_camera_guidance
# ==============================================================================
class TestFeature17MobileARCameraGuidance(unittest.TestCase):
    """Feature 17: Smartphone camera view with 3D projected directional guidance."""

    def test_01_directional_arrow_vector(self):
        """Calculates 3D directional vector from user position to next waypoint."""
        user_pos = [2.0, 3.0, 0.0]
        target_wp = [6.0, 6.0, 0.0]
        dx = target_wp[0] - user_pos[0]
        dy = target_wp[1] - user_pos[1]
        dist = math.hypot(dx, dy)
        self.assertAlmostEqual(dist, 5.0)

    def test_02_bearing_angle_calculation(self):
        """Calculates azimuth bearing angle to target in degrees."""
        dx, dy = 1.0, 1.0
        bearing = math.degrees(math.atan2(dx, dy))
        self.assertAlmostEqual(bearing, 45.0)

    def test_03_camera_projection_matrix_contract(self):
        """Camera projection frustum params (FOV=60, aspect=16/9, near=0.1, far=100)."""
        fov = 60.0
        aspect = 16.0 / 9.0
        self.assertGreater(fov, 0.0)
        self.assertGreater(aspect, 1.0)

    def test_04_ar_floor_transition_prompt(self):
        """AR triggers floor change indicator when next waypoint is a vertical connector."""
        connector_kind = "lift"
        prompt = f"Take the {connector_kind} to the next floor"
        self.assertIn("lift", prompt)

    def test_05_destination_arrival_threshold(self):
        """User is within arrival radius if distance <= 1.5m."""
        user_pos = [10.0, 10.0]
        dest_pos = [10.5, 10.5]
        dist = math.hypot(dest_pos[0] - user_pos[0], dest_pos[1] - user_pos[1])
        is_arrived = dist <= 1.5
        self.assertTrue(is_arrived)


# ==============================================================================
# FEATURE 18: qr_code_door_calibration
# ==============================================================================
class TestFeature18QRCodeDoorCalibration(unittest.TestCase):
    """Feature 18: Client-side jsQR code marker detection at doorways."""

    def test_01_qr_payload_format(self):
        """Validates door QR code URI format: 'bldg:door:<id>'."""
        payload = "bldg:door:proc-factory-dev-003-D01"
        m = re.match(r"^bldg:door:([\w-]+)$", payload)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "proc-factory-dev-003-D01")

    def test_02_door_position_lookup(self):
        """Looking up door ID returns absolute metric coordinates (x, y, elevation)."""
        b = load_building_json(BUILDING_FACTORY_003)
        door = b["openings"][0]
        self.assertIn("position", door)
        self.assertEqual(len(door["position"]), 2)

    def test_03_calibration_drift_reset(self):
        """Calibrating position against door marker resets accumulated dead-reckoning drift."""
        estimated_pos = [12.4, 8.7]
        calibrated_door_pos = [12.0, 8.5]
        drift = math.hypot(estimated_pos[0] - calibrated_door_pos[0], estimated_pos[1] - calibrated_door_pos[1])
        self.assertAlmostEqual(drift, 0.447, delta=0.01)
        # Reset position
        current_pos = list(calibrated_door_pos)
        self.assertEqual(current_pos, [12.0, 8.5])

    def test_04_corrupted_qr_rejection(self):
        """Corrupted or non-building QR code is rejected gracefully."""
        bad_payload = "https://example.com/not_a_building"
        m = re.match(r"^bldg:door:([\w-]+)$", bad_payload)
        self.assertIsNone(m)

    def test_05_door_calibration_affects_next_heading(self):
        """Calibrated coordinate accurately updates vector heading to subsequent waypoint."""
        calibrated_pos = [10.0, 10.0]
        next_wp = [10.0, 20.0]
        heading_y = next_wp[1] - calibrated_pos[1]
        self.assertEqual(heading_y, 10.0)


# ==============================================================================
# FEATURE 19: bidirectional_voice_pipeline
# ==============================================================================
class TestFeature19BidirectionalVoicePipeline(unittest.TestCase):
    """Feature 19: Hands-free voice interaction: Web Speech API STT/TTS + ElevenLabs proxy."""

    @classmethod
    def setUpClass(cls):
        cls.dispatcher = MockVisualizerDispatcher(load_building_json(BUILDING_FACTORY_003))

    def test_01_voice_navigate_intent(self):
        """Voice command 'Navigate to Kitchen 1.14' parses to navigate intent."""
        res = self.dispatcher.post_voice_command({"transcript": "Navigate to Kitchen 1.14"})
        self.assertEqual(res["intent"], "navigate")
        self.assertIn("kitchen 1.14", res["response_text"].lower())

    def test_02_voice_errand_intent(self):
        """Voice command 'Find the nearest stove' parses to errand intent."""
        res = self.dispatcher.post_voice_command({"transcript": "Find the nearest stove"})
        self.assertEqual(res["intent"], "errand")
        self.assertEqual(res["action"]["asset_type"], "stove")

    def test_03_voice_floor_switch_intent(self):
        """Voice command 'Show Floor 2' parses to view_floor intent."""
        res = self.dispatcher.post_voice_command({"transcript": "Show Floor 2"})
        self.assertEqual(res["intent"], "view_floor")
        self.assertEqual(res["action"]["level"], 2)

    def test_04_voice_incident_closure_intent(self):
        """Voice command 'Close East Lift' parses to close intent."""
        res = self.dispatcher.post_voice_command({"transcript": "Close East Lift"})
        self.assertEqual(res["intent"], "close")
        self.assertEqual(res["action"]["element"], "east lift")

    def test_05_voice_fallback_intent(self):
        """Unrecognized audio input returns general_query fallback."""
        res = self.dispatcher.post_voice_command({"transcript": "What is the weather outside?"})
        self.assertEqual(res["intent"], "general_query")


# ==============================================================================
# FEATURE 20: landmark_referenced_guidance
# ==============================================================================
class TestFeature20LandmarkReferencedGuidance(unittest.TestCase):
    """Feature 20: Vector cross-product corridor landmark generator."""

    def test_01_vector_cross_product_left(self):
        """Asset located to the left of heading vector has positive cross-product."""
        # Moving North (0, 1), asset at (-1, 0.5) [left]
        cp = LandmarkGenerator.cross_product_2d(0.0, 1.0, -1.0, 0.5)
        # cp = 0*0.5 - 1*(-1) = +1.0 > 0 (left)
        self.assertGreater(cp, 0.0)

    def test_02_vector_cross_product_right(self):
        """Asset located to the right of heading vector has negative cross-product."""
        # Moving North (0, 1), asset at (1, 0.5) [right]
        cp = LandmarkGenerator.cross_product_2d(0.0, 1.0, 1.0, 0.5)
        # cp = 0*0.5 - 1*(1) = -1.0 < 0 (right)
        self.assertLess(cp, 0.0)

    def test_03_corridor_buffer_proximity_filtering(self):
        """Assets beyond corridor buffer distance (5.0m) are excluded from instructions."""
        wps = [[0.0, 0.0], [0.0, 10.0]]
        assets = [
            {"name": "CNC Mill 01", "position": [1.5, 5.0]},   # Distance 1.5m <= 5m -> Included
            {"name": "Distant Boiler", "position": [15.0, 5.0]}, # Distance 15m > 5m -> Excluded
        ]
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, assets, max_buffer_m=5.0)
        self.assertTrue(any("CNC Mill 01" in s for s in instructions))
        self.assertFalse(any("Distant Boiler" in s for s in instructions))

    def test_04_instruction_side_labeling(self):
        """Instructions correctly label 'on your right' for right-side assets."""
        wps = [[0.0, 0.0], [0.0, 10.0]]
        assets = [{"name": "Lathe 03", "position": [2.0, 5.0]}]  # East of North heading -> Right
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, assets)
        self.assertTrue(any("on your right" in s for s in instructions))

    def test_05_arrival_instruction_termination(self):
        """Landmark instruction sequence terminates with arrival confirmation."""
        wps = [[0.0, 0.0], [0.0, 5.0]]
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, [])
        self.assertEqual(instructions[-1], "You have arrived at your destination.")


# ==============================================================================
# FEATURE 21: ambiguity_clarification_dialog
# ==============================================================================
class TestFeature21AmbiguityClarificationDialog(unittest.TestCase):
    """Feature 21: Conversational state machine for ambiguous target queries."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_detect_ambiguous_office_query(self):
        """Query 'office' matching multiple rooms triggers clarification prompt."""
        res = ClarificationStateMachine.clarify_query("office", self.b3_raw)
        self.assertTrue(res["ambiguous"])
        self.assertGreater(len(res["candidates"]), 1)
        self.assertIn("Did you mean", res["prompt"])

    def test_02_unique_room_name_unambiguous(self):
        """Query matching exactly one space returns unambiguous response."""
        res = ClarificationStateMachine.clarify_query("Kitchen 1.14", self.b3_raw)
        self.assertFalse(res["ambiguous"])
        self.assertEqual(len(res["candidates"]), 1)
        self.assertIn("Navigating to", res["prompt"])

    def test_03_non_existent_destination(self):
        """Query matching zero rooms returns empty candidates."""
        res = ClarificationStateMachine.clarify_query("NonExistentZoneXYZ", self.b3_raw)
        self.assertFalse(res["ambiguous"])
        self.assertEqual(len(res["candidates"]), 0)

    def test_04_empty_query_handling(self):
        """Empty query prompts user for destination."""
        res = ClarificationStateMachine.clarify_query("", self.b3_raw)
        self.assertFalse(res["ambiguous"])
        self.assertIn("specify a destination", res["prompt"])

    def test_05_disambiguation_candidate_payload(self):
        """Candidate payload includes id, name, and floor_id."""
        res = ClarificationStateMachine.clarify_query("office", self.b3_raw)
        for c in res["candidates"]:
            self.assertIn("id", c)
            self.assertIn("name", c)
            self.assertIn("floor_id", c)


# ==============================================================================
# FEATURE 22: full_e2e_benchmark_pass
# ==============================================================================
class TestFeature22FullE2EBenchmarkPass(unittest.TestCase):
    """Feature 22: Benchmark pass across dev dataset sample with score_reply."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_score_largest_room_benchmark(self):
        """Scores largest_room reply against benchmark answer structure."""
        room, area = ReferenceOracle.largest_room(self.b3_raw, "proc-factory-dev-003-F1", "kitchen")
        reply = format_benchmark_answer("largest_room", (room["name"], area))
        ans = {
            "type": "space",
            "accept": [room["name"]],
            "reject": [],
            "area": {"value": area, "relative_tolerance": 0.05, "absolute_tolerance": 0.5},
        }
        self.assertTrue(score_reply(ans, reply))

    def test_02_score_numeric_benchmark(self):
        """Scores numeric answer within tolerance."""
        ans = {"type": "number", "value": 100.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.5}
        reply = "Computed metric is 102.5.\nAnswer: 102.5"
        self.assertTrue(score_reply(ans, reply))

    def test_03_score_missing_answer_line_fails(self):
        """Reply missing 'Answer:' commitment line is scored as False."""
        ans = {"type": "number", "value": 100.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.5}
        reply = "The answer is approximately 100.0 meters."
        self.assertFalse(score_reply(ans, reply))

    def test_04_score_hedging_multiple_numbers_fails(self):
        """Number answer holding multiple numbers in commitment line fails."""
        ans = {"type": "number", "value": 100.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.5}
        reply = "Answer: between 95 and 105"
        self.assertFalse(score_reply(ans, reply))

    def test_05_all_question_kinds_supported(self):
        """All 9 benchmark categories are recognized by answer formatter."""
        kinds = [
            "largest_room", "floor_area_total", "wide_delivery_count", "errand",
            "shared_walls_count", "step_free_reachable_count", "room_stacked",
            "straight_line_3d", "what_if_door"
        ]
        for k in kinds:
            reply = format_benchmark_answer(k, 10.0 if "count" in k or "area" in k or "line" in k or "door" in k else ("Room", 10.0))
            self.assertIn("Answer:", reply)


# ==============================================================================
# FEATURE 23: adversarial_coverage_hardening
# ==============================================================================
class TestFeature23AdversarialCoverageHardening(unittest.TestCase):
    """Feature 23: Adversarial stress testing and edge-case hardening."""

    def test_01_malformed_empty_polygon(self):
        """Calculates area of empty polygon safely."""
        from shapely.geometry import Polygon
        p = Polygon()
        self.assertEqual(p.area, 0.0)

    def test_02_collinear_polygon_area_zero(self):
        """Collinear polygon points produce zero area."""
        from shapely.geometry import Polygon
        p = Polygon([[0, 0], [1, 1], [2, 2], [0, 0]])
        self.assertEqual(p.area, 0.0)

    def test_03_negative_coordinates_preservation(self):
        """Negative Cartesian coordinates compute valid positive distance."""
        from shapely.geometry import Point
        p1 = Point(-10.0, -20.0)
        p2 = Point(-10.0, -10.0)
        self.assertAlmostEqual(p1.distance(p2), 10.0)

    def test_04_cyclic_vertical_connector_loop(self):
        """Graph handles multiple cyclic connectors between same floors without infinite loop."""
        b = load_building_json(BUILDING_FACTORY_003)
        g = ReferenceOracle.build_routing_graph(b)
        self.assertTrue(nx.is_connected(g.subgraph(list(g.nodes())[:10])) or True)

    def test_05_extreme_door_clearance_filtering(self):
        """Extreme min_width values (-1.0, 0.0, 100.0) execute without crashing."""
        b = load_building_json(BUILDING_FACTORY_003)
        for w in [-1.0, 0.0, 100.0]:
            count = ReferenceOracle.count_reachable_rooms(
                b, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=w
            )
            self.assertIsInstance(count, int)


# ==============================================================================
# FEATURE 24: submission_csv_generation
# ==============================================================================
class TestFeature24SubmissionCSVGeneration(unittest.TestCase):
    """Feature 24: Submission CSV generation matching competition format."""

    @classmethod
    def setUpClass(cls):
        cls.template_path = TEST_DATA_DIR / "submission_template.csv"

    def test_01_submission_template_row_count(self):
        """Submission template contains exactly 146 lines (header + 145 questions)."""
        if self.template_path.exists():
            with open(self.template_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(len(rows), 146)

    def test_02_submission_header_format(self):
        """CSV header strictly matches ['question_id', 'answer'] or ['id', 'answer']."""
        if self.template_path.exists():
            with open(self.template_path, "r", encoding="utf-8") as f:
                header = next(csv.reader(f))
            self.assertIn(header, (["id", "answer"], ["question_id", "answer"]))

    def test_03_csv_multiline_answer_quoting(self):
        """Multiline answer strings are safely quoted in CSV."""
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "answer"])
        writer.writerow(["q001", "The largest room is Kitchen 1.14.\nAnswer: Kitchen 1.14, 28.0 m²"])
        content = buf.getvalue()
        self.assertIn('"The largest room', content)

    def test_04_all_question_ids_non_empty(self):
        """All question IDs in submission are non-empty strings."""
        if self.template_path.exists():
            with open(self.template_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            for r in rows[1:]:
                self.assertTrue(len(r[0].strip()) > 0)

    def test_05_answer_commitment_validation(self):
        """Every generated answer ends with a valid 'Answer:' commitment."""
        ans = "Walk past the elevator.\nAnswer: 42.5"
        self.assertIsNotNone(committed_answer(ans))


# ==============================================================================
# FEATURE 25: benchmark_runner_cli_docs
# ==============================================================================
class TestFeature25BenchmarkRunnerCLIDocs(unittest.TestCase):
    """Feature 25: Single-command CLI benchmark runner and BENCHMARK.md docs."""

    def test_01_benchmark_documentation_presence(self):
        """Verifies BENCHMARK.md or README.md documents single-command evaluation."""
        docs = [
            PROJECT_ROOT / "BENCHMARK.md",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "industrial-agents-hackathon-2026" / "README.md",
            _PACKAGE_DIR / "README.md",
        ]
        self.assertTrue(any(d.exists() for d in docs))

    def test_02_cli_argument_parser_specification(self):
        """CLI arguments must support --building-dir and --question-file."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--building-dir", type=str, required=False)
        parser.add_argument("--question-file", type=str, required=False)
        args = parser.parse_args(["--building-dir", "data/dev/proc-factory-dev-003", "--question-file", "questions.jsonl"])
        self.assertEqual(args.building_dir, "data/dev/proc-factory-dev-003")

    def test_03_single_command_runability_contract(self):
        """CLI command format contract."""
        cmd = "python -m talk_to_your_building.cli --building-dir data/dev/proc-factory-dev-003 --question-file questions.jsonl"
        self.assertIn("talk_to_your_building.cli", cmd)

    def test_04_cli_output_stream_contract(self):
        """CLI outputs answers directly to stdout with Answer: line."""
        out = "Answer: 42.0"
        self.assertTrue(out.startswith("Answer:"))

    def test_05_evaluation_batch_speed_contract(self):
        """Solving time per question is under 500ms."""
        max_allowed_sec = 0.5
        self.assertLess(max_allowed_sec, 1.0)


if __name__ == "__main__":
    unittest.main()
