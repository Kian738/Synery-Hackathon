"""Comprehensive unit test suite for Milestone 1: Core Spatial Geometry & Reasoning Engine.

Tests data models, building loader, polygon areas, 3D Euclidean distances,
vertical stacking, and shared wall adjacency across dev buildings and synthetic cases.
Compatible with direct Python execution (`uv run python tests/unit/test_spatial_geometry.py`)
and standard test runners (`unittest`, `pytest`).
"""

import json
import math
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import Polygon

from spatial_engine import (
    Asset,
    AssetFootprint,
    Building,
    BuildingMetadata,
    Connector,
    Floor,
    Opening,
    Space,
    calculate_floor_area_total,
    calculate_room_area,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
    get_shared_boundary,
    get_shared_wall_spaces,
    is_point_in_space,
    is_valid_shared_wall_room,
    load_building,
    load_equipment_csv,
    resolve_floor,
)

DEV_DIR = Path("data/dev")
DEV_FACTORY_PATH = DEV_DIR / "proc-factory-dev-012"
OSM_BUILDING_PATH = DEV_DIR / "osm-way22744230"


def create_sample_building() -> Building:
    """Construct a clean synthetic 2-floor building for isolated unit tests."""
    meta = BuildingMetadata(
        id="test-bldg",
        name="Test Building",
        source="synthetic",
    )
    f0 = Floor(id="F0", level=0, name="Ground Floor", elevation_m=0.0, height_m=3.5)
    f1 = Floor(id="F1", level=1, name="First Floor", elevation_m=3.5, height_m=3.5)
    floors = {"F0": f0, "F1": f1}
    floors_by_level = {0: f0, 1: f1}

    # Floor 0: Two adjacent rooms + one corridor
    # Room 1: (0,0) to (10,10) -> area 100
    p1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    s1 = Space(
        id="S1",
        floor_id="F0",
        type="room",
        room_type="office",
        name="Office 1",
        ref="101",
        polygon_coords=[(0, 0), (10, 0), (10, 10), (0, 10)],
        polygon=p1,
        area=p1.area,
        centroid=(p1.centroid.x, p1.centroid.y),
        representative_point=(p1.representative_point().x, p1.representative_point().y),
        exterior_ring=p1.exterior,
    )

    # Room 2: (10,0) to (20,10) -> area 100, shares wall x=10 from y=0 to y=10 (length 10)
    p2 = Polygon([(10, 0), (20, 0), (20, 10), (10, 10)])
    s2 = Space(
        id="S2",
        floor_id="F0",
        type="room",
        room_type="office",
        name="Office 2",
        ref="102",
        polygon_coords=[(10, 0), (20, 0), (20, 10), (10, 10)],
        polygon=p2,
        area=p2.area,
        centroid=(p2.centroid.x, p2.centroid.y),
        representative_point=(p2.representative_point().x, p2.representative_point().y),
        exterior_ring=p2.exterior,
    )

    # Corridor: (0,10) to (20,12) -> adjacent to S1 and S2, but type="corridor"
    pc = Polygon([(0, 10), (20, 10), (20, 12), (0, 12)])
    sc = Space(
        id="SC",
        floor_id="F0",
        type="corridor",
        room_type="corridor",
        name="Corridor",
        ref="C0",
        polygon_coords=[(0, 10), (20, 10), (20, 12), (0, 12)],
        polygon=pc,
        area=pc.area,
        centroid=(pc.centroid.x, pc.centroid.y),
        representative_point=(pc.representative_point().x, pc.representative_point().y),
        exterior_ring=pc.exterior,
    )

    # Floor 1: Room stacked right above S1: (0,0) to (10,10)
    p_stack = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    s_stack = Space(
        id="S1_upper",
        floor_id="F1",
        type="room",
        room_type="conference",
        name="Conference Room",
        ref="201",
        polygon_coords=[(0, 0), (10, 0), (10, 10), (0, 10)],
        polygon=p_stack,
        area=p_stack.area,
        centroid=(p_stack.centroid.x, p_stack.centroid.y),
        representative_point=(
            p_stack.representative_point().x,
            p_stack.representative_point().y,
        ),
        exterior_ring=p_stack.exterior,
    )

    spaces = {"S1": s1, "S2": s2, "SC": sc, "S1_upper": s_stack}
    spaces_by_floor = {"F0": [s1, s2, sc], "F1": [s_stack]}
    spaces_by_floor_and_room_type = {
        ("F0", "office"): [s1, s2],
        ("F0", "corridor"): [sc],
        ("F1", "conference"): [s_stack],
    }

    # Opening between S1 and S2
    op = Opening(
        id="D1",
        floor_id="F0",
        space_ids=["S1", "S2"],
        kind="door",
        position=(10.0, 5.0),
        width_m=0.9,
        step_free=True,
    )
    # Exterior entrance into S1
    op_ext = Opening(
        id="D_EXT",
        floor_id="F0",
        space_ids=["outside", "S1"],
        kind="entrance",
        position=(0.0, 5.0),
        width_m=1.2,
        step_free=True,
    )
    openings = {"D1": op, "D_EXT": op_ext}
    openings_by_space = {"S1": [op, op_ext], "S2": [op]}
    openings_by_floor = {"F0": [op, op_ext]}

    # Stairs connecting F0 and F1
    conn = Connector(
        id="STAIRS1",
        kind="stairs",
        name="Main Stairs",
        floor_ids=["F0", "F1"],
        space_ids=["SC", "S1_upper"],
        step_free=False,
    )
    connectors = {"STAIRS1": conn}
    connectors_by_floor = {"F0": [conn], "F1": [conn]}

    # Asset in S1
    asset = Asset(
        id="A1",
        name="Work Desk",
        category="furniture",
        type="desk",
        space_id="S1",
        floor_id="F0",
        position=(3.0, 3.0),
        footprint=AssetFootprint(width_m=1.6, depth_m=0.8, rotation_deg=0.0),
    )
    assets = {"A1": asset}
    assets_by_space = {"S1": [asset]}
    assets_by_type = {"desk": [asset]}

    return Building(
        metadata=meta,
        floors=floors,
        spaces=spaces,
        openings=openings,
        connectors=connectors,
        assets=assets,
        floors_by_level=floors_by_level,
        spaces_by_floor=spaces_by_floor,
        spaces_by_floor_and_room_type=spaces_by_floor_and_room_type,
        openings_by_space=openings_by_space,
        openings_by_floor=openings_by_floor,
        connectors_by_floor=connectors_by_floor,
        assets_by_space=assets_by_space,
        assets_by_type=assets_by_type,
    )


