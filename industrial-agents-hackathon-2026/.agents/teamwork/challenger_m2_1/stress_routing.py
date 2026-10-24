"""Adversarial stress harness for Milestone 2 Multi-Floor Routing & Constraint Engine.

Tests:
1. Disconnected floor graphs & unreachability (missing connectors, isolated rooms, NetworkXNoPath).
2. Dynamic closures (closing all lifts on step-free errand/route, space closures, door closures).
3. Door clearance boundary precision (min_width, min_width - 0.01 rejected, min_width + 0.01 accepted).
4. What-if door counterfactuals (already directly connected vs far apart >0.6m vs shortcut).
5. Multi-stop errand routing stress (tie-breaking, co-located asset/start/target, unreachable assets).
6. High-throughput performance & stress queries (1,000 queries latency).
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

import networkx as nx
from shapely.geometry import Polygon

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatial_engine import load_building  # noqa: E402
from spatial_engine.graph import DOOR_PREFIX, build_routing_graph  # noqa: E402
from spatial_engine.models import (  # noqa: E402
    Asset,
    Building,
    BuildingMetadata,
    Connector,
    Floor,
    Opening,
    Space,
)
from spatial_engine.router import (  # noqa: E402
    count_reachable_rooms,
    evaluate_what_if_door,
    find_route,
    shortest_path,
    solve_errand,
)

DEV_DATA_DIR = PROJECT_ROOT / "data" / "dev"
BUILDING_FACTORY_003 = DEV_DATA_DIR / "proc-factory-dev-003"
BUILDING_FACTORY_012 = DEV_DATA_DIR / "proc-factory-dev-012"
BUILDING_OSM_22744230 = DEV_DATA_DIR / "osm-way22744230"


def make_space(
    s_id: str,
    floor_id: str,
    coords: list[tuple[float, float]],
    stype: str = "room",
    room_type: str = "office",
    name: str = "",
) -> Space:
    poly = Polygon(coords)
    rep = poly.representative_point()
    return Space(
        id=s_id,
        floor_id=floor_id,
        type=stype,
        room_type=room_type,
        name=name or s_id,
        ref=s_id,
        polygon_coords=list(poly.exterior.coords),
        polygon=poly,
        area=float(poly.area),
        centroid=(float(poly.centroid.x), float(poly.centroid.y)),
        representative_point=(float(rep.x), float(rep.y)),
        exterior_ring=poly.exterior,
    )


def build_test_building(
    include_stairs: bool = True,
    include_lift: bool = True,
    door1_width: float = 1.0,
    door2_width: float = 0.8,
) -> Building:
    """Build a multi-floor synthetic building with customizable connectors and door widths."""
    meta = BuildingMetadata(id="stress-bldg", name="Stress Test Building", source="challenger")
    f0 = Floor(id="F0", level=0, name="Ground Floor", elevation_m=0.0, height_m=3.5)
    f1 = Floor(id="F1", level=1, name="First Floor", elevation_m=3.5, height_m=3.5)
    floors = {"F0": f0, "F1": f1}
    floors_by_level = {0: f0, 1: f1}

    # Floor 0 spaces:
    # S01: (0,0) -> (4,4) Room (office)
    # S02: (4,0) -> (8,4) Room (storage)
    # S03: (0,4) -> (8,6) Corridor
    # S0_stair: (0,6) -> (3,8) Stair space
    # S0_lift: (5,6) -> (8,8) Lift space
    s01 = make_space("S01", "F0", [(0, 0), (4, 0), (4, 4), (0, 4)], "room", "office")
    s02 = make_space("S02", "F0", [(4, 0), (8, 0), (8, 4), (4, 4)], "room", "storage")
    s03 = make_space("S03", "F0", [(0, 4), (8, 4), (8, 6), (0, 6)], "corridor", "corridor")
    s0_stair = make_space("S0_stair", "F0", [(0, 6), (3, 6), (3, 8), (0, 8)], "stairs", "stairs")
    s0_lift = make_space("S0_lift", "F0", [(5, 6), (8, 6), (8, 8), (5, 8)], "lift", "lift")

    # Floor 1 spaces:
    # S11: (0,0) -> (4,4) Room (conference)
    # S12: (4,0) -> (8,4) Room (office)
    # S13: (0,4) -> (8,6) Corridor
    # S1_stair: (0,6) -> (3,8) Stair space
    # S1_lift: (5,6) -> (8,8) Lift space
    s11 = make_space("S11", "F1", [(0, 0), (4, 0), (4, 4), (0, 4)], "room", "conference")
    s12 = make_space("S12", "F1", [(4, 0), (8, 0), (8, 4), (4, 4)], "room", "office")
    s13 = make_space("S13", "F1", [(0, 4), (8, 4), (8, 6), (0, 6)], "corridor", "corridor")
    s1_stair = make_space("S1_stair", "F1", [(0, 6), (3, 6), (3, 8), (0, 8)], "stairs", "stairs")
    s1_lift = make_space("S1_lift", "F1", [(5, 6), (8, 6), (8, 8), (5, 8)], "lift", "lift")

    spaces = {
        s.id: s
        for s in [
            s01, s02, s03, s0_stair, s0_lift,
            s11, s12, s13, s1_stair, s1_lift,
        ]
    }
    spaces_by_floor = {
        "F0": [s01, s02, s03, s0_stair, s0_lift],
        "F1": [s11, s12, s13, s1_stair, s1_lift],
    }

    # Openings Floor 0:
    # D01: S01 <-> S03 (at y=4, x=2)
    # D02: S02 <-> S03 (at y=4, x=6)
    # D0_stair: S03 <-> S0_stair (at y=6, x=1.5)
    # D0_lift: S03 <-> S0_lift (at y=6, x=6.5)
    # D_ext: S03 <-> outside (at y=5, x=8)
    d01 = Opening(
        id="D01", floor_id="F0", kind="door", space_ids=["S01", "S03"],
        position=(2.0, 4.0), width_m=door1_width, step_free=True
    )
    d02 = Opening(
        id="D02", floor_id="F0", kind="door", space_ids=["S02", "S03"],
        position=(6.0, 4.0), width_m=door2_width, step_free=True
    )
    d0_stair = Opening(
        id="D0_stair", floor_id="F0", kind="door", space_ids=["S03", "S0_stair"],
        position=(1.5, 6.0), width_m=0.9, step_free=True
    )
    d0_lift = Opening(
        id="D0_lift", floor_id="F0", kind="door", space_ids=["S03", "S0_lift"],
        position=(6.5, 6.0), width_m=0.9, step_free=True
    )
    d_ext = Opening(
        id="D_ext", floor_id="F0", kind="entrance", space_ids=["S03", "outside"],
        position=(8.0, 5.0), width_m=1.2, step_free=True
    )

    # Openings Floor 1:
    d11 = Opening(
        id="D11", floor_id="F1", kind="door", space_ids=["S11", "S13"],
        position=(2.0, 4.0), width_m=1.0, step_free=True
    )
    d12 = Opening(
        id="D12", floor_id="F1", kind="door", space_ids=["S12", "S13"],
        position=(6.0, 4.0), width_m=1.0, step_free=True
    )
    d1_stair = Opening(
        id="D1_stair", floor_id="F1", kind="door", space_ids=["S13", "S1_stair"],
        position=(1.5, 6.0), width_m=0.9, step_free=True
    )
    d1_lift = Opening(
        id="D1_lift", floor_id="F1", kind="door", space_ids=["S13", "S1_lift"],
        position=(6.5, 6.0), width_m=0.9, step_free=True
    )

    openings = {
        o.id: o
        for o in [
            d01, d02, d0_stair, d0_lift, d_ext,
            d11, d12, d1_stair, d1_lift,
        ]
    }
    openings_by_floor = {
        "F0": [d01, d02, d0_stair, d0_lift, d_ext],
        "F1": [d11, d12, d1_stair, d1_lift],
    }

    # Vertical connectors
    connectors = {}
    connectors_by_floor = {"F0": [], "F1": []}
    if include_stairs:
        c_stairs = Connector(
            id="CONN_STAIRS",
            kind="stairs",
            name="Main Staircase",
            floor_ids=["F0", "F1"],
            space_ids=["S0_stair", "S1_stair"],
            step_free=False,
        )
        connectors["CONN_STAIRS"] = c_stairs
        connectors_by_floor["F0"].append(c_stairs)
        connectors_by_floor["F1"].append(c_stairs)

    if include_lift:
        c_lift = Connector(
            id="CONN_LIFT",
            kind="lift",
            name="Main Elevator",
            floor_ids=["F0", "F1"],
            space_ids=["S0_lift", "S1_lift"],
            step_free=True,
        )
        connectors["CONN_LIFT"] = c_lift
        connectors_by_floor["F0"].append(c_lift)
        connectors_by_floor["F1"].append(c_lift)

    # Assets
    a1 = Asset(
        id="A1", name="Extinguisher 1", category="safety",
        type="extinguisher", space_id="S02", floor_id="F0",
        position=(6.0, 2.0)
    )
    a2 = Asset(
        id="A2", name="Defibrillator 1", category="medical",
        type="defibrillator", space_id="S11", floor_id="F1",
        position=(2.0, 2.0)
    )
    assets = {"A1": a1, "A2": a2}
    assets_by_type = {"extinguisher": [a1], "defibrillator": [a2]}
    assets_by_space = {"S02": [a1], "S11": [a2]}

    return Building(
        metadata=meta,
        floors=floors,
        floors_by_level=floors_by_level,
        spaces=spaces,
        spaces_by_floor=spaces_by_floor,
        openings=openings,
        openings_by_floor=openings_by_floor,
        connectors=connectors,
        connectors_by_floor=connectors_by_floor,
        assets=assets,
        assets_by_type=assets_by_type,
        assets_by_space=assets_by_space,
    )


class TestStressRoutingEngine(unittest.TestCase):
    """Stress tests covering all required adversarial edge cases."""

    # =========================================================================
    # Edge Case 1: Disconnected floor graph
    # =========================================================================

    def test_01_disconnected_floors_no_connectors(self):
        """When a building has no vertical connectors, multi-floor paths must be unreachable."""
        bldg = build_test_building(include_stairs=False, include_lift=False)
        g = build_routing_graph(bldg)

        # 1. shortest_path between floors must raise NetworkXNoPath
        with self.assertRaises(nx.NetworkXNoPath):
            shortest_path(g, "S01", "S11")

        # 2. find_route between floors must raise NetworkXNoPath
        with self.assertRaises(nx.NetworkXNoPath):
            find_route(bldg, "S01", "S11")

        # 3. count_reachable_rooms from F0 to F1 must return exactly 0
        count_f1 = count_reachable_rooms(bldg, "S01", target_floor_id="F1")
        self.assertEqual(count_f1, 0)

        # 4. Same floor reachable count should still work normally
        count_f0 = count_reachable_rooms(bldg, "S01", target_floor_id="F0")
        self.assertEqual(count_f0, 2)  # S01 and S02

        # 5. solve_errand starting on F0 with target on F1 must raise NetworkXNoPath
        with self.assertRaises(nx.NetworkXNoPath):
            solve_errand(bldg, "S01", "extinguisher", "conference", "F1")

    def test_02_isolated_space_no_doors(self):
        """A space with no openings is an isolated island."""
        bldg = build_test_building()
        # Create an island space with no door
        island = make_space("ISLAND_99", "F0", [(20, 20), (25, 20), (25, 25), (20, 25)], "room", "office")
        bldg.spaces["ISLAND_99"] = island
        bldg.spaces_by_floor["F0"].append(island)

        g = build_routing_graph(bldg)

        # Island is in graph as an isolated node
        self.assertIn("ISLAND_99", g)
        self.assertEqual(g.degree("ISLAND_99"), 0)

        # Shortest path to or from island raises NetworkXNoPath
        with self.assertRaises(nx.NetworkXNoPath):
            shortest_path(g, "S01", "ISLAND_99")
        with self.assertRaises(nx.NetworkXNoPath):
            shortest_path(g, "ISLAND_99", "S01")

        # Self-path is trivial (0 distance, 1 node)
        res_self = shortest_path(g, "ISLAND_99", "ISLAND_99")
        self.assertEqual(res_self.distance, 0.0)
        self.assertEqual(res_self.path, ["ISLAND_99"])

        # Reachable rooms starting from island: only itself
        count_from_island = count_reachable_rooms(bldg, "ISLAND_99", target_floor_id="F0")
        self.assertEqual(count_from_island, 1)

        # Reachable rooms starting from S01: must NOT include island
        count_from_s01 = count_reachable_rooms(bldg, "S01", target_floor_id="F0")
        self.assertEqual(count_from_s01, 2)  # S01, S02

    def test_03_missing_or_invalid_node_handling(self):
        """Missing or non-existent node identifiers raise NodeNotFound."""
        bldg = build_test_building()
        g = build_routing_graph(bldg)

        with self.assertRaises(nx.NodeNotFound):
            shortest_path(g, "NON_EXISTENT_SOURCE", "S01")
        with self.assertRaises(nx.NodeNotFound):
            shortest_path(g, "S01", "NON_EXISTENT_TARGET")

    # =========================================================================
    # Edge Case 2: Dynamic closures
    # =========================================================================

    def test_04_closing_all_lifts_on_step_free_errand(self):
        """Closing all lifts makes a step-free multi-floor errand or route impossible."""
        bldg = build_test_building(include_stairs=True, include_lift=True)

        # Before closure:
        # Step-free route F0 to F1 succeeds via lift
        res_before = find_route(bldg, "S01", "S11", step_free=True)
        self.assertTrue(res_before.step_free)
        self.assertIn("S0_lift", res_before.path)
        self.assertIn("S1_lift", res_before.path)

        # Now dynamically close the lift connector
        closed_lift = {"CONN_LIFT"}
        g_closed = build_routing_graph(bldg, step_free=True, closed=closed_lift)

        # In step-free mode, stairs are pruned, and lift is closed -> disconnected!
        with self.assertRaises(nx.NetworkXNoPath):
            shortest_path(g_closed, "S01", "S11")

        with self.assertRaises(nx.NetworkXNoPath):
            find_route(bldg, "S01", "S11", step_free=True, closed=closed_lift)

        # Reachable count to F1 under step_free with lift closed must be 0
        reach_f1_closed = count_reachable_rooms(bldg, "S01", "F1", step_free=True, closed=closed_lift)
        self.assertEqual(reach_f1_closed, 0)

        # However, non-step-free route must STILL SUCCEED using the stairs!
        res_stairs = find_route(bldg, "S01", "S11", step_free=False, closed=closed_lift)
        self.assertIn("S0_stair", res_stairs.path)
        self.assertIn("S1_stair", res_stairs.path)

    def test_05_closing_lift_space_blocks_lift(self):
        """Closing a lift stop space also blocks passage through that lift."""
        bldg = build_test_building(include_stairs=True, include_lift=True)
        closed_space = {"S0_lift"}

        # Step-free route should fail because S0_lift is closed
        with self.assertRaises(nx.NetworkXNoPath):
            find_route(bldg, "S01", "S11", step_free=True, closed=closed_space)

    def test_06_closure_idempotence_and_reopening(self):
        """Reopening closed elements restores the graph to full connectivity."""
        bldg = build_test_building(include_stairs=True, include_lift=True)
        closures = {"CONN_LIFT", "CONN_STAIRS", "D01"}

        g_closed = build_routing_graph(bldg, closed=closures)
        self.assertNotIn("D01", [e[2].get("via") for e in g_closed.edges(data=True)])

        # Reopen by passing empty set
        g_reopened = build_routing_graph(bldg, closed=set())
        # Both stairs and lift available
        kinds = {e[2].get("kind") for e in g_reopened.edges(data=True)}
        self.assertIn("lift", kinds)
        self.assertIn("stairs", kinds)

    # =========================================================================
    # Edge Case 3: Door clearance precision
    # =========================================================================

    def test_07_door_clearance_boundary_precision(self):
        """Test door openings at width == min_width, min_width - 0.01 (rejected), min_width + 0.01 (accepted)."""
        target_min_width = 1.00

        # Subtest A: Door exactly at min_width (1.00 m) -> must be ACCEPTED
        bldg_exact = build_test_building(door1_width=1.00, door2_width=0.80)
        g_exact = build_routing_graph(bldg_exact, min_door_width=target_min_width)
        door_node = f"{DOOR_PREFIX}D01"
        self.assertIn(door_node, g_exact, "Door exactly at min_width (1.00m) MUST be accepted in graph")
        # S01 should be connected to S03 via D01
        self.assertTrue(g_exact.has_edge("S01", door_node))

        # Subtest B: Door at min_width - 0.01 (0.99 m) -> must be REJECTED
        bldg_narrow = build_test_building(door1_width=0.99, door2_width=0.80)
        g_narrow = build_routing_graph(bldg_narrow, min_door_width=target_min_width)
        self.assertNotIn(door_node, g_narrow, "Door at min_width - 0.01 (0.99m) MUST be rejected from graph")
        # S01 cannot reach S03 because its only door is D01
        with self.assertRaises(nx.NetworkXNoPath):
            shortest_path(g_narrow, "S01", "S03")

        # Subtest C: Door at min_width + 0.01 (1.01 m) -> must be ACCEPTED
        bldg_wide = build_test_building(door1_width=1.01, door2_width=0.80)
        g_wide = build_routing_graph(bldg_wide, min_door_width=target_min_width)
        self.assertIn(door_node, g_wide, "Door at min_width + 0.01 (1.01m) MUST be accepted in graph")
        self.assertTrue(g_wide.has_edge("S01", door_node))
        # Route through D01 must succeed
        res = shortest_path(g_wide, "S01", "S03")
        self.assertIn(door_node, res.path)

    def test_08_door_clearance_reachable_count_differential(self):
        """Verify count_reachable_rooms reflects door width filtering threshold."""
        target_min_width = 1.00

        # S02 has door D02 width 0.80m. S01 has D01.
        # When D01 is 0.99m (< 1.00m), S01 cannot reach S03 or any other rooms
        bldg_under = build_test_building(door1_width=0.99, door2_width=0.80)
        # Starting from S03: S01 and S02 both have doors < 1.0m, so reachable rooms on F0 is 0!
        count_under = count_reachable_rooms(bldg_under, "S03", "F0", min_width=target_min_width)
        self.assertEqual(count_under, 0)

        # When D01 is 1.00m (>= 1.00m), S01 becomes reachable from S03
        bldg_exact = build_test_building(door1_width=1.00, door2_width=0.80)
        count_exact = count_reachable_rooms(bldg_exact, "S03", "F0", min_width=target_min_width)
        self.assertEqual(count_exact, 1)  # S01 is reachable, S02 (0.80m) is still blocked

        # When both D01 and D02 >= 1.00m, both become reachable
        bldg_both = build_test_building(door1_width=1.00, door2_width=1.05)
        count_both = count_reachable_rooms(bldg_both, "S03", "F0", min_width=target_min_width)
        self.assertEqual(count_both, 2)

    # =========================================================================
    # Edge Case 4: What-if door counterfactuals
    # =========================================================================

    def test_09_what_if_door_far_apart_raises_value_error(self):
        """Spaces separated by > 0.6 m must raise ValueError."""
        bldg = build_test_building()
        # S01: (0,0)-(4,4)
        # S0_lift: (5,6)-(8,8) -> Euclidean distance between polygons is > 0.6m
        with self.assertRaises(ValueError):
            evaluate_what_if_door(bldg, "S01", "S0_lift", target_floor_id="F0")

    def test_10_what_if_door_already_directly_connected(self):
        """When spaces are already directly connected, adding a virtual door yields 0 improved rooms."""
        bldg = build_test_building()
        # S01 and S03 share door D01.
        # Adding another door between S01 and S03 does NOT significantly improve exit distance to outside
        improved_count = evaluate_what_if_door(bldg, "S01", "S03", target_floor_id="F0", threshold=1.0)
        self.assertEqual(improved_count, 0, "Adding door between already connected adjacent spaces should yield 0 improved rooms")

    def test_11_what_if_door_shortcut_improves_exit_distance(self):
        """When adjacent rooms have no direct door and long detour, what-if door improves exit distance."""
        # Create a building with two adjacent rooms S_A and S_B:
        # S_A is adjacent to outside exit.
        # S_B has to walk through a 50m long detour corridor to reach S_A and outside.
        # S_A and S_B share a wall (distance = 0.0).
        bldg_detour = {
            "floors": [{"id": "F0", "level": 0, "elevation_m": 0.0}],
            "spaces": [
                # Room A: (0,0) -> (4,4)
                {"id": "ROOM_A", "floor_id": "F0", "type": "room", "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                # Room B: (4,0) -> (8,4), shares wall at x=4 with ROOM_A
                {"id": "ROOM_B", "floor_id": "F0", "type": "room", "polygon": [[4, 0], [8, 0], [8, 4], [4, 4]]},
                # Corridor starting at (8,2) going 50m away and looping back to (2,4)
                {"id": "CORR_LONG", "floor_id": "F0", "type": "corridor", "polygon": [[4, 4], [8, 4], [8, 50], [0, 50], [0, 4]]},
            ],
            "openings": [
                # ROOM_A has direct door to outside at (0, 2)
                {"id": "D_OUT", "floor_id": "F0", "kind": "entrance", "space_ids": ["ROOM_A", "outside"], "position": [0.0, 2.0], "width_m": 1.0, "step_free": True},
                # ROOM_A connected to CORR_LONG at (2, 4)
                {"id": "D_A_CORR", "floor_id": "F0", "kind": "door", "space_ids": ["ROOM_A", "CORR_LONG"], "position": [2.0, 4.0], "width_m": 1.0, "step_free": True},
                # ROOM_B has door to CORR_LONG way up at (6, 50)
                {"id": "D_B_CORR", "floor_id": "F0", "kind": "door", "space_ids": ["ROOM_B", "CORR_LONG"], "position": [6.0, 50.0], "width_m": 1.0, "step_free": True},
            ],
            "vertical_connectors": [],
            "assets": [],
        }

        # S_B currently has to walk up to y=50 to exit! That is > 40m walk.
        # Adding a direct door between ROOM_A and ROOM_B at x=4 saves ~40m!
        # Threshold is 1.0m. So ROOM_B must be improved by > 1.0m!
        count = evaluate_what_if_door(bldg_detour, "ROOM_A", "ROOM_B", target_floor_id="F0", threshold=1.0)
        self.assertEqual(count, 1, "ROOM_B should experience > 1.0m exit distance improvement")

    # =========================================================================
    # Edge Case 5: Multi-stop errand routing stress
    # =========================================================================

    def test_12_errand_nearest_asset_dijkstra_selection(self):
        """solve_errand selects nearest asset by graph shortest path, not straight line."""
        bldg = build_test_building()
        # Add a second extinguisher in S01 (start space)
        # Extinguisher A_close in S01 has distance 0.0!
        a_close = Asset(
            id="A_CLOSE", name="Close Extinguisher", category="safety",
            type="extinguisher", space_id="S01", floor_id="F0",
            position=(2.0, 2.0)
        )
        bldg.assets["A_CLOSE"] = a_close
        bldg.assets_by_type["extinguisher"].append(a_close)
        bldg.assets_by_space.setdefault("S01", []).append(a_close)

        res = solve_errand(bldg, "S01", "extinguisher", "storage", "F0")
        # Should pick A_CLOSE in S01!
        self.assertEqual(res.via, "S01")
        self.assertEqual(res.leg1_distance, 0.0)
        self.assertEqual(res.target, "S02")
        self.assertGreater(res.total_distance, 0.0)

    def test_13_errand_unreachable_asset_raises_no_path(self):
        """solve_errand raises NetworkXNoPath when asset exists but is in an unreachable island."""
        bldg = build_test_building()
        # Put an asset of rare type in an isolated island
        island = make_space("ISLAND_ASSET", "F0", [(30, 30), (35, 30), (35, 35), (30, 35)], "room", "storage")
        bldg.spaces["ISLAND_ASSET"] = island
        bldg.spaces_by_floor["F0"].append(island)
        rare_asset = Asset(
            id="A_RARE", name="Quantum Computer", category="computing",
            type="quantum_computer", space_id="ISLAND_ASSET", floor_id="F0",
            position=(32.0, 32.0)
        )
        bldg.assets["A_RARE"] = rare_asset
        bldg.assets_by_type["quantum_computer"] = [rare_asset]

        with self.assertRaises(nx.NetworkXNoPath):
            solve_errand(bldg, "S01", "quantum_computer", "conference", "F1")

    def test_14_errand_nonexistent_asset_type_raises_value_error(self):
        """solve_errand raises ValueError when asset type is completely absent."""
        bldg = build_test_building()
        with self.assertRaises(ValueError):
            solve_errand(bldg, "S01", "nonexistent_asset_type_xyz", "office", "F0")

    # =========================================================================
    # Edge Case 6: Real-world dev building stress & performance
    # =========================================================================

    def test_15_dev_building_multi_floor_stress_and_performance(self):
        """Execute 1,000 route computations on a complex real industrial facility (proc-factory-dev-003)."""
        self.assertTrue(BUILDING_FACTORY_003.exists(), f"Dev building {BUILDING_FACTORY_003} missing")
        bldg = load_building(BUILDING_FACTORY_003)
        g = build_routing_graph(bldg)

        # Confirm non-empty graph with stairs and lift edges
        self.assertGreater(len(g.nodes), 20)
        self.assertGreater(len(g.edges), 30)

        # Measure 1,000 Dijkstra shortest path computations
        start_node = "proc-factory-dev-003-F0-S013"
        end_node = "proc-factory-dev-003-F1-S014"

        t0 = time.perf_counter()
        for _ in range(1000):
            res = shortest_path(g, start_node, end_node)
        elapsed = time.perf_counter() - t0

        avg_latency_ms = (elapsed / 1000.0) * 1000.0
        print(f"\n[PERFORMANCE] 1,000 Dijkstra queries completed in {elapsed:.3f}s (Avg: {avg_latency_ms:.3f} ms/query)")
        self.assertLess(avg_latency_ms, 1.0, "Dijkstra query must run in under 1ms on average")
        self.assertGreater(res.distance, 10.0)

    def test_16_osm_way22744230_step_free_closure_benchmark_accuracy(self):
        """Validate step-free reachable count on 3-floor building osm-way22744230 matches benchmark ground truth."""
        if not BUILDING_OSM_22744230.exists():
            self.skipTest("OSM building not available")

        bldg = load_building(BUILDING_OSM_22744230)
        start_space = "osm-way22744230-F0-S029"
        target_floor = "osm-way22744230-F2"

        # Benchmark question H03: Lift osm-way22744230-V07 closed -> exactly 30 rooms reachable via remaining lift
        count_v07_closed = count_reachable_rooms(
            bldg, start_space, target_floor, step_free=True, closed={"osm-way22744230-V07"}
        )
        self.assertEqual(count_v07_closed, 30)

        # Adversarial closure: Close ALL lifts in the building -> step-free count must drop to 0!
        all_lifts = {c.id for c in bldg.connectors.values() if c.is_lift}
        self.assertGreater(len(all_lifts), 1, "Building should have multiple lifts")
        count_all_closed = count_reachable_rooms(
            bldg, start_space, target_floor, step_free=True, closed=all_lifts
        )
        self.assertEqual(count_all_closed, 0, "When all lifts are closed, step-free reachability to F2 MUST be 0")


def run_stress_suite() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestStressRoutingEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_stress_suite()
    sys.exit(0 if success else 1)
