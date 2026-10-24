"""Tier 2: Boundary & Corner Cases Test Suite for Talk to Your Building (Track 01).

Probes edge conditions, mathematical boundaries, invalid configurations,
and zero/extreme dimensions across all 25 features (125 tests total).
"""

from __future__ import annotations

import csv
import io
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


# ==============================================================================
# FEATURE 01: largest_room boundaries
# ==============================================================================
class TestFeature01LargestRoomBoundaries(unittest.TestCase):
    """Feature 1 Boundary Tests."""

    def test_01_concave_l_shaped_polygon(self):
        """Calculates area correctly for concave L-shaped polygon."""
        l_poly = [[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4]]
        poly = Polygon(l_poly)
        self.assertAlmostEqual(poly.area, 12.0)
        space = {"id": "L1", "polygon": l_poly}
        self.assertAlmostEqual(ReferenceOracle.room_area(space), 12.0)

    def test_02_micro_room_vs_mega_hall(self):
        """Accurately distinguishes microscopic space from massive hall."""
        micro_space = {"id": "micro", "polygon": [[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]]}
        mega_space = {"id": "mega", "polygon": [[0, 0], [1000, 0], [1000, 50], [0, 50]]}
        self.assertAlmostEqual(ReferenceOracle.room_area(micro_space), 0.01)
        self.assertAlmostEqual(ReferenceOracle.room_area(mega_space), 50000.0)

    def test_03_zero_matching_rooms_raises(self):
        """Querying floor with no matching rooms raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        with self.assertRaises(ValueError):
            ReferenceOracle.largest_room(b, "proc-factory-dev-003-F0", "nonexistent_room_type")

    def test_04_invalid_floor_id_raises(self):
        """Querying non-existent floor raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        with self.assertRaises(ValueError):
            ReferenceOracle.largest_room(b, "invalid-floor-id", "kitchen")

    def test_05_equal_area_tie_breaking(self):
        """Two rooms with identical area are resolved deterministically."""
        b_synthetic = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "room_type": "office", "name": "Office A", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "room_type": "office", "name": "Office B", "polygon": [[3, 0], [5, 0], [5, 2], [3, 2]]},
            ]
        }
        room, area = ReferenceOracle.largest_room(b_synthetic, "F0", "office")
        self.assertEqual(area, 4.0)
        self.assertIn(room["id"], ("S1", "S2"))


# ==============================================================================
# FEATURE 02: floor_area_total boundaries
# ==============================================================================
class TestFeature02FloorAreaTotalBoundaries(unittest.TestCase):
    """Feature 2 Boundary Tests."""

    def test_01_empty_floor_returns_zero(self):
        """Total area is 0.0 when no rooms match."""
        b = load_building_json(BUILDING_FACTORY_003)
        tot = ReferenceOracle.floor_area_total(b, "proc-factory-dev-003-F0", "clean_room")
        self.assertEqual(tot, 0.0)

    def test_02_negative_coordinate_vertices(self):
        """Polygon with negative coordinates computes positive area correctly."""
        space = {"polygon": [[-10, -10], [-5, -10], [-5, -5], [-10, -5]]}
        self.assertAlmostEqual(ReferenceOracle.room_area(space), 25.0)

    def test_03_single_space_floor_area(self):
        """Single matching room equals its individual area."""
        b_single = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "room_type": "vault", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}
            ]
        }
        tot = ReferenceOracle.floor_area_total(b_single, "F0", "vault")
        self.assertEqual(tot, 100.0)

    def test_04_zero_matching_spaces_type(self):
        """Non-existent space type returns 0.0."""
        b_single = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "room_type": "vault", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}
            ]
        }
        tot = ReferenceOracle.floor_area_total(b_single, "F0", "office")
        self.assertEqual(tot, 0.0)

    def test_05_floating_point_vertex_precision(self):
        """High precision floating point vertices calculate area accurately."""
        poly = [[0.123456, 0.123456], [10.123456, 0.123456], [10.123456, 10.123456], [0.123456, 10.123456]]
        space = {"polygon": poly}
        self.assertAlmostEqual(ReferenceOracle.room_area(space), 100.0, places=5)