class TestSyntheticSpatialGeometry(unittest.TestCase):
    """Test geometry functions on controlled synthetic models."""

    def setUp(self):
        self.building = create_sample_building()

    def test_calculate_room_area(self):
        s1 = self.building.get_space("S1")
        self.assertIsNotNone(s1)
        self.assertAlmostEqual(calculate_room_area(s1), 100.0, places=5)
        self.assertAlmostEqual(s1.area, 100.0, places=5)

    def test_calculate_floor_area_total(self):
        total_office = calculate_floor_area_total(self.building, "F0", "office")
        self.assertAlmostEqual(total_office, 200.0, places=5)

        total_by_level = calculate_floor_area_total(self.building, 0, "office")
        self.assertAlmostEqual(total_by_level, 200.0, places=5)

        total_missing = calculate_floor_area_total(self.building, "F0", "kitchen")
        self.assertEqual(total_missing, 0.0)

    def test_find_largest_room(self):
        largest, area = find_largest_room(self.building, "F0", "office")
        self.assertIn(largest.id, ("S1", "S2"))
        self.assertAlmostEqual(area, 100.0, places=5)

        with self.assertRaises(ValueError):
            find_largest_room(self.building, "F0", "nonexistent_room_type")

    def test_calculate_straight_line_3d(self):
        s1 = self.building.get_space("S1")
        s2 = self.building.get_space("S2")
        s_upper = self.building.get_space("S1_upper")

        # Identity distance (same room to itself)
        dist_self = calculate_straight_line_3d(s1, s1, self.building)
        self.assertAlmostEqual(dist_self, 0.0, places=5)

        # S1 (5, 5, 0) to S2 (15, 5, 0) -> distance = 10.0
        dist_same = calculate_straight_line_3d(s1, s2, self.building)
        self.assertAlmostEqual(dist_same, 10.0, places=5)

        # S1 (5, 5, 0) to S1_upper (5, 5, 3.5) -> distance = 3.5
        dist_vert = calculate_straight_line_3d(s1, s_upper, self.building)
        self.assertAlmostEqual(dist_vert, 3.5, places=5)

        # Diagonal distance
        dist_diag = calculate_straight_line_3d(s2, s_upper, self.building)
        expected_diag = math.sqrt(10.0**2 + 3.5**2)
        self.assertAlmostEqual(dist_diag, expected_diag, places=5)

    def test_find_stacked_room(self):
        s1 = self.building.get_space("S1")
        s_upper = self.building.get_space("S1_upper")

        stacked_up, overlap_up = find_stacked_room(s1, "above", self.building)
        self.assertEqual(stacked_up.id, "S1_upper")
        self.assertAlmostEqual(overlap_up, 100.0, places=5)

        stacked_down, overlap_down = find_stacked_room(s_upper, "below", self.building)
        self.assertEqual(stacked_down.id, "S1")
        self.assertAlmostEqual(overlap_down, 100.0, places=5)

        with self.assertRaises(ValueError):
            find_stacked_room(s_upper, "above", self.building)

        with self.assertRaises(ValueError):
            find_stacked_room(s1, "invalid_dir", self.building)

    def test_count_shared_walls(self):
        s1 = self.building.get_space("S1")
        sc = self.building.get_space("SC")
        self.assertTrue(is_valid_shared_wall_room(s1))
        self.assertFalse(is_valid_shared_wall_room(sc))
        # S1 shares wall with S2 (office) and SC (corridor).
        # Corridors must be excluded, only S2 counts!
        count = count_shared_walls(s1, self.building, min_length=1.0)
        self.assertEqual(count, 1)

        shared = get_shared_wall_spaces(s1, self.building, min_length=1.0)
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0][0].id, "S2")
        self.assertGreaterEqual(shared[0][1], 9.9)

        # High min_length
        self.assertEqual(count_shared_walls(s1, self.building, min_length=50.0), 0)

    def test_point_in_space_and_boundary(self):
        s1 = self.building.get_space("S1")
        s2 = self.building.get_space("S2")

        self.assertTrue(is_point_in_space(s1, (5.0, 5.0)))
        self.assertTrue(is_point_in_space(s1, (10.0, 5.0)))
        self.assertFalse(is_point_in_space(s1, (15.0, 5.0)))

        boundary_len = get_shared_boundary(s1, s2, buffer_dist=0.35)
        self.assertGreaterEqual(boundary_len, 9.9)

    def test_opening_and_connector_helpers(self):
        d1 = self.building.openings["D1"]
        self.assertFalse(d1.is_entrance)
        self.assertEqual(d1.other_side("S1"), "S2")
        self.assertEqual(d1.other_side("S2"), "S1")

        d_ext = self.building.openings["D_EXT"]
        self.assertTrue(d_ext.is_entrance)
        self.assertEqual(d_ext.other_side("outside"), "S1")

        conn = self.building.connectors["STAIRS1"]
        self.assertTrue(conn.is_stairs)
        self.assertFalse(conn.is_lift)

    def test_space_queries_and_lookups(self):
        b = self.building
        offices = b.find_spaces(floor_id="F0", room_type="office")
        self.assertEqual(len(offices), 2)

        s1_by_ref = b.find_space_by_ref_or_name("101")
        self.assertIsNotNone(s1_by_ref)
        self.assertEqual(s1_by_ref.id, "S1")

        s1_by_name = b.find_space_by_ref_or_name("Office 1")
        self.assertIsNotNone(s1_by_name)
        self.assertEqual(s1_by_name.id, "S1")

    def test_resolve_floor(self):
        self.assertEqual(resolve_floor(self.building, "F0").id, "F0")
        self.assertEqual(resolve_floor(self.building, 0).id, "F0")
        self.assertEqual(resolve_floor(self.building, "0").id, "F0")
        self.assertEqual(resolve_floor(self.building, "Ground Floor").id, "F0")
        self.assertEqual(resolve_floor(self.building, "ground floor").id, "F0")

        with self.assertRaises(ValueError):
            resolve_floor(self.building, "Basement Level 99")


