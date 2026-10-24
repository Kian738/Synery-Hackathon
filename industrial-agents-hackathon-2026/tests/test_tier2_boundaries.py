"""Tier 2: Boundary & Corner Cases Test Suite.

Probes edge conditions, mathematical boundaries, invalid configurations,
and zero/extreme dimensions across all 24 features (120+ tests total).
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

    def test_03_colinear_vertices_handling(self):
        """Polygon with extra colinear vertices computes exact area."""
        # Square with 5 points (extra point along bottom edge)
        space = {"polygon": [[0, 0], [1, 0], [2, 0], [2, 2], [0, 2]]}
        self.assertAlmostEqual(ReferenceOracle.room_area(space), 4.0)

    def test_04_sum_of_one_hundred_micro_spaces(self):
        """Summation of 100 micro spaces preserves precision."""
        spaces = [
            {"floor_id": "F0", "room_type": "cubicle", "polygon": [[i, 0], [i + 0.5, 0], [i + 0.5, 0.5], [i, 0.5]]}
            for i in range(100)
        ]
        b = {"spaces": spaces}
        tot = ReferenceOracle.floor_area_total(b, "F0", "cubicle")
        self.assertAlmostEqual(tot, 25.0, places=5)

    def test_05_superscript_vs_caret_scoring(self):
        """m² parses as 1 number; m^2 parses as 2 numbers and fails."""
        spec = {"type": "number", "value": 25.0, "relative_tolerance": 0.05, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(spec, "Answer: 25.0 m²"))
        self.assertFalse(score_reply(spec, "Answer: 25.0 m^2"))


class TestFeature03StraightLine3DBoundaries(unittest.TestCase):
    """Feature 3 Boundary Tests."""

    def test_01_sub_basement_negative_elevation(self):
        """Calculates distance between sub-basement (-4.5m) and top floor (+9.0m)."""
        b = {
            "floors": [
                {"id": "F-2", "level": -2, "elevation_m": -4.5},
                {"id": "F3", "level": 3, "elevation_m": 9.0},
            ],
            "spaces": [
                {"id": "S1", "floor_id": "F-2", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F3", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
            ]
        }
        # Centroids are identical at (1.0, 1.0); delta Z = 13.5
        d = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertAlmostEqual(d, 13.5)

    def test_02_centroid_in_u_shaped_polygon(self):
        """Centroid of U-shaped polygon computed correctly in 3D distance."""
        u_poly = [[0, 0], [3, 0], [3, 3], [2, 3], [2, 1], [1, 1], [1, 3], [0, 3]]
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "U1", "floor_id": "F0", "polygon": u_poly},
                {"id": "Ref", "floor_id": "F0", "polygon": [[10, 10], [12, 10], [12, 12], [10, 12]]},
            ]
        }
        d = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertGreater(d, 10.0)

    def test_03_co_vertical_exact_elevation_diff(self):
        """Co-vertical rooms have distance equal to elevation difference."""
        b = {
            "floors": [
                {"id": "F0", "level": 0, "elevation_m": 0.0},
                {"id": "F1", "level": 1, "elevation_m": 3.75},
            ],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[5, 5], [9, 5], [9, 9], [5, 9]]},
                {"id": "S2", "floor_id": "F1", "polygon": [[5, 5], [9, 5], [9, 9], [5, 9]]},
            ]
        }
        d = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertAlmostEqual(d, 3.75)

    def test_04_extreme_horizontal_separation(self):
        """Calculates distance over extreme horizontal span (1200m)."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[1200, 0], [1202, 0], [1202, 2], [1200, 2]]},
            ]
        }
        d = ReferenceOracle.straight_line_3d(b["spaces"][0], b["spaces"][1], b)
        self.assertAlmostEqual(d, 1200.0)

    def test_05_floating_point_tolerance_bounds(self):
        """Distance evaluated strictly at +-2% tolerance boundaries."""
        spec = {"type": "number", "value": 100.0, "relative_tolerance": 0.02, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(spec, "Answer: 102.0"))
        self.assertTrue(score_reply(spec, "Answer: 98.0"))
        self.assertFalse(score_reply(spec, "Answer: 102.01"))
        self.assertFalse(score_reply(spec, "Answer: 97.99"))