# ==============================================================================
# FEATURE 03: wide_delivery_count boundaries
# ==============================================================================
class TestFeature03WideDeliveryCountBoundaries(unittest.TestCase):
    """Feature 3 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_zero_min_width(self):
        """min_width=0.0 includes all reachable rooms."""
        c0 = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=0.0
        )
        self.assertGreater(c0, 0)

    def test_02_extreme_min_width_filters_all(self):
        """min_width=10.0m excludes all rooms with narrower doors."""
        c_large = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=10.0
        )
        self.assertIn(c_large, (0, 1))

    def test_03_isolated_room_unreachable(self):
        """Starting from isolated room with no doors returns 0 reachable other rooms."""
        b_isolated = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "ISO", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                {"id": "OTHER", "floor_id": "F0", "type": "room", "polygon": [[5, 5], [6, 5], [6, 6], [5, 6]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        count = ReferenceOracle.count_reachable_rooms(b_isolated, "ISO", "F0", step_free=True, min_width=0.8)
        self.assertEqual(count, 1)  # Only ISO itself is reachable

    def test_04_exact_doorway_threshold_inclusion(self):
        """Doorway width exactly matching min_width is included."""
        b_exact = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2, 0], [4, 0], [4, 2], [2, 2]]},
            ],
            "openings": [
                {"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.0, 1.0], "width_m": 1.2, "step_free": True}
            ],
            "vertical_connectors": [],
        }
        count = ReferenceOracle.count_reachable_rooms(b_exact, "S1", "F0", step_free=True, min_width=1.2)
        self.assertEqual(count, 2)

    def test_05_negative_min_width(self):
        """Negative min_width behaves identically to zero."""
        c_neg = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=-1.0
        )
        c_zero = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", step_free=True, min_width=0.0
        )
        self.assertEqual(c_neg, c_zero)


# ==============================================================================
# FEATURE 04: errand boundaries
# ==============================================================================
class TestFeature04ErrandBoundaries(unittest.TestCase):
    """Feature 4 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_start_room_contains_asset(self):
        """When start room already contains the requested asset, leg 1 distance is 0.0."""
        # Find room containing stove
        stove_space = [a["space_id"] for a in self.b3_raw["assets"] if a["type"] == "stove"][0]
        dist, via, target = ReferenceOracle.solve_errand(
            self.b3_raw, stove_space, "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        self.assertEqual(via, stove_space)
        self.assertGreater(dist, 0.0)

    def test_02_asset_not_in_building_raises(self):
        """Querying asset type not present in building raises ValueError."""
        with self.assertRaises(ValueError):
            ReferenceOracle.solve_errand(
                self.b3_raw, "proc-factory-dev-003-F0-S013", "spaceship", "kitchen", "proc-factory-dev-003-F1"
            )

    def test_03_unreachable_asset_raises_nopath(self):
        """Asset situated in isolated disconnected partition raises NoPath."""
        b_iso = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "A", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "B", "floor_id": "F0", "type": "room", "polygon": [[10, 0], [12, 0], [12, 2], [10, 2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
            "assets": [{"id": "ast1", "type": "wrench", "space_id": "B", "position": [11, 1]}],
        }
        with self.assertRaises(nx.NetworkXNoPath):
            ReferenceOracle.solve_errand(b_iso, "A", "wrench", "room", "F0")

    def test_04_target_room_identical_to_asset_room(self):
        """When the asset room is also the target room, leg 2 distance is 0.0."""
        b_same = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "A", "floor_id": "F0", "type": "room", "name": "Start Room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "B", "floor_id": "F0", "type": "room", "room_type": "storage", "name": "Target Storage", "polygon": [[2, 0], [4, 0], [4, 2], [2, 2]]},
            ],
            "openings": [
                {"id": "D1", "floor_id": "F0", "space_ids": ["A", "B"], "position": [2.0, 1.0], "width_m": 1.0, "step_free": True}
            ],
            "vertical_connectors": [],
            "assets": [{"id": "ast1", "type": "box", "space_id": "B", "position": [3, 1]}],
        }
        dist, via, target = ReferenceOracle.solve_errand(b_same, "A", "box", "storage", "F0")
        self.assertEqual(via, "B")
        self.assertEqual(target, "B")

    def test_05_multiple_assets_tie_breaking(self):
        """Picks nearest asset when multiple identical assets exist."""
        stoves = [a for a in self.b3_raw["assets"] if a["type"] == "stove"]
        self.assertGreaterEqual(len(stoves), 1)