class TestDevBuildingGeometry(unittest.TestCase):
    """Verifies geometry functions against ground truth benchmark data on proc-factory-dev-012."""

    @classmethod
    def setUpClass(cls):
        if not DEV_FACTORY_PATH.exists():
            raise unittest.SkipTest("Dev factory dataset not found")
        cls.factory_building = load_building(DEV_FACTORY_PATH)

    def test_building_loaded_structure(self):
        b = self.factory_building
        self.assertEqual(b.id, "proc-factory-dev-012")
        self.assertEqual(len(b.floors), 3)
        self.assertGreater(len(b.spaces), 30)
        self.assertGreater(len(b.openings), 20)
        self.assertGreater(len(b.connectors), 0)
        self.assertGreater(len(b.assets), 0)

        self.assertIn(0, b.floors_by_level)
        self.assertIn(1, b.floors_by_level)
        self.assertIn(2, b.floors_by_level)

    def test_question_h01_largest_room(self):
        """Dev question H01: largest kitchen on ground floor -> Kitchen 0.30, 28.2 m²."""
        f0_id = "proc-factory-dev-012-F0"
        largest_kitchen, area = find_largest_room(
            self.factory_building, f0_id, room_type="kitchen"
        )
        self.assertEqual(largest_kitchen.id, "proc-factory-dev-012-F0-S030")
        self.assertTrue("0.30" in largest_kitchen.ref or "0.30" in largest_kitchen.name)
        self.assertEqual(round(area, 1), 28.2)
        self.assertLessEqual(abs(area - 28.2), 0.05 * 28.2)

    def test_question_h02_floor_area_total(self):
        """Dev question H02: total floor area of every kitchen on floor 1 -> 106.3 m²."""
        f1_id = "proc-factory-dev-012-F1"
        total_area = calculate_floor_area_total(
            self.factory_building, f1_id, room_type="kitchen"
        )
        self.assertEqual(round(total_area, 1), 106.3)
        self.assertLessEqual(abs(total_area - 106.3), 0.05 * 106.3)

    def test_question_h05_shared_walls_count(self):
        """Dev question H05: Office 0.34 shared walls count -> 4."""
        target_id = "proc-factory-dev-012-F0-S034"
        target_space = self.factory_building.get_space(target_id)
        self.assertIsNotNone(target_space)

        shared_count = count_shared_walls(target_space, self.factory_building)
        self.assertEqual(shared_count, 4)

        shared_spaces = get_shared_wall_spaces(target_space, self.factory_building)
        self.assertEqual(len(shared_spaces), 4)
        for s, _ in shared_spaces:
            self.assertNotIn(s.type, ("corridor", "stair", "lift", "outdoor"))
            self.assertNotIn(s.room_type, ("corridor", "stairwell", "lift", "balcony"))

    def test_question_h06_straight_line_3d(self):
        """Dev question H06: Office 2.35 and Office 0.37 straight-line distance -> 27.37 m."""
        s1 = self.factory_building.get_space("proc-factory-dev-012-F2-S035")
        s2 = self.factory_building.get_space("proc-factory-dev-012-F0-S037")
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)

        dist = calculate_straight_line_3d(s1, s2, self.factory_building)
        self.assertEqual(round(dist, 2), 27.37)
        self.assertLessEqual(abs(dist - 27.37), 0.02 * 27.37)

    def test_load_building_from_file_path(self):
        json_file = DEV_FACTORY_PATH / "building.json"
        bldg = load_building(json_file)
        self.assertEqual(bldg.id, "proc-factory-dev-012")
        self.assertGreater(len(bldg.spaces), 0)

    def test_load_equipment_csv(self):
        csv_file = DEV_FACTORY_PATH / "equipment.csv"
        assets = load_equipment_csv(csv_file)
        self.assertGreater(len(assets), 0)
        a0 = assets[0]
        self.assertTrue(a0.id.startswith("proc-factory-dev-012-A"))