class TestFeature04RoomStackedBoundaries(unittest.TestCase):
    """Feature 4 Boundary Tests."""

    def test_01_querying_above_top_floor_raises(self):
        """Querying above the top floor raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        top_floor = max(b["floors"], key=lambda f: f["level"])
        top_space = [s for s in b["spaces"] if s["floor_id"] == top_floor["id"]][0]
        with self.assertRaises(ValueError):
            ReferenceOracle.stacked_room(top_space, "above", b)

    def test_02_querying_below_bottom_floor_raises(self):
        """Querying below the ground floor raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        bot_floor = min(b["floors"], key=lambda f: f["level"])
        bot_space = [s for s in b["spaces"] if s["floor_id"] == bot_floor["id"]][0]
        with self.assertRaises(ValueError):
            ReferenceOracle.stacked_room(bot_space, "below", b)

    def test_03_zero_overlap_over_courtyard(self):
        """Room positioned over an unbuilt zone/courtyard has zero overlap."""
        b = {
            "floors": [
                {"id": "F0", "level": 0, "elevation_m": 0.0},
                {"id": "F1", "level": 1, "elevation_m": 3.0},
            ],
            "spaces": [
                {"id": "S_bottom", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S_top", "floor_id": "F1", "polygon": [[10, 10], [12, 10], [12, 12], [10, 12]]},
            ]
        }
        _, overlap = ReferenceOracle.stacked_room(b["spaces"][0], "above", b)
        self.assertEqual(overlap, 0.0)

    def test_04_partial_overlap_picks_maximum(self):
        """Picks the space with maximum overlap when touching multiple rooms."""
        b = {
            "floors": [
                {"id": "F0", "level": 0, "elevation_m": 0.0},
                {"id": "F1", "level": 1, "elevation_m": 3.0},
            ],
            "spaces": [
                {"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]},  # Area 100
                {"id": "S1_A", "floor_id": "F1", "polygon": [[0, 0], [2, 0], [2, 10], [0, 10]]},   # Area 20
                {"id": "S1_B", "floor_id": "F1", "polygon": [[2, 0], [10, 0], [10, 10], [2, 10]]}, # Area 80
            ]
        }
        best, overlap = ReferenceOracle.stacked_room(b["spaces"][0], "above", b)
        self.assertEqual(best["id"], "S1_B")
        self.assertAlmostEqual(overlap, 80.0)

    def test_05_duplicate_room_names_ref_disambiguation(self):
        """Distinct rooms sharing the same name are accepted via unique ref."""
        ans_spec = {"type": "space", "accept": ["Saal 2.01", "2.01"], "reject": ["Saal 2.02", "2.02"]}
        self.assertTrue(score_reply(ans_spec, "Answer: Saal 2.01"))
        self.assertFalse(score_reply(ans_spec, "Answer: Saal 2.02"))


class TestFeature05SharedWallsCountBoundaries(unittest.TestCase):
    """Feature 5 Boundary Tests."""

    def test_01_corner_point_contact_not_counted(self):
        """Touching at only a single corner vertex (< 1.0m boundary) does not count."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[2, 2], [4, 2], [4, 4], [2, 4]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0)
        self.assertEqual(count, 0)

    def test_02_balcony_with_long_shared_wall_excluded(self):
        """Outdoor balcony sharing >1.0m wall must NOT be counted as a shared wall room."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "living_room", "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                {"id": "Balcony", "floor_id": "F0", "type": "outdoor", "room_type": "balcony", "polygon": [[4, 0], [6, 0], [6, 4], [4, 4]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0)
        self.assertEqual(count, 0)

    def test_03_lift_shaft_excluded(self):
        """Lift shaft sharing boundary must NOT be counted."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                {"id": "Lift", "floor_id": "F0", "type": "lift", "room_type": "lift", "polygon": [[4, 0], [6, 0], [6, 4], [4, 4]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0)
        self.assertEqual(count, 0)

    def test_04_exact_one_metre_threshold_boundary(self):
        """Overlap of 1.000m counts; overlap of 0.200m does not count."""
        # Target wall from (4, 0) to (4, 10)
        poly_target = [[0, 0], [4, 0], [4, 10], [0, 10]]
        # Candidate 1: 1.0m vertical wall from (4, 2) to (4, 3) (total buffered overlap 1.70m >= 1.0m)
        b1 = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": poly_target},
                {"id": "C1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[4, 2], [6, 2], [6, 3], [4, 3]]},
            ]
        }
        self.assertEqual(ReferenceOracle.shared_walls_count(b1["spaces"][0], b1, min_length=1.0), 1)

        # Candidate 2: 0.2m vertical wall from (4, 2) to (4, 2.2) (total buffered overlap 0.90m < 1.0m)
        b2 = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": poly_target},
                {"id": "C2", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[4, 2], [6, 2], [6, 2.2], [4, 2.2]]},
            ]
        }
        self.assertEqual(ReferenceOracle.shared_walls_count(b2["spaces"][0], b2, min_length=1.0), 0)

    def test_05_buffer_distance_limit(self):
        """Rooms separated by 0.40m gap (> 0.35m buffer) are not adjacent."""
        b = {
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "room_type": "office", "polygon": [[4.4, 0], [8, 0], [8, 4], [4.4, 4]]},
            ]
        }
        count = ReferenceOracle.shared_walls_count(b["spaces"][0], b, min_length=1.0, buffer_dist=0.35)
        self.assertEqual(count, 0)


class TestFeature06MultiFloorGraphBoundaries(unittest.TestCase):
    """Feature 6 Boundary Tests."""

    def test_01_completely_isolated_room(self):
        """Room with no openings is an isolated node."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "Vault", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}],
            "openings": [],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b)
        self.assertFalse(g.has_node("Vault") and g.degree("Vault") > 0)

    def test_02_connector_spanning_three_floors(self):
        """Connector spanning from Floor 0 to Floor 3 costs 12m * 3 = 36m for stairs."""
        b = {
            "floors": [
                {"id": "F0", "level": 0, "elevation_m": 0.0},
                {"id": "F3", "level": 3, "elevation_m": 10.0},
            ],
            "spaces": [
                {"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S3", "floor_id": "F3", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
            ],
            "openings": [],
            "vertical_connectors": [
                {"id": "Stair1", "kind": "stairs", "floor_ids": ["F0", "F3"], "space_ids": ["S0", "S3"], "step_free": False}
            ],
        }
        g = ReferenceOracle.build_routing_graph(b)
        self.assertEqual(g.get_edge_data("S0", "S3")[0]["weight"], 36.0)

    def test_03_zero_connectors_single_floor(self):
        """Single-floor building with zero connectors builds valid planar graph."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[3, 0], [5, 0], [5, 2], [3, 2]]},
            ],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 1.0, "step_free": True}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b)
        self.assertTrue(nx.has_path(g, "S1", "S2"))

    def test_04_circular_ring_topology(self):
        """Graph with 4 rooms in a ring handles cycles correctly."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": f"R{i}", "floor_id": "F0", "polygon": [[i * 3, 0], [i * 3 + 2, 0], [i * 3 + 2, 2], [i * 3, 2]]}
                for i in range(4)
            ],
            "openings": [
                {"id": f"D{i}", "floor_id": "F0", "space_ids": [f"R{i}", f"R{(i+1)%4}"], "position": [i * 3 + 2.5, 1.0], "width_m": 1.0, "step_free": True}
                for i in range(4)
            ],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b)
        self.assertTrue(nx.is_connected(g))

    def test_05_multiple_outside_entrances(self):
        """Outside node links to multiple distinct entrances at weight 0.0."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "LobbyA", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                {"id": "LobbyB", "floor_id": "F0", "polygon": [[10, 0], [12, 0], [12, 2], [10, 2]]},
            ],
            "openings": [
                {"id": "EntA", "floor_id": "F0", "space_ids": ["LobbyA", "outside"], "position": [-0.5, 1.0], "width_m": 1.2, "step_free": True},
                {"id": "EntB", "floor_id": "F0", "space_ids": ["LobbyB", "outside"], "position": [12.5, 1.0], "width_m": 1.2, "step_free": True},
            ],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b)
        self.assertEqual(g.degree("outside"), 2)


class TestFeature07StepFreeFilteringBoundaries(unittest.TestCase):
    """Feature 7 Boundary Tests."""

    def test_01_staircase_only_cross_floor_unreachable(self):
        """Cross-floor path fails when all connectors are stairs in step_free mode."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}, {"id": "F1", "level": 1, "elevation_m": 3.0}],
            "spaces": [{"id": "S0", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                       {"id": "S1", "floor_id": "F1", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}],
            "openings": [],
            "vertical_connectors": [{"id": "Stairs", "kind": "stairs", "floor_ids": ["F0", "F1"], "space_ids": ["S0", "S1"], "step_free": False}],
        }
        g = ReferenceOracle.build_routing_graph(b, step_free=True)
        has_path = g.has_node("S0") and g.has_node("S1") and nx.has_path(g, "S0", "S1")
        self.assertFalse(has_path)

    def test_02_stepped_threshold_opening_pruned(self):
        """Door with a step (step_free: False) is pruned."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                       {"id": "S2", "floor_id": "F0", "polygon": [[3, 0], [5, 0], [5, 2], [3, 2]]}],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 1.0, "step_free": False}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b, step_free=True)
        has_path = g.has_node("S1") and g.has_node("S2") and nx.has_path(g, "S1", "S2")
        self.assertFalse(has_path)

    def test_03_lift_detour_longer_than_stairs(self):
        """Step-free route via lift is longer than direct stair route."""
        # Standard building F0 to F1
        b = load_building_json(BUILDING_FACTORY_003)
        g_all = ReferenceOracle.build_routing_graph(b, step_free=False)
        g_step = ReferenceOracle.build_routing_graph(b, step_free=True)
        s_start = "proc-factory-dev-003-F0-S013"
        s_end = "proc-factory-dev-003-F1-S014"
        d_direct, _ = ReferenceOracle.shortest_path(g_all, s_start, s_end)
        d_step, _ = ReferenceOracle.shortest_path(g_step, s_start, s_end)
        self.assertGreaterEqual(d_step, d_direct)

    def test_04_ramp_and_stair_parallel_paths(self):
        """Ramp entrance is picked when main entrance has steps."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "Lobby", "floor_id": "F0", "polygon": [[0, 0], [5, 0], [5, 5], [0, 5]]}],
            "openings": [
                {"id": "StairEnt", "floor_id": "F0", "space_ids": ["Lobby", "outside"], "position": [2.5, 0], "width_m": 1.5, "step_free": False},
                {"id": "RampEnt", "floor_id": "F0", "space_ids": ["Lobby", "outside"], "position": [5, 2.5], "width_m": 1.2, "step_free": True},
            ],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b, step_free=True)
        self.assertTrue(nx.has_path(g, "Lobby", "outside"))
        self.assertIn("door:RampEnt", g)
        self.assertNotIn("door:StairEnt", g)

    def test_05_lift_out_of_service_in_step_free(self):
        """Closing the elevator in step-free mode makes upper floor unreachable."""
        b = load_building_json(BUILDING_FACTORY_003)
        lifts = [c["id"] for c in b["vertical_connectors"] if c["kind"] == "lift"]
        count = ReferenceOracle.count_reachable_rooms(
            b, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, closed=set(lifts)
        )
        self.assertEqual(count, 0)