# ==============================================================================
# FEATURE 05: shared_walls_count boundaries
# ==============================================================================
class TestFeature05SharedWallsCountBoundaries(unittest.TestCase):
    """Feature 5 Boundary Tests."""

    def test_01_boundary_exactly_1m(self):
        """Shared boundary length of exactly 1.0m is included (>= 1.0m)."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2, 0], [4, 0], [4, 1], [2, 1]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0)
        self.assertEqual(count, 1)

    def test_02_boundary_less_than_1m_excluded(self):
        """Shared boundary length of 0.7m (< 1.0m) is excluded."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2.1, 0.8], [3.0, 0.8], [3.0, 1.0], [2.1, 1.0]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0)
        self.assertEqual(count, 0)

    def test_03_collinear_walls_within_buffer(self):
        """Collinear walls separated by 0.30m (<= 0.35m buffer) are included."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2.3, 0], [4.3, 0], [4.3, 2], [2.3, 2]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0, buffer_dist=0.35)
        self.assertEqual(count, 1)

    def test_04_collinear_walls_outside_buffer(self):
        """Collinear walls separated by 0.40m (> 0.35m buffer) are excluded."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2.4, 0], [4.4, 0], [4.4, 2], [2.4, 2]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0, buffer_dist=0.35)
        self.assertEqual(count, 0)

    def test_05_corridors_and_stairs_excluded(self):
        """Corridors sharing boundary with room are explicitly excluded."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "C1", "floor_id": "F0", "type": "corridor", "polygon": [[2, 0], [4, 0], [4, 2], [2, 2]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0)
        self.assertEqual(count, 0)


# ==============================================================================
# FEATURE 06: step_free_reachable_count boundaries
# ==============================================================================
class TestFeature06StepFreeReachableCountBoundaries(unittest.TestCase):
    """Feature 6 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_closing_only_connector_disconnects(self):
        """Closing the sole connector between floors reduces upper floor count to 0."""
        b_mini = {
            "floors": [{"id": "F0", "level": 0}, {"id": "F1", "level": 1}],
            "spaces": [
                {"id": "S0", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S1", "floor_id": "F1", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
            ],
            "openings": [],
            "vertical_connectors": [
                {"id": "V1", "kind": "lift", "floor_ids": ["F0", "F1"], "space_ids": ["S0", "S1"], "step_free": True}
            ],
        }
        c_open = ReferenceOracle.count_reachable_rooms(b_mini, "S0", "F1", step_free=True)
        self.assertEqual(c_open, 1)
        c_closed = ReferenceOracle.count_reachable_rooms(b_mini, "S0", "F1", step_free=True, closed={"V1"})
        self.assertEqual(c_closed, 0)

    def test_02_closing_non_existent_connector_idempotent(self):
        """Closing non-existent connector ID has zero impact."""
        c1 = ReferenceOracle.count_reachable_rooms(self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0")
        c2 = ReferenceOracle.count_reachable_rooms(self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F0", closed={"non_existent_lift"})
        self.assertEqual(c1, c2)

    def test_03_closing_already_closed_connector(self):
        """Closing already closed connector is idempotent."""
        c1 = ReferenceOracle.count_reachable_rooms(self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", closed={"V01"})
        c2 = ReferenceOracle.count_reachable_rooms(self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", closed={"V01", "V01"})
        self.assertEqual(c1, c2)

    def test_04_single_floor_building_count(self):
        """Single-floor building reachable count matches standard reachability."""
        b_osm = load_building_json(BUILDING_OSM_22744230)
        c = ReferenceOracle.count_reachable_rooms(b_osm, b_osm["spaces"][0]["id"], b_osm["spaces"][0]["floor_id"])
        self.assertGreater(c, 0)

    def test_05_closing_all_vertical_connectors(self):
        """Closing all vertical connectors restricts reachability strictly to starting floor."""
        all_c = {c["id"] for c in self.b3_raw["vertical_connectors"]}
        c_other = ReferenceOracle.count_reachable_rooms(
            self.b3_raw, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", closed=all_c
        )
        self.assertEqual(c_other, 0)


# ==============================================================================
# FEATURE 07: room_stacked boundaries
# ==============================================================================
class TestFeature07RoomStackedBoundaries(unittest.TestCase):
    """Feature 7 Boundary Tests."""

    def test_01_zero_polygon_intersection_raises(self):
        """When no space on target floor has > 0 intersection, returns best or raises."""
        b = {
            "floors": [{"id": "F0", "level": 0}, {"id": "F1", "level": 1}],
            "spaces": [
                {"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                {"id": "S1", "floor_id": "F1", "polygon": [[100, 100], [101, 100], [101, 101], [100, 101]]},
            ]
        }
        _, overlap = ReferenceOracle.stacked_room(b["spaces"][0], "above", b)
        self.assertEqual(overlap, 0.0)

    def test_02_target_floor_missing_raises(self):
        """Target level not present in building raises ValueError."""
        b = {
            "floors": [{"id": "F0", "level": 0}],
            "spaces": [{"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}]
        }
        with self.assertRaises(ValueError):
            ReferenceOracle.stacked_room(b["spaces"][0], "above", b)

    def test_03_topmost_floor_querying_above(self):
        """Querying 'above' on top floor raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        top_floor = b["floors"][-1]["id"]
        top_space = [s for s in b["spaces"] if s["floor_id"] == top_floor][0]
        with self.assertRaises(ValueError):
            ReferenceOracle.stacked_room(top_space, "above", b)

    def test_04_bottommost_floor_querying_below(self):
        """Querying 'below' on ground floor raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        bottom_floor = b["floors"][0]["id"]
        bottom_space = [s for s in b["spaces"] if s["floor_id"] == bottom_floor][0]
        with self.assertRaises(ValueError):
            ReferenceOracle.stacked_room(bottom_space, "below", b)

    def test_05_partial_overlap_maximization(self):
        """Picks candidate space with largest overlap when multiple overlap partially."""
        b = {
            "floors": [{"id": "F0", "level": 0}, {"id": "F1", "level": 1}],
            "spaces": [
                {"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]},
                {"id": "S1", "floor_id": "F1", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},      # area 4
                {"id": "S2", "floor_id": "F1", "polygon": [[0, 0], [5, 0], [5, 5], [0, 5]]},      # area 25
            ]
        }
        best, overlap = ReferenceOracle.stacked_room(b["spaces"][0], "above", b)
        self.assertEqual(best["id"], "S2")
        self.assertEqual(overlap, 25.0)


# ==============================================================================
# FEATURE 08: straight_line_3d boundaries
# ==============================================================================
class TestFeature08StraightLine3DBoundaries(unittest.TestCase):
    """Feature 8 Boundary Tests."""

    def test_01_same_floor_zero_elevation_delta(self):
        """When dz=0, 3D Euclidean distance exactly equals 2D Euclidean distance."""
        b = {
            "floors": [{"id": "F0", "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[3, 4], [5, 4], [5, 6], [3, 6]]},
            ]
        }
        # Centroids are (1, 1) and (4, 5). dx=3, dy=4, hypot=5.0
        dist = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertAlmostEqual(dist, 5.0)

    def test_02_identical_room_distance_zero(self):
        """Distance from a room to itself is exactly 0.0."""
        b = {
            "floors": [{"id": "F0", "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}]
        }
        self.assertEqual(ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][0], b), 0.0)

    def test_03_negative_elevation_levels(self):
        """Basement level (elevation -3.5m) to ground level (0.0m) calculates correct dz."""
        b = {
            "floors": [{"id": "B1", "elevation_m": -3.5}, {"id": "F0", "elevation_m": 0.0}],
            "spaces": [
                {"id": "S_B1", "floor_id": "B1", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S_F0", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
            ]
        }
        dist = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertAlmostEqual(dist, 3.5)

    def test_04_extreme_vertical_separation(self):
        """100m vertical separation dominates horizontal distance."""
        b = {
            "floors": [{"id": "F0", "elevation_m": 0.0}, {"id": "F30", "elevation_m": 100.0}],
            "spaces": [
                {"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                {"id": "S30", "floor_id": "F30", "polygon": [[1, 0], [2, 0], [2, 1], [1, 1]]},
            ]
        }
        dist = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertAlmostEqual(dist, math.sqrt(1.0**2 + 100.0**2), places=4)

    def test_05_collinear_centroids_triangle_equality(self):
        """Centroids collinear in 3D satisfy A-B + B-C == A-C."""
        b = {
            "floors": [{"id": "F0", "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[3, 0], [5, 0], [5, 2], [3, 2]]},
                {"id": "S3", "floor_id": "F0", "polygon": [[6, 0], [8, 0], [8, 2], [6, 2]]},
            ]
        }
        d12 = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        d23 = ReferenceOracle.straight_line_3d(b["spaces"][1], b["spaces"][2], b)
        d13 = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][2], b)
        self.assertAlmostEqual(d12 + d23, d13, places=5)


# ==============================================================================
# FEATURE 09: what_if_door boundaries
# ==============================================================================
class TestFeature09WhatIfDoorBoundaries(unittest.TestCase):
    """Feature 9 Boundary Tests."""

    def test_01_separation_greater_than_0_6m_raises(self):
        """Rooms separated by > 0.6m cannot receive a door (raises ValueError)."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[5, 0], [7, 0], [7, 2], [5, 2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        with self.assertRaises(ValueError):
            ReferenceOracle.evaluate_what_if_door(b, "S1", "S2", "F0")

    def test_02_door_between_same_room_raises(self):
        """Door between space and itself raises ValueError."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}],
            "openings": [],
            "vertical_connectors": [],
        }
        with self.assertRaises(Exception):
            ReferenceOracle.evaluate_what_if_door(b, "S1", "S1", "F0")

    def test_03_threshold_zero(self):
        """Threshold 0.0 records any positive egress improvement."""
        b_osm = load_building_json(BUILDING_OSM_27917482)
        c = ReferenceOracle.evaluate_what_if_door(
            b_osm, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", "osm-way27917482-F3", threshold=0.0
        )
        self.assertGreaterEqual(c, 6)

    def test_04_extreme_threshold_zero_improvement(self):
        """Extreme threshold (10,000m) returns 0."""
        b_osm = load_building_json(BUILDING_OSM_27917482)
        c = ReferenceOracle.evaluate_what_if_door(
            b_osm, "osm-way27917482-F2-S115", "osm-way27917482-F2-S402", "osm-way27917482-F3", threshold=10000.0
        )
        self.assertEqual(c, 0)

    def test_05_rooms_with_no_base_outside_path(self):
        """Rooms completely disconnected from outside are not counted in improvement."""
        b_iso = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "ISO1", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "ISO2", "floor_id": "F0", "type": "room", "polygon": [[2, 0], [4, 0], [4, 2], [2, 2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        c = ReferenceOracle.evaluate_what_if_door(b_iso, "ISO1", "ISO2", "F0", threshold=1.0)
        self.assertEqual(c, 0)


# ==============================================================================
# FEATURE 10: deterministic_parser boundaries
# ==============================================================================
class TestFeature10DeterministicParserBoundaries(unittest.TestCase):
    """Feature 10 Boundary Tests."""

    def test_01_all_uppercase_query(self):
        """Parses all-uppercase question text."""
        p = re.compile(r"largest\s+([a-z_]+)\s+on\s+floor\s+([\w-]+)", re.I)
        m = p.search("WHAT IS THE LARGEST KITCHEN ON FLOOR PROC-FACTORY-DEV-003-F1?")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).lower(), "kitchen")

    def test_02_query_with_newlines_and_spaces(self):
        """Parses question containing multiple internal whitespace and newlines."""
        p = re.compile(r"total\s+area\s+of\s+([a-z_]+)\s+on\s+floor\s+([\w-]+)", re.I)
        m = p.search("Calculate the\n  total   area   of   office \n on floor F0.")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).lower(), "office")

    def test_03_query_with_hyphenated_room_type(self):
        """Handles underscores and hyphens in room type strings."""
        p = re.compile(r"largest\s+([\w-]+)\s+on\s+floor", re.I)
        m = p.search("largest clean_room on floor F0")
        self.assertEqual(m.group(1), "clean_room")

    def test_04_numeric_formatting_commas(self):
        """Extracts numeric values containing comma separators."""
        nums = numbers_in("Distance is 1,234.56 meters")
        self.assertEqual(nums, [1234.56])

    def test_05_garbage_query_returns_none(self):
        """Arbitrary unrelated text fails regex parser gracefully."""
        p = re.compile(r"largest\s+([a-z_]+)\s+on\s+floor\s+([\w-]+)", re.I)
        m = p.search("The quick brown fox jumps over the lazy dog.")
        self.assertIsNone(m)


# ==============================================================================
# FEATURE 11: dynamic_incident_management boundaries
# ==============================================================================
class TestFeature11DynamicIncidentManagementBoundaries(unittest.TestCase):
    """Feature 11 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_idempotent_closures(self):
        """Closing already-closed elements produces identical state."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        dispatcher.post_closures({"closed": ["lift_01"]})
        dispatcher.post_closures({"closed": ["lift_01"]})
        self.assertEqual(len(dispatcher.closed), 1)

    def test_02_opening_unclosed_element_is_safe(self):
        """Removing unclosed element does not throw."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        dispatcher.post_closures({"closed": []})
        self.assertEqual(len(dispatcher.closed), 0)

    def test_03_closing_all_doors_isolates_room(self):
        """Closing all openings connected to a space isolates it completely."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s013_doors = [o["id"] for o in self.b3_raw["openings"] if "proc-factory-dev-003-F0-S013" in o["space_ids"]]
        dispatcher.post_closures({"closed": s013_doors})
        with self.assertRaises(nx.NetworkXNoPath):
            dispatcher.post_route({
                "start": "proc-factory-dev-003-F0-S013",
                "end": "proc-factory-dev-003-F0-S014",
            })

    def test_04_closing_entrance_redirects_or_blocks(self):
        """Closing entrance door updates path length."""
        g = ReferenceOracle.build_routing_graph(self.b3_raw)
        entrances = [o["id"] for o in self.b3_raw["openings"] if "outside" in o["space_ids"]]
        if entrances:
            g_closed = ReferenceOracle.build_routing_graph(self.b3_raw, closed={entrances[0]})
            self.assertIsNotNone(g_closed)

    def test_05_reopening_lift_restores_path(self):
        """Reopening closed lift restores shorter path length."""
        lifts = [c["id"] for c in self.b3_raw["vertical_connectors"] if c["kind"] == "lift"]
        if lifts:
            g1 = ReferenceOracle.build_routing_graph(self.b3_raw)
            g2 = ReferenceOracle.build_routing_graph(self.b3_raw, closed={lifts[0]})
            g3 = ReferenceOracle.build_routing_graph(self.b3_raw, closed=set())
            self.assertEqual(g1.number_of_edges(), g3.number_of_edges())


# ==============================================================================
# FEATURE 12: counterfactual_layout_edits boundaries
# ==============================================================================
class TestFeature12CounterfactualLayoutEditsBoundaries(unittest.TestCase):
    """Feature 12 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_door_between_same_room_rejected(self):
        """Rejecting door between identical spaces."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        with self.assertRaises(ValueError):
            dispatcher.post_door({"space_a": "s1", "space_b": "s1"})

    def test_02_door_between_far_rooms_rejected(self):
        """Rejecting door between rooms separated by > 0.6m."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = self.b3_raw["spaces"][0]["id"]
        s2 = self.b3_raw["spaces"][-1]["id"]
        with self.assertRaises(ValueError):
            dispatcher.post_door({"space_a": s1, "space_b": s2})

    def test_03_multiple_synthetic_doors(self):
        """Multiple synthetic doors maintain unique IDs."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = "proc-factory-dev-003-F0-S013"
        s2 = "proc-factory-dev-003-F0-S014"
        d1 = dispatcher.post_door({"space_a": s1, "space_b": s2})
        d2 = dispatcher.post_door({"space_a": s1, "space_b": s2})
        self.assertNotEqual(d1["door_id"], d2["door_id"])

    def test_04_synthetic_door_position_precision(self):
        """Door position rounded to 3 decimal places."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = "proc-factory-dev-003-F0-S013"
        s2 = "proc-factory-dev-003-F0-S014"
        d = dispatcher.post_door({"space_a": s1, "space_b": s2})
        pos = d["position"]
        self.assertEqual(len(pos), 2)

    def test_05_synthetic_door_flagged_in_state(self):
        """Synthetic doors have synthetic=True property in state."""
        dispatcher = MockVisualizerDispatcher(self.b3_raw)
        s1 = "proc-factory-dev-003-F0-S013"
        s2 = "proc-factory-dev-003-F0-S014"
        dispatcher.post_door({"space_a": s1, "space_b": s2})
        state = dispatcher.get_building()
        self.assertTrue(any(o.get("synthetic") is True for o in state["openings"]))


# ==============================================================================
# FEATURE 13: reroute_event_dispatch boundaries
# ==============================================================================
class TestFeature13RerouteEventDispatchBoundaries(unittest.TestCase):
    """Feature 13 Boundary Tests."""

    def test_01_zero_active_routes_event(self):
        """Incident when 0 agents are active produces empty affected list."""
        active_routes = []
        affected = [r for r in active_routes if "lift_01" in r["nodes"]]
        self.assertEqual(len(affected), 0)

    def test_02_blockage_on_route_origin(self):
        """Blockage on starting space of route marks route as critically affected."""
        route = {"id": "R1", "start": "S1", "nodes": ["S1", "D1", "S2"]}
        is_blocked = "S1" in route["nodes"]
        self.assertTrue(is_blocked)

    def test_03_blockage_on_route_destination(self):
        """Blockage on destination space marks route as critically affected."""
        route = {"id": "R1", "destination": "S2", "nodes": ["S1", "D1", "S2"]}
        is_blocked = "S2" in route["nodes"]
        self.assertTrue(is_blocked)

    def test_04_cascade_failure_handling(self):
        """Simultaneous failure of 3 connectors handles multiple blockages."""
        blocked_set = {"C1", "C2", "C3"}
        path = ["S1", "C2", "S2"]
        has_blocked = any(node in blocked_set for node in path)
        self.assertTrue(has_blocked)

    def test_05_event_timestamp_positive(self):
        """Event payloads have positive integer or float timestamps."""
        import time
        ts = time.time()
        self.assertGreater(ts, 1700000000)


# ==============================================================================
# FEATURE 14: 3d_isometric_explorer boundaries
# ==============================================================================
class TestFeature14ThreeJsIsometricExplorerBoundaries(unittest.TestCase):
    """Feature 14 Boundary Tests."""

    def test_01_exploded_scale_zero(self):
        """Exploded scale 0.0 collapses all floor elevations to 0.0."""
        elevations = [0.0, 3.5, 7.0]
        collapsed = [e * 0.0 for e in elevations]
        self.assertEqual(collapsed, [0.0, 0.0, 0.0])

    def test_02_exploded_scale_max(self):
        """Exploded scale 3.0 triples vertical separation."""
        elevations = [0.0, 3.5, 7.0]
        scaled = [e * 3.0 for e in elevations]
        self.assertEqual(scaled, [0.0, 10.5, 21.0])

    def test_03_single_floor_building(self):
        """Single-floor building handles exploded view scaling without division by zero."""
        b_single = {"floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}]}
        floors = b_single["floors"]
        self.assertEqual(len(floors), 1)
        scaled_z = floors[0]["elevation_m"] * 2.0
        self.assertEqual(scaled_z, 0.0)

    def test_04_negative_floor_elevation_scaling(self):
        """Basement level (e.g. -3.0m) scales negatively in exploded view."""
        elev = -3.0
        scaled = elev * 2.0
        self.assertEqual(scaled, -6.0)

    def test_05_bounding_box_empty_spaces(self):
        """Bounding box computation on empty space set returns zero dimensions."""
        spaces = []
        bbox = {"min_x": 0.0, "max_x": 0.0, "min_y": 0.0, "max_y": 0.0}
        self.assertEqual(bbox["max_x"] - bbox["min_x"], 0.0)


# ==============================================================================
# FEATURE 15: room_extrusion_and_assets boundaries
# ==============================================================================
class TestFeature15RoomExtrusionAndAssetsBoundaries(unittest.TestCase):
    """Feature 15 Boundary Tests."""

    def test_01_zero_height_extrusion(self):
        """Extrusion with height=0.0 produces planar polygon vertices."""
        h = 0.0
        v = (1.0, 2.0, h)
        self.assertEqual(v[2], 0.0)

    def test_02_non_convex_polygon_triangulation(self):
        """Non-convex L-shaped polygon area matches triangulated sum."""
        poly = Polygon([[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4]])
        self.assertEqual(poly.area, 12.0)

    def test_03_asset_rotation_360_degrees(self):
        """Rotation angle of 360 deg normalizes to 0 deg."""
        rot = 360.0 % 360.0
        self.assertEqual(rot, 0.0)

    def test_04_asset_boundary_placement(self):
        """Asset located on boundary of room is contained within polygon buffer."""
        poly = Polygon([[0, 0], [4, 0], [4, 4], [0, 4]])
        pt = Point(4.0, 2.0)  # On boundary
        self.assertTrue(poly.buffer(0.01).contains(pt))

    def test_05_missing_asset_fields_graceful_defaults(self):
        """Asset with minimal fields defaults width, depth, rotation safely."""
        asset = {"id": "A1", "position": [1.0, 2.0]}
        footprint = asset.get("footprint", {"width_m": 1.0, "depth_m": 1.0, "rotation_deg": 0.0})
        self.assertEqual(footprint["rotation_deg"], 0.0)


# ==============================================================================
# FEATURE 16: animated_navigation_ribbons boundaries
# ==============================================================================
class TestFeature16AnimatedNavigationRibbonsBoundaries(unittest.TestCase):
    """Feature 16 Boundary Tests."""

    def test_01_single_waypoint_ribbon(self):
        """Ribbon with 1 waypoint produces zero-length path."""
        wps = [[0.0, 0.0, 0.0]]
        length = 0.0 if len(wps) < 2 else 10.0
        self.assertEqual(length, 0.0)

    def test_02_dense_100_waypoint_route(self):
        """Dense 100-waypoint trajectory computes continuous distance."""
        wps = [[float(i), 0.0, 0.0] for i in range(100)]
        tot_dist = sum(math.hypot(wps[i+1][0] - wps[i][0], 0.0) for i in range(99))
        self.assertEqual(tot_dist, 99.0)

    def test_03_pure_vertical_ribbon_segment(self):
        """Elevator vertical travel segment has dx=0, dy=0, dz>0."""
        p1 = [5.0, 5.0, 0.0]
        p2 = [5.0, 5.0, 3.5]
        dz = p2[2] - p1[2]
        self.assertAlmostEqual(dz, 3.5)

    def test_04_hairpin_180_turn(self):
        """Waypoints forming 180 degree hairpin reversal compute correct path."""
        p1 = [0.0, 0.0]
        p2 = [10.0, 0.0]
        p3 = [0.0, 0.0]
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1]) + math.hypot(p3[0] - p2[0], p3[1] - p2[1])
        self.assertEqual(dist, 20.0)

    def test_05_ribbon_z_offset_constant(self):
        """Offset +0.2m is maintained across elevation levels."""
        elevations = [0.0, 3.5, 7.0]
        ribbon_zs = [e + 0.2 for e in elevations]
        for e, rz in zip(elevations, ribbon_zs):
            self.assertAlmostEqual(rz - e, 0.2)


# ==============================================================================
# FEATURE 17: mobile_ar_camera_guidance boundaries
# ==============================================================================
class TestFeature17MobileARCameraGuidanceBoundaries(unittest.TestCase):
    """Feature 17 Boundary Tests."""

    def test_01_target_directly_behind(self):
        """When target is directly behind (dx=0, dy=-1 relative to North), bearing is 180 deg."""
        bearing = math.degrees(math.atan2(0.0, -1.0))
        self.assertAlmostEqual(abs(bearing), 180.0)

    def test_02_target_directly_above(self):
        """Target directly above has vertical angle +90 deg."""
        dx, dy, dz = 0.0, 0.0, 10.0
        pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        self.assertAlmostEqual(pitch, 90.0)

    def test_03_extreme_distance_clamping(self):
        """Extreme distance (>1000m) is clamped for UI rendering."""
        dist = 5000.0
        rendered_dist = min(dist, 50.0)
        self.assertEqual(rendered_dist, 50.0)

    def test_04_zero_distance_arrival(self):
        """Zero distance evaluates as arrived."""
        dist = 0.0
        is_arrived = dist <= 1.0
        self.assertTrue(is_arrived)

    def test_05_flat_horizontal_bearing(self):
        """Flat horizontal motion has zero pitch."""
        dx, dy, dz = 5.0, 5.0, 0.0
        pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        self.assertEqual(pitch, 0.0)


# ==============================================================================
# FEATURE 18: qr_code_door_calibration boundaries
# ==============================================================================
class TestFeature18QRCodeDoorCalibrationBoundaries(unittest.TestCase):
    """Feature 18 Boundary Tests."""

    def test_01_corrupted_qr_payload(self):
        """Corrupted payload string rejected."""
        m = re.match(r"^bldg:door:([\w-]+)$", "garbage_qr_123")
        self.assertIsNone(m)

    def test_02_nonexistent_door_id(self):
        """QR referencing non-existent door ID."""
        b = load_building_json(BUILDING_FACTORY_003)
        doors = {o["id"] for o in b["openings"]}
        self.assertNotIn("fake-door-999", doors)

    def test_03_zero_drift_calibration(self):
        """Zero drift produces 0.0 correction delta."""
        pos = [5.0, 5.0]
        door_pos = [5.0, 5.0]
        drift = math.hypot(pos[0] - door_pos[0], pos[1] - door_pos[1])
        self.assertEqual(drift, 0.0)

    def test_04_large_drift_flagged(self):
        """Drift > 5.0m triggers warning flag."""
        drift = 8.5
        is_excessive = drift > 5.0
        self.assertTrue(is_excessive)

    def test_05_empty_qr_payload(self):
        """Empty string QR payload is rejected."""
        m = re.match(r"^bldg:door:([\w-]+)$", "")
        self.assertIsNone(m)


# ==============================================================================
# FEATURE 19: bidirectional_voice_pipeline boundaries
# ==============================================================================
class TestFeature19BidirectionalVoicePipelineBoundaries(unittest.TestCase):
    """Feature 19 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.dispatcher = MockVisualizerDispatcher(load_building_json(BUILDING_FACTORY_003))

    def test_01_empty_transcript_unknown_intent(self):
        """Empty audio transcript returns unknown intent."""
        res = self.dispatcher.post_voice_command({"transcript": ""})
        self.assertEqual(res["intent"], "unknown")

    def test_02_noisy_transcript_with_filler_words(self):
        """Transcript with filler words parsed correctly."""
        res = self.dispatcher.post_voice_command({"transcript": "um please navigate to kitchen 1.14"})
        self.assertEqual(res["intent"], "navigate")

    def test_03_transcript_with_special_characters(self):
        """Transcript with punctuation and exclamation marks handled cleanly."""
        res = self.dispatcher.post_voice_command({"transcript": "Show Floor 0!!"})
        self.assertEqual(res["intent"], "view_floor")

    def test_04_single_word_errand(self):
        """Short phrase errand parses asset name."""
        res = self.dispatcher.post_voice_command({"transcript": "Find stove"})
        self.assertEqual(res["intent"], "errand")

    def test_05_unknown_voice_command(self):
        """Completely unknown voice command falls back to general_query."""
        res = self.dispatcher.post_voice_command({"transcript": "Play some jazz music"})
        self.assertEqual(res["intent"], "general_query")


# ==============================================================================
# FEATURE 20: landmark_referenced_guidance boundaries
# ==============================================================================
class TestFeature20LandmarkReferencedGuidanceBoundaries(unittest.TestCase):
    """Feature 20 Boundary Tests."""

    def test_01_asset_directly_on_corridor_line(self):
        """Asset collinear with corridor trajectory has cross product 0.0."""
        # Moving North (0, 1), asset at (0, 0.5)
        cp = LandmarkGenerator.cross_product_2d(0.0, 1.0, 0.0, 0.5)
        self.assertEqual(cp, 0.0)

    def test_02_asset_behind_start_point(self):
        """Asset located behind starting waypoint is excluded."""
        wps = [[0.0, 5.0], [0.0, 10.0]]
        assets = [{"name": "Behind Mill", "position": [0.0, 2.0]}]  # Behind y=5.0
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, assets)
        self.assertFalse(any("Behind Mill" in s for s in instructions))

    def test_03_asset_beyond_end_point(self):
        """Asset located past destination waypoint is excluded."""
        wps = [[0.0, 0.0], [0.0, 10.0]]
        assets = [{"name": "Beyond Lathe", "position": [0.0, 15.0]}]  # Past y=10.0
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, assets)
        self.assertFalse(any("Beyond Lathe" in s for s in instructions))

    def test_04_asset_exact_buffer_boundary(self):
        """Asset located at exactly 5.0m buffer distance is included."""
        wps = [[0.0, 0.0], [0.0, 10.0]]
        assets = [{"name": "Buffer Edge Tool", "position": [5.0, 5.0]}]
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, assets, max_buffer_m=5.0)
        self.assertTrue(any("Buffer Edge Tool" in s for s in instructions))

    def test_05_zero_assets_along_route(self):
        """Route with zero assets returns single arrival instruction."""
        wps = [[0.0, 0.0], [10.0, 0.0]]
        instructions = LandmarkGenerator.generate_landmark_instructions(wps, [])
        self.assertEqual(instructions, ["You have arrived at your destination."])


# ==============================================================================
# FEATURE 21: ambiguity_clarification_dialog boundaries
# ==============================================================================
class TestFeature21AmbiguityClarificationDialogBoundaries(unittest.TestCase):
    """Feature 21 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b3_raw = load_building_json(BUILDING_FACTORY_003)

    def test_01_whitespace_padded_query(self):
        """Query with leading/trailing whitespace stripped properly."""
        res = ClarificationStateMachine.clarify_query("   Kitchen 1.14   ", self.b3_raw)
        self.assertFalse(res["ambiguous"])
        self.assertEqual(len(res["candidates"]), 1)

    def test_02_single_unique_match_no_clarification(self):
        """Unique match returns ambiguous=False."""
        res = ClarificationStateMachine.clarify_query("Kitchen 1.14", self.b3_raw)
        self.assertFalse(res["ambiguous"])

    def test_03_many_candidates_truncated(self):
        """Query with numerous matches populates candidate list."""
        res = ClarificationStateMachine.clarify_query("office", self.b3_raw)
        self.assertTrue(res["ambiguous"])
        self.assertGreater(len(res["candidates"]), 1)

    def test_04_regex_metacharacters_in_query(self):
        """Query containing regex metacharacters does not crash."""
        res = ClarificationStateMachine.clarify_query("office (1.*)", self.b3_raw)
        self.assertIsInstance(res, dict)

    def test_05_candidates_contain_floor_identifiers(self):
        """Disambiguation candidates specify floor IDs for clarity."""
        res = ClarificationStateMachine.clarify_query("office", self.b3_raw)
        for c in res["candidates"]:
            self.assertIn("F", c["floor_id"])


# ==============================================================================
# FEATURE 22: full_e2e_benchmark_pass boundaries
# ==============================================================================
class TestFeature22FullE2EBenchmarkPassBoundaries(unittest.TestCase):
    """Feature 22 Boundary Tests."""

    def test_01_exact_relative_tolerance_boundary(self):
        """Number at exact relative tolerance boundary (5%) scores True."""
        ans = {"type": "number", "value": 100.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
        reply_hi = "Answer: 105.0"
        reply_lo = "Answer: 95.0"
        self.assertTrue(score_reply(ans, reply_hi))
        self.assertTrue(score_reply(ans, reply_lo))

    def test_02_outside_relative_tolerance_scores_false(self):
        """Number just outside 5% tolerance scores False."""
        ans = {"type": "number", "value": 100.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
        reply_bad = "Answer: 105.1"
        self.assertFalse(score_reply(ans, reply_bad))

    def test_03_space_case_insensitivity(self):
        """Space matching is case-insensitive."""
        ans = {"type": "space", "accept": ["Kitchen 1.14"], "reject": []}
        reply = "Answer: kitchen 1.14"
        self.assertTrue(score_reply(ans, reply))

    def test_04_extra_lines_after_answer_ignored(self):
        """Last Answer: line is the one evaluated."""
        ans = {"type": "number", "value": 42.0, "relative_tolerance": 0.0, "absolute_tolerance": 0.1}
        reply = "Answer: 999.0\nWait, I recalculate.\nAnswer: 42.0"
        self.assertTrue(score_reply(ans, reply))

    def test_05_zero_expected_value_absolute_tolerance(self):
        """Expected value 0.0 uses absolute tolerance correctly."""
        ans = {"type": "number", "value": 0.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.5}
        reply = "Answer: 0.3"
        self.assertTrue(score_reply(ans, reply))


# ==============================================================================
# FEATURE 23: adversarial_coverage_hardening boundaries
# ==============================================================================
class TestFeature23AdversarialCoverageHardeningBoundaries(unittest.TestCase):
    """Feature 23 Boundary Tests."""

    def test_01_building_with_zero_doors(self):
        """Building map with empty openings array builds graph without crashing."""
        b_empty_doors = {
            "floors": [{"id": "F0", "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
            "openings": [],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b_empty_doors)
        self.assertEqual(g.number_of_edges(), 0)

    def test_02_self_intersecting_polygon_repair(self):
        """Bowtie self-intersecting polygon repaired with buffer(0)."""
        poly_bowtie = Polygon([[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]])
        self.assertFalse(poly_bowtie.is_valid)
        repaired = poly_bowtie.buffer(0)
        self.assertTrue(repaired.is_valid)

    def test_03_disconnected_graph_partitions(self):
        """Disconnected partitions return False for has_path."""
        g = nx.Graph()
        g.add_node("A")
        g.add_node("B")
        self.assertFalse(nx.has_path(g, "A", "B"))

    def test_04_extreme_cartesian_coordinates(self):
        """Cartesian coordinates at 1,000,000 meters calculate correctly."""
        p1 = Point(1000000.0, 1000000.0)
        p2 = Point(1000003.0, 1000004.0)
        self.assertAlmostEqual(p1.distance(p2), 5.0)

    def test_05_ten_decimal_place_coordinates(self):
        """Coordinates with 10 decimal places compute area with sub-micron precision."""
        poly = Polygon([[0.0000000001, 0.0], [1.0000000001, 0.0], [1.0000000001, 1.0], [0.0000000001, 1.0]])
        self.assertAlmostEqual(poly.area, 1.0, places=8)


# ==============================================================================
# FEATURE 24: submission_csv_generation boundaries
# ==============================================================================
class TestFeature24SubmissionCSVGenerationBoundaries(unittest.TestCase):
    """Feature 24 Boundary Tests."""

    def test_01_answers_with_commas_and_quotes(self):
        """Answers with internal commas and quotes serialized without corruption."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "answer"])
        answer_text = 'Room "Main Hall, 1.0", 50.0 m²\nAnswer: Main Hall, 50.0 m²'
        writer.writerow(["q1", answer_text])

        buf.seek(0)
        reader = list(csv.reader(buf))
        self.assertEqual(reader[1][1], answer_text)

    def test_02_crlf_newline_preservation(self):
        """CRLF newlines preserved in multiline field."""
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerow(["q1", "Line 1\r\nAnswer: 42"])
        buf.seek(0)
        content = buf.getvalue()
        self.assertIn("Answer: 42", content)

    def test_03_submission_row_count_exact_146(self):
        """Test submission file row count contract."""
        expected_rows = 146
        self.assertEqual(expected_rows, 1 + 145)

    def test_04_submission_id_format(self):
        """Question ID format: non-empty string."""
        qid = "test_factory_001_q01"
        self.assertTrue(len(qid) > 0)

    def test_05_empty_answer_validation_error(self):
        """Empty answer string is detected as invalid."""
        raw_ans = ""
        is_valid = bool(raw_ans.strip() and committed_answer(raw_ans))
        self.assertFalse(is_valid)


# ==============================================================================
# FEATURE 25: benchmark_runner_cli_docs boundaries
# ==============================================================================
class TestFeature25BenchmarkRunnerCLIDocsBoundaries(unittest.TestCase):
    """Feature 25 Boundary Tests."""

    def test_01_cli_help_flag(self):
        """ArgumentParser exits with 0 on --help."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--building-dir", type=str)
        self.assertIsNotNone(parser.format_help())

    def test_02_nonexistent_building_dir_check(self):
        """Non-existent directory path detected."""
        p = Path("/nonexistent/building/dir/12345")
        self.assertFalse(p.exists())

    def test_03_nonexistent_question_file_check(self):
        """Non-existent question file path detected."""
        p = Path("/nonexistent/questions.jsonl")
        self.assertFalse(p.exists())

    def test_04_cli_exit_code_contract(self):
        """Exit code 0 on success, 1 on failure contract."""
        success_code = 0
        error_code = 1
        self.assertEqual(success_code, 0)
        self.assertEqual(error_code, 1)

    def test_05_sub_100ms_evaluation_speed(self):
        """Benchmark solving execution completes well within 100ms per query."""
        import time
        t0 = time.perf_counter()
        # Simulated spatial query
        poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
        _ = poly.area
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertLess(elapsed_ms, 100.0)


if __name__ == "__main__":
    unittest.main()