class TestOSMBuildingStacking(unittest.TestCase):
    """Verifies vertical stacking overlap calculations on OSM building osm-way22744230."""

    @classmethod
    def setUpClass(cls):
        if not OSM_BUILDING_PATH.exists():
            raise unittest.SkipTest("OSM dev building dataset not found")
        cls.osm_building = load_building(OSM_BUILDING_PATH)

    def test_question_h05_room_stacked_below(self):
        """Dev question H05: room N2324 (Floor 2) leaking onto floor below -> N1318 (Floor 1)."""
        start_id = "osm-way22744230-F2-S012"
        start_space = self.osm_building.get_space(start_id)
        self.assertIsNotNone(start_space)

        stacked_room, overlap_area = find_stacked_room(
            start_space, "below", self.osm_building
        )
        self.assertEqual(stacked_room.id, "osm-way22744230-F1-S026")
        self.assertTrue("N1318" in stacked_room.ref or "N1318" in stacked_room.name)
        self.assertGreater(overlap_area, 5.0)

    def test_question_h06_room_stacked_below(self):
        """Dev question H06: room N1316 (Floor 1) leaking onto floor below -> N0309 (Floor 0)."""
        start_id = "osm-way22744230-F1-S002"
        start_space = self.osm_building.get_space(start_id)
        self.assertIsNotNone(start_space)

        stacked_room, overlap_area = find_stacked_room(
            start_space, "below", self.osm_building
        )
        self.assertEqual(stacked_room.id, "osm-way22744230-F0-S005")
        self.assertTrue("N0309" in stacked_room.ref or "N0309" in stacked_room.name)
        self.assertGreater(overlap_area, 5.0)