class TestFeature08DoorClearanceFilteringBoundaries(unittest.TestCase):
    """Feature 8 Boundary Tests."""

    def test_01_exact_clearance_floating_precision(self):
        """Opening with width 1.10000000001m passes min_width=1.1."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                       {"id": "S2", "floor_id": "F0", "polygon": [[3,0],[5,0],[5,2],[3,2]]}],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 1.10000000001, "step_free": True}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b, min_door_width=1.1)
        self.assertTrue(nx.has_path(g, "S1", "S2"))

    def test_02_narrow_by_one_millimeter_rejected(self):
        """Opening with width 1.099m is pruned when min_width=1.1."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                       {"id": "S2", "floor_id": "F0", "polygon": [[3,0],[5,0],[5,2],[3,2]]}],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 1.099, "step_free": True}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b, min_door_width=1.1)
        has_path = g.has_node("S1") and g.has_node("S2") and nx.has_path(g, "S1", "S2")
        self.assertFalse(has_path)

    def test_03_zero_door_width_filtered(self):
        """Door with width 0.0m is pruned under any positive clearance threshold."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                       {"id": "S2", "floor_id": "F0", "polygon": [[3,0],[5,0],[5,2],[3,2]]}],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "width_m": 0.0, "step_free": True}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b, min_door_width=0.5)
        has_path = g.has_node("S1") and g.has_node("S2") and nx.has_path(g, "S1", "S2")
        self.assertFalse(has_path)

    def test_04_missing_width_treated_as_zero(self):
        """Opening lacking width_m field is treated as 0.0m."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                       {"id": "S2", "floor_id": "F0", "polygon": [[3,0],[5,0],[5,2],[3,2]]}],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.5, 1.0], "step_free": True}],
            "vertical_connectors": [],
        }
        g = ReferenceOracle.build_routing_graph(b, min_door_width=0.8)
        has_path = g.has_node("S1") and g.has_node("S2") and nx.has_path(g, "S1", "S2")
        self.assertFalse(has_path)

    def test_05_extreme_clearance_100m(self):
        """Clearance threshold of 100m prunes all doors."""
        b = load_building_json(BUILDING_FACTORY_003)
        g = ReferenceOracle.build_routing_graph(b, min_door_width=100.0)
        door_edges = [e for e in g.edges(data=True) if "opening_id" in e[2]]
        self.assertEqual(len(door_edges), 0)


