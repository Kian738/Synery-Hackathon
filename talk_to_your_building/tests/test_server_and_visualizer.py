"""Comprehensive automated verification test suite for server.py and landmarks.py.

Validates:
  - list_available_buildings scanning across dev and test datasets
  - GET /api/buildings and GET /api/building/state payload structure
  - POST /api/route constrained routing, 3D waypoints, and landmark guidance
  - POST /api/incident connector closure toggling and dynamic counterfactual door insertion
  - Vector cross-product relative landmark orientation (left vs right)
  - Ambiguity clarification state machine
  - HTTP Server end-to-end socket request execution
"""

import json
import threading
import time
import urllib.request
import unittest

from talk_to_your_building.server import (
    SESSION,
    list_available_buildings,
    run_server,
)
from talk_to_your_building.spatial_engine.landmarks import (
    calculate_segment_landmarks,
    clarify_query,
    compute_path_waypoints,
    generate_landmark_instructions,
    resolve_clarification,
)
from talk_to_your_building.spatial_engine.router import find_route


class TestServerAndVisualizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure session loaded dev factory
        cls.building = SESSION.load_or_switch_building("proc-factory-dev-003")
        assert cls.building is not None, "Failed to load proc-factory-dev-003"

    def test_01_list_available_buildings(self):
        buildings = list_available_buildings()
        self.assertGreater(len(buildings), 0, "Should discover buildings in data/dev and data/test")
        ids = [b["id"] for b in buildings]
        self.assertIn("proc-factory-dev-003", ids)

    def test_02_landmarks_cross_product_orientation(self):
        # Test vector cross-product orientation logic
        # Moving from (0, 0) to (10, 0): +X direction
        p1 = [0.0, 0.0, 0.0]
        p2 = [10.0, 0.0, 0.0]

        # In proc-factory-dev-003, query segment landmarks along ground floor
        f0 = self.building.floors_by_level[0].id
        spaces = self.building.spaces_by_floor[f0]
        # Choose a space with assets
        asset_spaces = [s for s in spaces if s.id in self.building.assets_by_space]
        self.assertTrue(len(asset_spaces) > 0, "Ground floor should contain spaces with assets")

        sp = asset_spaces[0]
        assets = self.building.assets_by_space[sp.id]
        ast = assets[0]
        # Create segment near this asset
        seg_p1 = [ast.position[0] - 2.0, ast.position[1] - 1.0, 0.0]
        seg_p2 = [ast.position[0] + 2.0, ast.position[1] - 1.0, 0.0]

        landmarks = calculate_segment_landmarks(self.building, seg_p1, seg_p2, floor_id=f0)
        self.assertTrue(len(landmarks) > 0, "Should observe nearby asset")
        # Since asset y is greater than line y (ast.pos[1] > seg_p1[1]), and vector is along +X:
        # cross = vx * uy - vy * ux = 4.0 * (1.0) - 0 = +4.0 > 0 -> LEFT
        obs = next((o for o in landmarks if o.asset.id == ast.id), None)
        self.assertIsNotNone(obs)
        self.assertEqual(obs.side, "left")

    def test_03_ambiguity_clarification(self):
        # Ambiguous query matching multiple CNC mills
        res_ambiguous = clarify_query("mill", self.building)
        self.assertTrue(res_ambiguous["ambiguous"])
        self.assertGreater(res_ambiguous["count"], 1)
        self.assertTrue(len(res_ambiguous["candidates"]) > 1)

        # Disambiguate using resolve_clarification
        choice = resolve_clarification("first", res_ambiguous["candidates"])
        self.assertIsNotNone(choice)
        self.assertEqual(choice["id"], res_ambiguous["candidates"][0]["id"])

        # Specific query matching unique space or machine
        res_unique = clarify_query("CNC mill H-A1-A", self.building)
        self.assertFalse(res_unique["ambiguous"])
        self.assertIsNotNone(res_unique["target_id"])

    def test_04_landmark_instructions_generation(self):
        f0 = self.building.floors_by_level[0].id
        f1 = self.building.floors_by_level[1].id
        s_start = list(self.building.spaces_by_floor[f0])[0].id
        s_end = list(self.building.spaces_by_floor[f1])[0].id

        route = find_route(self.building, s_start, s_end)
        self.assertTrue(route.success)

        waypoints = compute_path_waypoints(self.building, route.path_nodes)
        self.assertEqual(len(waypoints), len(route.path_nodes))

        instructions = generate_landmark_instructions(self.building, route.path_nodes, waypoints)
        self.assertGreater(len(instructions), 1)
        self.assertTrue(any("Start in" in s for s in instructions))
        self.assertTrue(any("destination" in s.lower() for s in instructions))

    def test_05_dynamic_closure_and_rerouting(self):
        f0 = self.building.floors_by_level[0].id
        f1 = self.building.floors_by_level[1].id
        s_start = list(self.building.spaces_by_floor[f0])[0].id
        s_end = list(self.building.spaces_by_floor[f1])[0].id

        # Baseline step-free route (must use elevator V02)
        r_stepfree = find_route(self.building, s_start, s_end, step_free=True)
        self.assertTrue(r_stepfree.success)

        # Close elevator
        closed = SESSION.get_closed_set(self.building.id)
        lift_id = "proc-factory-dev-003-V02"
        closed.add(lift_id)

        # Step-free route should now fail because no step-free path exists
        r_blocked = find_route(self.building, s_start, s_end, step_free=True, closed=closed)
        self.assertFalse(r_blocked.success)

        # Remove closure
        closed.discard(lift_id)
        r_restored = find_route(self.building, s_start, s_end, step_free=True, closed=closed)
        self.assertTrue(r_restored.success)

    def test_06_counterfactual_synthetic_door(self):
        f0 = self.building.floors_by_level[0].id
        spaces = self.building.spaces_by_floor[f0]
        # Find two adjacent spaces that do not currently have a direct door
        sp_a = spaces[0]
        sp_b = None
        for cand in spaces[1:]:
            dist = sp_a.polygon.distance(cand.polygon)
            if dist <= 0.6:
                sp_b = cand
                break

        if sp_b:
            new_door = SESSION.add_synthetic_door(sp_a.id, sp_b.id, width_m=1.0)
            self.assertIsNotNone(new_door)
            self.assertTrue(new_door.id in self.building.openings)
            self.assertTrue(new_door.synthetic)


class TestLiveHTTPServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Launch live server in background thread on ephemeral port
        cls.port = 8912
        cls.server_thread = threading.Thread(
            target=run_server,
            kwargs={"host": "127.0.0.1", "port": cls.port, "default_building": "proc-factory-dev-003"},
            daemon=True,
        )
        cls.server_thread.start()
        time.sleep(0.5)

    def test_01_get_index_html(self):
        url = f"http://127.0.0.1:{self.port}/"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode("utf-8")
            self.assertIn("Talk to Your Building", html)
            self.assertIn("scene3d-canvas", html)
            self.assertIn("slider-explode", html)

    def test_02_get_buildings_api(self):
        url = f"http://127.0.0.1:{self.port}/api/buildings"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("buildings", data)
            self.assertGreater(data["count"], 0)

    def test_03_get_building_state_api(self):
        url = f"http://127.0.0.1:{self.port}/api/building/state?building=proc-factory-dev-003"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("floors", data)
            self.assertIn("spaces", data)
            self.assertIn("openings", data)
            self.assertIn("vertical_connectors", data)
            self.assertIn("assets", data)
            self.assertEqual(data["building"]["id"], "proc-factory-dev-003")

    def test_04_post_route_api(self):
        url = f"http://127.0.0.1:{self.port}/api/route"
        payload = json.dumps({
            "start": "proc-factory-dev-003-F0-S001",
            "destination": "proc-factory-dev-003-F1-S001",
            "step_free": False,
            "min_width": 0.0
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertGreater(data["distance_m"], 0.0)
            self.assertTrue(len(data["waypoints"]) > 1)
            self.assertTrue(len(data["landmark_instructions"]) > 0)

    def test_05_post_incident_api(self):
        url = f"http://127.0.0.1:{self.port}/api/incident"
        payload = json.dumps({
            "action": "toggle",
            "target_id": "proc-factory-dev-003-V01",
            "reason": "Test inspection closure"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertIn("closed_elements", data)


if __name__ == "__main__":
    unittest.main()