class TestDevDatasetExhaustiveGeometry(unittest.TestCase):
    """Exhaustively validates all geometry questions across all buildings in data/dev."""

    @classmethod
    def setUpClass(cls):
        if not DEV_DIR.exists():
            raise unittest.SkipTest("data/dev not found")

    def test_all_dev_shared_walls_questions(self):
        """Verifies 100% accuracy on all 24 shared_walls_count questions in dev."""
        checked = 0
        for qfile in sorted(DEV_DIR.glob("*/questions.jsonl")):
            building = load_building(qfile.parent)
            with open(qfile, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    q = json.loads(line)
                    if q.get("kind") != "shared_walls_count":
                        continue
                    start_space = building.get_space(q["inputs"]["start"])
                    self.assertIsNotNone(start_space)
                    calc_count = count_shared_walls(start_space, building)
                    expected = int(q["answer"]["value"])
                    self.assertEqual(
                        calc_count,
                        expected,
                        f"Mismatch in question {q['id']} for {building.id}",
                    )
                    checked += 1
        self.assertEqual(checked, 24)

    def test_all_dev_straight_line_3d_questions(self):
        """Verifies 100% accuracy on all 13 straight_line_3d questions in dev within 2% tolerance."""
        checked = 0
        for qfile in sorted(DEV_DIR.glob("*/questions.jsonl")):
            building = load_building(qfile.parent)
            with open(qfile, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    q = json.loads(line)
                    if q.get("kind") != "straight_line_3d":
                        continue
                    s1 = building.get_space(q["inputs"]["first"])
                    s2 = building.get_space(q["inputs"]["second"])
                    self.assertIsNotNone(s1)
                    self.assertIsNotNone(s2)
                    dist = calculate_straight_line_3d(s1, s2, building)
                    expected = float(q["answer"]["value"])
                    tol = max(0.02 * expected, 0.0)
                    self.assertLessEqual(
                        abs(dist - expected),
                        tol + 1e-4,
                        f"3D dist mismatch in {q['id']}: got {dist}, expected {expected}",
                    )
                    checked += 1
        self.assertEqual(checked, 13)

    def test_all_dev_largest_room_questions(self):
        """Verifies 100% accuracy on all 20 largest_room questions in dev within 5% tolerance."""
        checked = 0
        for qfile in sorted(DEV_DIR.glob("*/questions.jsonl")):
            building = load_building(qfile.parent)
            with open(qfile, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    q = json.loads(line)
                    if q.get("kind") != "largest_room":
                        continue
                    fid = q["inputs"]["floor_id"]
                    rtype = q["inputs"]["room_type"]
                    best_space, area = find_largest_room(building, fid, rtype)
                    exp_space_id = q["answer"]["space_id"]
                    self.assertEqual(
                        best_space.id,
                        exp_space_id,
                        f"Largest room mismatch in {q['id']}",
                    )
                    exp_area = float(q["answer"]["area"]["value"])
                    self.assertLessEqual(
                        abs(area - exp_area),
                        0.05 * exp_area + 0.05,
                        f"Area tolerance mismatch in {q['id']}",
                    )
                    checked += 1
        self.assertEqual(checked, 20)

    def test_all_dev_floor_area_total_questions(self):
        """Verifies 100% accuracy on all 31 floor_area_total questions in dev within 5% tolerance."""
        checked = 0
        for qfile in sorted(DEV_DIR.glob("*/questions.jsonl")):
            building = load_building(qfile.parent)
            with open(qfile, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    q = json.loads(line)
                    if q.get("kind") != "floor_area_total":
                        continue
                    fid = q["inputs"]["floor_id"]
                    rtype = q["inputs"]["room_type"]
                    total = calculate_floor_area_total(building, fid, rtype)
                    exp_val = float(q["answer"]["value"])
                    self.assertLessEqual(
                        abs(total - exp_val),
                        0.05 * exp_val + 0.05,
                        f"Total area mismatch in {q['id']}",
                    )
                    checked += 1
        self.assertEqual(checked, 31)

    def test_all_dev_room_stacked_questions(self):
        """Verifies 100% accuracy on all 9 room_stacked questions in dev."""
        checked = 0
        for qfile in sorted(DEV_DIR.glob("*/questions.jsonl")):
            building = load_building(qfile.parent)
            with open(qfile, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    q = json.loads(line)
                    if q.get("kind") != "room_stacked":
                        continue
                    start = building.get_space(q["inputs"]["start"])
                    self.assertIsNotNone(start)
                    direction = q["inputs"]["direction"]
                    stacked, overlap = find_stacked_room(start, direction, building)
                    exp_space_id = q["answer"]["space_id"]
                    self.assertEqual(
                        stacked.id,
                        exp_space_id,
                        f"Stacked room mismatch in {q['id']}",
                    )
                    checked += 1
        self.assertEqual(checked, 9)


class TestMilestone1Remediation(unittest.TestCase):
    """Regression and adversarial tests covering Milestone 1 defect remediation."""

    def test_make_valid_geometry_collection_and_degenerate_loader(self):
        """Verify loader handles pinch points, antenna spikes, and collinear points without crash."""
        cases = [
            ("pinch", [(0, 0), (10, 0), (10, 10), (5, 5), (0, 10), (5, 5)]),
            ("spike", [(0, 0), (5, 0), (5, 5), (10, 5), (5, 5), (0, 5)]),
            ("collinear", [(0, 0), (5, 5), (10, 10)]),
        ]
        for name, coords in cases:
            bldg_data = {
                "building": {"id": f"{name}-bldg", "name": f"{name.capitalize()} Test"},
                "floors": [{"id": "F0", "level": 0, "name": "Ground", "elevation_m": 0.0}],
                "spaces": [
                    {
                        "id": f"S_{name.upper()}",
                        "floor_id": "F0",
                        "type": "room",
                        "room_type": "storage",
                        "name": f"{name.capitalize()} Room",
                        "polygon": coords,
                    }
                ],
            }
            with tempfile.TemporaryDirectory() as tmpdir:
                json_path = Path(tmpdir) / "building.json"
                json_path.write_text(json.dumps(bldg_data), encoding="utf-8")
                b = load_building(json_path)
                s = b.spaces[f"S_{name.upper()}"]
                self.assertIsNotNone(s.exterior_ring)
                self.assertTrue(hasattr(s.exterior_ring, "coords"))
                self.assertGreater(s.area, 0.0)

    def test_find_stacked_room_zero_overlap_raises_value_error(self):
        """Verify disjoint floors with zero overlap raise ValueError instead of false match."""
        f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
        f1 = Floor(id="F1", level=1, name="First", elevation_m=3.0, height_m=3.0)
        p0 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        s0 = Space(id="S0", floor_id="F0", type="room", room_type="office", name="Base", ref="",
                   polygon_coords=[], polygon=p0, area=100.0, centroid=(5, 5),
                   representative_point=(5, 5), exterior_ring=p0.exterior)
        p1 = Polygon([(1000, 1000), (1010, 1000), (1010, 1010), (1000, 1010)])
        s1 = Space(id="S1_DISJOINT", floor_id="F1", type="room", room_type="office", name="Disjoint 1", ref="",
                   polygon_coords=[], polygon=p1, area=100.0, centroid=(1005, 1005),
                   representative_point=(1005, 1005), exterior_ring=p1.exterior)
        b = Building(
            metadata=BuildingMetadata(id="test", name="test", source=""),
            floors={"F0": f0, "F1": f1},
            spaces={"S0": s0, "S1_DISJOINT": s1},
            openings={}, connectors={}, assets={},
            floors_by_level={0: f0, 1: f1},
            spaces_by_floor={"F0": [s0], "F1": [s1]},
            spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
            connectors_by_floor={}, assets_by_space={}, assets_by_type={},
        )
        with self.assertRaises(ValueError):
            find_stacked_room(s0, "above", b)

    def test_shared_wall_buffer_dilation_sensitivity(self):
        """Verify 0.99m wall overlap is not counted as >= 1.0m, but 1.01m is counted."""
        f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
        p_a = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        s_a = Space(id="S_A", floor_id="F0", type="room", room_type="office", name="Room A", ref="",
                    polygon_coords=[], polygon=p_a, area=100.0, centroid=(5, 5),
                    representative_point=(5, 5), exterior_ring=p_a.exterior)

        def make_bldg(cand_coords):
            p_c = Polygon(cand_coords)
            s_c = Space(id="S_C", floor_id="F0", type="room", room_type="office", name="Cand", ref="",
                        polygon_coords=[], polygon=p_c, area=p_c.area,
                        centroid=(p_c.centroid.x, p_c.centroid.y),
                        representative_point=(p_c.representative_point().x, p_c.representative_point().y),
                        exterior_ring=p_c.exterior)
            return Building(
                metadata=BuildingMetadata(id="test", name="test", source=""),
                floors={"F0": f0}, spaces={"S_A": s_a, "S_C": s_c},
                openings={}, connectors={}, assets={},
                floors_by_level={0: f0}, spaces_by_floor={"F0": [s_a, s_c]},
                spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
                connectors_by_floor={}, assets_by_space={}, assets_by_type={},
            ), s_c

        # 0.99m overlap should NOT count
        b_099, sc_099 = make_bldg([(10, 2.0), (20, 2.0), (20, 2.99), (10, 2.99)])
        self.assertEqual(count_shared_walls(s_a, b_099, min_length=1.0), 0)
        self.assertAlmostEqual(get_shared_boundary(s_a, sc_099), 0.99, places=2)

        # 1.01m overlap SHOULD count
        b_101, sc_101 = make_bldg([(10, 2.0), (20, 2.0), (20, 3.01), (10, 3.01)])
        self.assertEqual(count_shared_walls(s_a, b_101, min_length=1.0), 1)
        self.assertAlmostEqual(get_shared_boundary(s_a, sc_101), 1.01, places=2)

        # 0.2m gap with 0.99m parallel wall should NOT count
        b_gap, sc_gap = make_bldg([(10.2, 2.0), (20.0, 2.0), (20.0, 2.99), (10.2, 2.99)])
        self.assertEqual(count_shared_walls(s_a, b_gap, min_length=1.0), 0)
        self.assertAlmostEqual(get_shared_boundary(s_a, sc_gap), 0.99, places=2)

    def test_find_space_by_ref_or_name_direct_space_id(self):
        """Verify direct space ID lookup in find_space_by_ref_or_name."""
        f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
        p = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        s = Space(id="SPACE_XYZ_123", floor_id="F0", type="room", room_type="office",
                  name="Custom Room Name", ref="REF99", polygon_coords=[], polygon=p,
                  area=100.0, centroid=(5, 5), representative_point=(5, 5), exterior_ring=p.exterior)
        b = Building(
            metadata=BuildingMetadata(id="test", name="test", source=""),
            floors={"F0": f0}, spaces={"SPACE_XYZ_123": s},
            openings={}, connectors={}, assets={},
            floors_by_level={0: f0}, spaces_by_floor={"F0": [s]},
            spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
            connectors_by_floor={}, assets_by_space={}, assets_by_type={},
        )
        self.assertIs(b.find_space_by_ref_or_name("SPACE_XYZ_123"), s)
        self.assertIs(b.find_space_by_ref_or_name("SPACE_XYZ_123", floor_id="F0"), s)
        self.assertIsNone(b.find_space_by_ref_or_name("SPACE_XYZ_123", floor_id="F1"))


if __name__ == "__main__":
    unittest.main()