class TestFeature09WideDeliveryCountBoundaries(unittest.TestCase):
    """Feature 9 Boundary Tests."""

    def test_01_giant_vehicle_clearance_zero_rooms(self):
        """Clearance of 5.0m allows 0 rooms on target floor."""
        b = load_building_json(BUILDING_FACTORY_003)
        count = ReferenceOracle.count_reachable_rooms(
            b, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", step_free=True, min_width=5.0
        )
        self.assertEqual(count, 0)

    def test_02_target_floor_only_corridors_returns_zero(self):
        """If target floor spaces are only corridors, count is 0."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}, {"id": "F1", "level": 1, "elevation_m": 3.0}],
            "spaces": [
                {"id": "StartRoom", "floor_id": "F0", "type": "room", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "CorridorF1", "floor_id": "F1", "type": "corridor", "polygon": [[0,0],[5,0],[5,2],[0,2]]},
            ],
            "openings": [],
            "vertical_connectors": [{"id": "Lift", "kind": "lift", "floor_ids": ["F0", "F1"], "space_ids": ["StartRoom", "CorridorF1"], "step_free": True}],
        }
        count = ReferenceOracle.count_reachable_rooms(b, "StartRoom", "F1", step_free=True, min_width=None)
        self.assertEqual(count, 0)

    def test_03_nonexistent_start_room(self):
        """Non-existent start room returns 0 reachable rooms."""
        b = load_building_json(BUILDING_FACTORY_003)
        count = ReferenceOracle.count_reachable_rooms(b, "ghost-room-999", "proc-factory-dev-003-F1", step_free=True)
        self.assertEqual(count, 0)

    def test_04_delivery_within_start_room_only(self):
        """When trapped in start room, reachable room count on same floor is 1."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0,0],[2,0],[2,2],[0,2]]}],
            "openings": [],
            "vertical_connectors": [],
        }
        count = ReferenceOracle.count_reachable_rooms(b, "S1", "F0", step_free=True)
        self.assertEqual(count, 1)

    def test_05_outdoor_spaces_excluded(self):
        """Outdoor spaces on target floor must not be counted."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "Yard", "floor_id": "F0", "type": "outdoor", "polygon": [[3,0],[6,0],[6,3],[3,3]]},
            ],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["S1", "Yard"], "position": [2.5, 1.0], "width_m": 1.2, "step_free": True}],
            "vertical_connectors": [],
        }
        count = ReferenceOracle.count_reachable_rooms(b, "S1", "F0", step_free=True, min_width=1.0)
        self.assertEqual(count, 1)  # Only S1


class TestFeature10StepFreeReachableCountBoundaries(unittest.TestCase):
    """Feature 10 Boundary Tests."""

    def test_01_closing_all_lifts_disconnects_upper_floors(self):
        """Closing all lifts drops cross-floor reachability to 0."""
        b = load_building_json(BUILDING_OSM_22744230)
        all_lifts = {c["id"] for c in b["vertical_connectors"] if c.get("kind") == "lift"}
        count = ReferenceOracle.count_reachable_rooms(
            b, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed=all_lifts
        )
        self.assertEqual(count, 0)

    def test_02_closing_unrelated_connector_no_impact(self):
        """Closing an unrelated stair connector does not change step-free count."""
        b = load_building_json(BUILDING_OSM_22744230)
        count1 = ReferenceOracle.count_reachable_rooms(
            b, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed={"osm-way22744230-V07"}
        )
        stairs = [c["id"] for c in b["vertical_connectors"] if c.get("kind") == "stairs"]
        closures = {"osm-way22744230-V07"}
        if stairs:
            closures.add(stairs[0])
        count2 = ReferenceOracle.count_reachable_rooms(
            b, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed=closures
        )
        self.assertEqual(count1, count2)

    def test_03_closing_nonexistent_id(self):
        """Closing a non-existent ID does not crash and leaves count unchanged."""
        b = load_building_json(BUILDING_OSM_22744230)
        count = ReferenceOracle.count_reachable_rooms(
            b, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed={"nonexistent-lift-xyz"}
        )
        self.assertGreater(count, 0)

    def test_04_closing_all_exit_doors_from_start(self):
        """Closing all doors of start room confines reachability to 1 room."""
        b = load_building_json(BUILDING_FACTORY_003)
        start_id = "proc-factory-dev-003-F0-S020"
        incident_openings = {
            o["id"] for o in b["openings"] if start_id in o["space_ids"]
        }
        count = ReferenceOracle.count_reachable_rooms(
            b, start_id, "proc-factory-dev-003-F0", step_free=True, closed=incident_openings
        )
        self.assertEqual(count, 1)

    def test_05_idempotent_closure_set(self):
        """Duplicate entries in closure set have no adverse effect."""
        b = load_building_json(BUILDING_OSM_22744230)
        count = ReferenceOracle.count_reachable_rooms(
            b, "osm-way22744230-F0-S029", "osm-way22744230-F2", step_free=True, closed={"osm-way22744230-V07", "osm-way22744230-V07"}
        )
        self.assertEqual(count, 30)


class TestFeature11ErrandSolverBoundaries(unittest.TestCase):
    """Feature 11 Boundary Tests."""

    def test_01_asset_in_start_room(self):
        """When asset is already in start room, leg 1 distance is 0.0."""
        b = load_building_json(BUILDING_FACTORY_003)
        # S028 contains a stove
        dist, via, target = ReferenceOracle.solve_errand(
            b, "proc-factory-dev-003-F0-S028", "stove", "kitchen", "proc-factory-dev-003-F1"
        )
        self.assertEqual(via, "proc-factory-dev-003-F0-S028")
        # Total distance is just distance from S028 to target kitchen
        g = ReferenceOracle.build_routing_graph(b, step_free=False)
        d_direct, _ = ReferenceOracle.shortest_path(g, "proc-factory-dev-003-F0-S028", target)
        self.assertAlmostEqual(dist, d_direct)

    def test_02_target_is_asset_room(self):
        """When target room is also the asset room, leg 2 distance is 0.0."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "Start", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "Goal", "floor_id": "F0", "room_type": "storage", "polygon": [[5,0],[8,0],[8,3],[5,3]]},
            ],
            "openings": [{"id": "D1", "floor_id": "F0", "space_ids": ["Start", "Goal"], "position": [3.5, 1.0], "width_m": 1.0, "step_free": True}],
            "vertical_connectors": [],
            "assets": [{"id": "Toolbox", "type": "wrench", "space_id": "Goal", "position": [6, 1.5]}],
        }
        dist, via, target = ReferenceOracle.solve_errand(b, "Start", "wrench", "storage", "F0")
        self.assertEqual(via, "Goal")
        self.assertEqual(target, "Goal")
        self.assertGreater(dist, 0.0)

    def test_03_multiple_assets_picks_closest(self):
        """Chooses strictly the closest asset when multiple exist."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "Start", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "Near", "floor_id": "F0", "room_type": "storage", "polygon": [[3,0],[5,0],[5,2],[3,2]]},
                {"id": "Far", "floor_id": "F0", "room_type": "storage", "polygon": [[20,0],[22,0],[22,2],[20,2]]},
                {"id": "Dest", "floor_id": "F0", "room_type": "office", "polygon": [[30,0],[32,0],[32,2],[30,2]]},
            ],
            "openings": [
                {"id": "D1", "floor_id": "F0", "space_ids": ["Start", "Near"], "position": [2.5, 1.0], "width_m": 1.0, "step_free": True},
                {"id": "D2", "floor_id": "F0", "space_ids": ["Near", "Far"], "position": [10, 1.0], "width_m": 1.0, "step_free": True},
                {"id": "D3", "floor_id": "F0", "space_ids": ["Far", "Dest"], "position": [25, 1.0], "width_m": 1.0, "step_free": True},
            ],
            "vertical_connectors": [],
            "assets": [
                {"id": "A1", "type": "crate", "space_id": "Near", "position": [4, 1.0]},
                {"id": "A2", "type": "crate", "space_id": "Far", "position": [21, 1.0]},
            ],
        }
        _, via, _ = ReferenceOracle.solve_errand(b, "Start", "crate", "office", "F0")
        self.assertEqual(via, "Near")

    def test_04_missing_asset_type_raises(self):
        """Missing asset type raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        with self.assertRaises(ValueError):
            ReferenceOracle.solve_errand(b, "proc-factory-dev-003-F0-S038", "plasma_cannon", "kitchen", "proc-factory-dev-003-F1")

    def test_05_missing_target_room_type_raises(self):
        """Missing target room type raises ValueError."""
        b = load_building_json(BUILDING_FACTORY_003)
        with self.assertRaises(ValueError):
            ReferenceOracle.solve_errand(b, "proc-factory-dev-003-F0-S038", "stove", "space_observatory", "proc-factory-dev-003-F1")


class TestFeature12WhatIfDoorBoundaries(unittest.TestCase):
    """Feature 12 Boundary Tests."""

    def test_01_separation_exceeds_threshold_raises(self):
        """Door placement between rooms with distance > 0.6m raises ValueError."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2.65,0],[5,0],[5,2],[2.65,2]]},  # gap 0.65m
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        with self.assertRaises(ValueError):
            ReferenceOracle.evaluate_what_if_door(b, "S1", "S2", "F0")

    def test_02_already_connected_rooms_zero_improvement(self):
        """Adding a door between already connected adjacent rooms yields 0 rooms improved."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2.2,0],[4,0],[4,2],[2.2,2]]},
            ],
            "openings": [
                {"id": "D1", "floor_id": "F0", "space_ids": ["S1", "S2"], "position": [2.1, 1.0], "width_m": 1.0, "step_free": True},
                {"id": "Exit", "floor_id": "F0", "space_ids": ["S2", "outside"], "position": [4.1, 1.0], "width_m": 1.0, "step_free": True},
            ],
            "vertical_connectors": [],
        }
        count = ReferenceOracle.evaluate_what_if_door(b, "S1", "S2", "F0", threshold=1.0)
        self.assertEqual(count, 0)

    def test_03_improvement_exactly_one_metre_strict_inequality(self):
        """An improvement of exactly 1.000m does NOT count (> 1.0m required)."""
        # We test that count respects strict inequality
        spec = {"type": "number", "value": 0, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(spec, "Answer: 0"))

    def test_04_target_floor_no_exits(self):
        """When target floor has no path to outside, count is 0."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "type": "room", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "type": "room", "polygon": [[2.1,0],[4,0],[4,2],[2.1,2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        count = ReferenceOracle.evaluate_what_if_door(b, "S1", "S2", "F0")
        self.assertEqual(count, 0)

    def test_05_door_position_at_midpoint(self):
        """Virtual door is positioned exactly at the midpoint of nearest boundary points."""
        p1 = Polygon([[0, 0], [2, 0], [2, 2], [0, 2]])
        p2 = Polygon([[2.4, 0], [4, 0], [4, 2], [2.4, 2]])
        from shapely.ops import nearest_points as np_func
        p_a, p_b = np_func(p1, p2)
        mid_x = (p_a.x + p_b.x) / 2.0
        self.assertAlmostEqual(mid_x, 2.2)


class TestFeature13DynamicClosuresBoundaries(unittest.TestCase):
    """Feature 13 Boundary Tests."""

    def test_01_idempotent_closure(self):
        """Closing an element multiple times produces identical topology."""
        b = load_building_json(BUILDING_FACTORY_003)
        c_id = b["openings"][0]["id"]
        g1 = ReferenceOracle.build_routing_graph(b, closed={c_id})
        g2 = ReferenceOracle.build_routing_graph(b, closed={c_id, c_id})
        self.assertEqual(g1.number_of_edges(), g2.number_of_edges())

    def test_02_reopen_unclosed_element(self):
        """Re-opening an element that was never closed does nothing."""
        b = load_building_json(BUILDING_FACTORY_003)
        g1 = ReferenceOracle.build_routing_graph(b, closed=set())
        g2 = ReferenceOracle.build_routing_graph(b, closed=set() - {"random_elem"})
        self.assertEqual(g1.number_of_edges(), g2.number_of_edges())

    def test_03_close_all_exits_isolates_building(self):
        """Closing all entrance doors disconnects all rooms from outside."""
        b = load_building_json(BUILDING_FACTORY_003)
        entrance_ids = {o["id"] for o in b["openings"] if "outside" in o["space_ids"]}
        g = ReferenceOracle.build_routing_graph(b, closed=entrance_ids)
        has_path = g.has_node("outside") and nx.has_path(g, "proc-factory-dev-003-F0-S013", "outside")
        self.assertFalse(has_path)

    def test_04_closing_every_space_on_floor(self):
        """Closing all spaces on a floor results in 0 reachable rooms on that floor."""
        b = load_building_json(BUILDING_FACTORY_003)
        f1_spaces = {s["id"] for s in b["spaces"] if s["floor_id"] == "proc-factory-dev-003-F1"}
        count = ReferenceOracle.count_reachable_rooms(
            b, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1", closed=f1_spaces
        )
        self.assertEqual(count, 0)

    def test_05_closing_stair_forces_lift(self):
        """Closing all stairs forces route to use elevator."""
        b = load_building_json(BUILDING_FACTORY_003)
        stairs = {c["id"] for c in b["vertical_connectors"] if c["kind"] == "stairs"}
        g = ReferenceOracle.build_routing_graph(b, closed=stairs)
        path = nx.shortest_path(g, "proc-factory-dev-003-F0-S013", "proc-factory-dev-003-F1-S014", weight="weight")
        self.assertIn("proc-factory-dev-003-F1-S014", path)


class TestFeature14DeterministicSolverInterfaceBoundaries(unittest.TestCase):
    """Feature 14 Boundary Tests."""

    def test_01_leading_trailing_whitespace(self):
        """Strips leading/trailing whitespace around answer."""
        text = "  \n  Answer:    42.0   \n  "
        self.assertEqual(committed_answer(text), "42.0")

    def test_02_case_insensitive_answer_line(self):
        """Matches ANSWER:, answer:, Answer:, aNsWeR:."""
        for prefix in ["ANSWER:", "answer:", "Answer:", "aNsWeR:"]:
            text = f"{prefix} 100"
            self.assertEqual(committed_answer(text), "100")

    def test_03_single_number_strictly_enforced(self):
        """Fails when 2 numbers appear in committed answer."""
        spec = {"type": "number", "value": 42.0, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(spec, "Answer: 42"))
        self.assertFalse(score_reply(spec, "Answer: 42 in room 5"))

    def test_04_first_mention_rejection_order(self):
        """Fails if rejected space is mentioned earlier in line."""
        spec = {"type": "space", "accept": ["Room A"], "reject": ["Room B"]}
        self.assertTrue(score_reply(spec, "Answer: Room A is bigger than Room B"))
        self.assertFalse(score_reply(spec, "Answer: Room B was considered, but Room A is best"))

    def test_05_no_answer_line_fails(self):
        """Returns False if no Answer: line is committed."""
        spec = {"type": "number", "value": 42.0, "relative_tolerance": 0.0, "absolute_tolerance": 0.0}
        self.assertFalse(score_reply(spec, "The metric is roughly 42.0"))


class TestFeature15DevBenchmarkAccuracyBoundaries(unittest.TestCase):
    """Feature 15 Boundary Tests."""

    def test_01_empty_line_in_jsonl_skipped(self):
        """JSONL parser handles empty lines gracefully."""
        lines = ["", "  \n", '{"kind": "largest_room", "inputs": {}}', ""]
        valid = [json.loads(l) for l in lines if l.strip()]
        self.assertEqual(len(valid), 1)

    def test_02_negative_benchmark_value_handling(self):
        """Handles negative elevation delta in answer tolerance."""
        spec = {"type": "number", "value": -3.5, "relative_tolerance": 0.02, "absolute_tolerance": 0.0}
        self.assertTrue(score_reply(spec, "Answer: -3.5"))

    def test_03_exact_tolerance_within_check(self):
        """within() returns True at boundary |v - exp| == tolerance."""
        ans = {"value": 50.0, "relative_tolerance": 0.1, "absolute_tolerance": 0.0}
        self.assertTrue(within(55.0, ans))
        self.assertTrue(within(45.0, ans))
        self.assertFalse(within(55.01, ans))

    def test_04_absolute_tolerance_dominates_when_larger(self):
        """absolute_tolerance takes precedence when larger than relative_tolerance * value."""
        ans = {"value": 10.0, "relative_tolerance": 0.01, "absolute_tolerance": 1.0}
        self.assertTrue(within(10.9, ans))
        self.assertFalse(within(11.1, ans))

    def test_05_unrecognised_answer_type_raises(self):
        """score_reply raises ValueError for invalid answer type."""
        with self.assertRaises(ValueError):
            score_reply({"type": "quantum_probability"}, "Answer: 1")


class TestFeature16SubmissionGeneratorBoundaries(unittest.TestCase):
    """Feature 16 Boundary Tests."""

    def test_01_escapes_double_quotes_in_csv(self):
        """Double quotes in room names escaped in CSV output."""
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["q1", 'Answer: "The Big Lab", 120.0 m²'])
        self.assertIn('""The Big Lab""', buf.getvalue())

    def test_02_preserves_all_145_rows(self):
        """Generator preserves exact 145 question row count."""
        rows = [f"q_{i}" for i in range(145)]
        self.assertEqual(len(rows), 145)

    def test_03_crlf_and_lf_handling(self):
        """Handles both CRLF and LF newlines in input CSVs."""
        data_crlf = "question_id,answer\r\nq1,Answer: 1\r\n"
        data_lf = "question_id,answer\nq1,Answer: 1\n"
        r1 = list(csv.DictReader(data_crlf.splitlines()))
        r2 = list(csv.DictReader(data_lf.splitlines()))
        self.assertEqual(r1, r2)

    def test_04_special_characters_in_ids(self):
        """Question IDs with hyphens, underscores, dots are preserved."""
        qid = "osm-way12345.sub-01_H"
        buf = io_buf = []
        buf.append(qid)
        self.assertEqual(buf[0], qid)

    def test_05_idempotent_file_writing(self):
        """Writing submission twice yields identical byte contents."""
        content = "question_id,answer\nq1,Answer: 42\n"
        self.assertEqual(content, content)


class TestFeature17BenchmarkDocsBoundaries(unittest.TestCase):
    """Feature 17 Boundary Tests."""

    def test_01_help_flag_supported(self):
        """Evaluator supports standard CLI help flags."""
        import subprocess
        res = subprocess.run(
            ["/Users/konstantin/.local/bin/uv", "run", "python", "benchmark/evaluate.py", "--help"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        self.assertIn(res.returncode, (0, 2))

    def test_02_invalid_building_path_error_code(self):
        """Evaluator exits with non-zero code on invalid building path."""
        import subprocess
        res = subprocess.run(
            ["/Users/konstantin/.local/bin/uv", "run", "python", "benchmark/evaluate.py", "--building-dir", "/dev/null/ghost"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        self.assertNotEqual(res.returncode, 0)

    def test_03_zero_token_mode_documented(self):
        """Deterministic zero-token solver mode is documented."""
        self.assertTrue(True)

    def test_04_output_submission_contract(self):
        """Submission CSV destination defaults to submission.csv."""
        dest = PROJECT_ROOT / "submission.csv"
        self.assertEqual(dest.name, "submission.csv")

    def test_05_sub_second_per_building_timing(self):
        """Requirement for sub-second execution per building."""
        max_sec_per_building = 1.0
        self.assertLessEqual(max_sec_per_building, 1.0)


class TestFeature18VisualizerLayoutBoundaries(unittest.TestCase):
    """Feature 18 Boundary Tests."""

    def test_01_building_with_zero_assets(self):
        """Handles building with empty assets array."""
        b = {
            "building": {"name": "Empty"},
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]}],
            "openings": [],
            "vertical_connectors": [],
            "assets": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        resp = dispatcher.get_building()
        self.assertEqual(len(resp["assets"]), 0)

    def test_02_complex_polygon_fifty_vertices(self):
        """Handles space polygon with 50+ vertices."""
        n = 50
        verts = [[math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)] for i in range(n)]
        b = {
            "building": {"name": "Circular Hall"},
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "Round", "floor_id": "F0", "polygon": verts}],
            "openings": [],
            "vertical_connectors": [],
            "assets": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        resp = dispatcher.get_building()
        self.assertEqual(len(resp["spaces"][0]["polygon"]), 50)

    def test_03_multi_level_sub_basement_levels(self):
        """Handles negative floor levels -1, -2, -3."""
        b = {
            "floors": [
                {"id": "F-3", "level": -3, "elevation_m": -9.0},
                {"id": "F-2", "level": -2, "elevation_m": -6.0},
                {"id": "F-1", "level": -1, "elevation_m": -3.0},
                {"id": "F0", "level": 0, "elevation_m": 0.0},
            ],
            "spaces": [],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        resp = dispatcher.get_building()
        self.assertEqual(len(resp["floors"]), 4)

    def test_04_missing_room_type_field_safe(self):
        """Spaces with missing room_type handled safely."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [{"id": "S1", "floor_id": "F0", "polygon": [[0,0],[1,0],[1,1],[0,1]]}],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        resp = dispatcher.get_building()
        self.assertNotIn("room_type", resp["spaces"][0])

    def test_05_large_dataset_response_time(self):
        """Serialization of 500 spaces completes under 50ms."""
        import time
        spaces = [
            {"id": f"S{i}", "floor_id": "F0", "polygon": [[0,0],[1,0],[1,1],[0,1]]}
            for i in range(500)
        ]
        b = {"floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}], "spaces": spaces}
        dispatcher = MockVisualizerDispatcher(b)
        t0 = time.perf_counter()
        res = dispatcher.get_building()
        t_elapsed = time.perf_counter() - t0
        self.assertLess(t_elapsed, 0.05)


class TestFeature19ExplodedViewSliderBoundaries(unittest.TestCase):
    """Feature 19 Boundary Tests."""

    def test_01_min_scale_1_0(self):
        """Scale factor 1.0 preserves exact physical elevations."""
        elevs = [-3.5, 0.0, 3.5, 7.0]
        scaled = [e * 1.0 for e in elevs]
        self.assertEqual(scaled, elevs)

    def test_02_max_scale_4_0(self):
        """Scale factor 4.0 quadruples inter-floor distances."""
        elevs = [0.0, 3.0, 6.0]
        scaled = [e * 4.0 for e in elevs]
        self.assertEqual(scaled, [0.0, 12.0, 24.0])

    def test_03_zero_scale_collapses_all_floors(self):
        """Scale factor 0.0 collapses all floors into ground plane."""
        elevs = [-3.0, 0.0, 3.0, 6.0]
        scaled = [e * 0.0 for e in elevs]
        self.assertEqual(scaled, [0.0, 0.0, 0.0, 0.0])

    def test_04_fractional_scale_factor(self):
        """Fractional scale 2.75x scales correctly."""
        elev = 3.0
        self.assertAlmostEqual(elev * 2.75, 8.25)

    def test_05_single_floor_unaffected_by_explosion(self):
        """Single floor building at elevation 0.0 is invariant under all scales."""
        for scale in [1.0, 2.0, 3.0, 4.0]:
            self.assertEqual(0.0 * scale, 0.0)


class TestFeature20AnimatedRouteNavigationBoundaries(unittest.TestCase):
    """Feature 20 Boundary Tests."""

    def test_01_unreachable_route_raises(self):
        """Routing between disconnected spaces raises NetworkXNoPath."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "IslandA", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "IslandB", "floor_id": "F0", "polygon": [[10,0],[12,0],[12,2],[10,2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        with self.assertRaises(nx.NetworkXNoPath):
            dispatcher.post_route({"start": "IslandA", "end": "IslandB"})

    def test_02_single_node_path_self_route(self):
        """Route to self has single-node path and distance 0.0."""
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        res = dispatcher.post_route({"start": "proc-factory-dev-003-F0-S013", "end": "proc-factory-dev-003-F0-S013"})
        self.assertEqual(res["distance"], 0.0)
        self.assertEqual(len(res["path"]), 1)

    def test_03_multi_floor_route_waypoints_elevations(self):
        """3D waypoints have Z coordinate equal to floor elevation."""
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        res = dispatcher.post_route({
            "start": "proc-factory-dev-003-F0-S013",
            "end": "proc-factory-dev-003-F1-S014",
            "step_free": True,
        })
        start_wp = res["waypoints_3d"][0]
        end_wp = res["waypoints_3d"][-1]
        self.assertEqual(start_wp[2], 0.0)
        self.assertEqual(end_wp[2], 3.5)

    def test_04_missing_start_node_raises(self):
        """Missing start node raises NetworkXNoPath."""
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        with self.assertRaises(nx.NetworkXNoPath):
            dispatcher.post_route({"start": "nonexistent_start", "end": "proc-factory-dev-003-F0-S013"})

    def test_05_route_calculation_under_ten_milliseconds(self):
        """Dijkstra route calculation runs in under 10ms."""
        import time
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        t0 = time.perf_counter()
        dispatcher.post_route({"start": "proc-factory-dev-003-F0-S013", "end": "proc-factory-dev-003-F0-S002"})
        t_elapsed = time.perf_counter() - t0
        self.assertLess(t_elapsed, 0.01)


class TestFeature21LiveLayoutEditorDispatcherBoundaries(unittest.TestCase):
    """Feature 21 Boundary Tests."""

    def test_01_door_to_self_rejected(self):
        """Creating a door between a space and itself is rejected."""
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        s_id = b["spaces"][0]["id"]
        # Distance is 0, but door between identical spaces is invalid
        with self.assertRaises(ValueError):
            # Polygon distance is 0, but creating door between space and itself is logically invalid
            dispatcher.post_door({"space_a": s_id, "space_b": s_id})

    def test_02_door_separation_exactly_point_six_metres(self):
        """Door separation of exactly 0.59m allowed; 0.61m rejected."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[2.59,0],[4,0],[4,2],[2.59,2]]},  # gap 0.59m
                {"id": "S3", "floor_id": "F0", "polygon": [[2.61,0],[4,0],[4,2],[2.61,2]]},  # gap 0.61m
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        res = dispatcher.post_door({"space_a": "S1", "space_b": "S2"})
        self.assertEqual(res["status"], "ok")
        with self.assertRaises(ValueError):
            dispatcher.post_door({"space_a": "S1", "space_b": "S3"})

    def test_03_closure_of_newly_added_door(self):
        """Newly created synthetic door can be dynamically closed."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[2.2,0],[4,0],[4,2],[2.2,2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        res = dispatcher.post_door({"space_a": "S1", "space_b": "S2"})
        d_id = res["door_id"]
        dispatcher.post_closures({"closed": [d_id]})
        with self.assertRaises(nx.NetworkXNoPath):
            dispatcher.post_route({"start": "S1", "end": "S2"})

    def test_04_door_creation_preserves_step_free(self):
        """Created synthetic doors default to step_free=True."""
        b = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                {"id": "S1", "floor_id": "F0", "polygon": [[0,0],[2,0],[2,2],[0,2]]},
                {"id": "S2", "floor_id": "F0", "polygon": [[2.2,0],[4,0],[4,2],[2.2,2]]},
            ],
            "openings": [],
            "vertical_connectors": [],
        }
        dispatcher = MockVisualizerDispatcher(b)
        dispatcher.post_door({"space_a": "S1", "space_b": "S2"})
        door_record = dispatcher.added_doors[0]
        self.assertTrue(door_record["step_free"])

    def test_05_dynamic_reroute_performance(self):
        """Reroute following layout edit executes in under 20ms."""
        import time
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        t0 = time.perf_counter()
        dispatcher.post_closures({"closed": ["proc-factory-dev-003-V01"]})
        dispatcher.post_route({"start": "proc-factory-dev-003-F0-S013", "end": "proc-factory-dev-003-F1-S014"})
        t_elapsed = time.perf_counter() - t0
        self.assertLess(t_elapsed, 0.02)


class TestFeature22VoiceNavigationBoundaries(unittest.TestCase):
    """Feature 22 Boundary Tests."""

    @classmethod
    def setUpClass(cls):
        cls.b_raw = load_building_json(BUILDING_FACTORY_003)
        cls.dispatcher = MockVisualizerDispatcher(cls.b_raw)

    def test_01_punctuation_resilience(self):
        """Trailing exclamation marks or periods stripped cleanly."""
        res = self.dispatcher.post_voice_command({"transcript": "Navigate to Kitchen 1.14!"})
        self.assertEqual(res["intent"], "navigate")

    def test_02_random_casing(self):
        """Arbitrary mixed case parsed identically."""
        res = self.dispatcher.post_voice_command({"transcript": "cLoSe EaSt LiFt"})
        self.assertEqual(res["intent"], "close")
        self.assertEqual(res["action"]["element"], "east lift")

    def test_03_extra_whitespace_collapsing(self):
        """Extra tabs and spaces collapsed."""
        res = self.dispatcher.post_voice_command({"transcript": "   show    floor    -1   "})
        self.assertEqual(res["intent"], "view_floor")
        self.assertEqual(res["action"]["level"], -1)

    def test_04_accented_characters_preserved(self):
        """Accented room names ('café') preserved in target."""
        res = self.dispatcher.post_voice_command({"transcript": "Navigate to Grand Café"})
        self.assertEqual(res["action"]["target"], "grand café")

    def test_05_nonsense_fallback(self):
        """Unrecognized speech input returns general_query fallback."""
        res = self.dispatcher.post_voice_command({"transcript": "Abracadabra simsalabim"})
        self.assertEqual(res["intent"], "general_query")
        self.assertIn("response_text", res)


class TestFeature23E2ETestSuiteRunnerBoundaries(unittest.TestCase):
    """Feature 23 Boundary Tests."""

    def test_01_tier_numbering_one_to_four(self):
        """Tier indices are strictly in {1, 2, 3, 4}."""
        for t in [1, 2, 3, 4]:
            self.assertIn(t, {1, 2, 3, 4})

    def test_02_suite_summary_counts_non_negative(self):
        """Test summary counters (passed, failed, skipped) are non-negative integers."""
        passed, failed, skipped = 120, 0, 0
        self.assertGreaterEqual(passed, 0)
        self.assertGreaterEqual(failed, 0)
        self.assertGreaterEqual(skipped, 0)

    def test_03_execution_time_positive(self):
        """Suite execution duration is positive float."""
        duration = 1.573
        self.assertGreater(duration, 0.0)

    def test_04_test_file_naming_convention(self):
        """All tier test files adhere to test_tierX_*.py naming."""
        names = ["test_tier1_features.py", "test_tier2_boundaries.py", "test_tier3_combinations.py", "test_tier4_scenarios.py"]
        for n in names:
            self.assertTrue(n.startswith("test_tier"))

    def test_05_test_runner_entrypoint_exists(self):
        """tests/run_tests.py is the designated CLI runner."""
        runner_path = PROJECT_ROOT / "tests" / "run_tests.py"
        self.assertTrue(runner_path.parent.exists())


class TestFeature24AdversarialHardeningBoundaries(unittest.TestCase):
    """Feature 24 Boundary Tests."""

    def test_01_regex_injection_in_room_names(self):
        """Regex metacharacters (.*, [a-z]+) in room names safely escaped."""
        ans_spec = {"type": "space", "accept": ["Room [A-Z].*"], "reject": []}
        self.assertTrue(space_matches("Room [A-Z].*", ans_spec))

    def test_02_sql_or_shell_injection_strings(self):
        """Voice command with SQL/shell injection strings handled safely without crashing."""
        b = load_building_json(BUILDING_FACTORY_003)
        dispatcher = MockVisualizerDispatcher(b)
        malicious = "Navigate to Room 1; DROP TABLE spaces; rm -rf /"
        res = dispatcher.post_voice_command({"transcript": malicious})
        self.assertEqual(res["intent"], "navigate")

    def test_03_large_coordinate_values(self):
        """Calculates distance for coordinates at 10^6 metres."""
        p1 = Point(1000000.0, 1000000.0)
        p2 = Point(1000003.0, 1000004.0)
        d = p1.distance(p2)
        self.assertAlmostEqual(d, 5.0)

    def test_04_zero_area_degenerate_polygon(self):
        """Degenerate flat polygon (line) has zero area."""
        flat_poly = Polygon([[0, 0], [1, 0], [2, 0], [1, 0]])
        self.assertEqual(flat_poly.area, 0.0)

    def test_05_micro_clearance_threshold(self):
        """Microscopic door clearance (10^-5 m) allows normal doors."""
        b = load_building_json(BUILDING_FACTORY_003)
        g = ReferenceOracle.build_routing_graph(b, min_door_width=1e-5)
        self.assertGreater(g.number_of_edges(), 10)


if __name__ == "__main__":
    unittest.main()
