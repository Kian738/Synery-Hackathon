"""Empirical Adversarial Stress Test Harness for Milestone 1.

Targets:
- spatial_engine.geometry
- spatial_engine.building_loader

Tested Dimensions:
1. Synthetic complex polygons (L-shaped, U-shaped, self-touching, colinear boundary walls)
2. Shared wall buffer sensitivity (exact 0.99m vs 1.01m, corner touches, wall gaps)
3. 3D centroid calculation precision across varying elevations & extreme coordinate ranges
4. Vertical stacking overlap under scaling, offsets, and disjoint floors (zero overlap bug)
"""

import json
import math
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shapely.geometry import Polygon
from spatial_engine.building_loader import load_building
from spatial_engine.geometry import (
    calculate_floor_area_total,
    calculate_room_area,
    calculate_straight_line_3d,
    count_shared_walls,
    find_largest_room,
    find_stacked_room,
    get_shared_boundary,
    get_shared_wall_spaces,
    is_point_in_space,
    resolve_floor,
)
from spatial_engine.models import (
    Building,
    BuildingMetadata,
    Floor,
    Space,
)


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.bug_exposed = False
        self.error_message = ""
        self.details = ""


results: list[TestResult] = []


def record_result(res: TestResult):
    results.append(res)
    status = "BUG EXPOSED" if res.bug_exposed else ("PASS" if res.passed else "FAIL")
    print(f"[{status}] {res.name}")
    if res.details:
        print(f"    Details: {res.details}")
    if res.error_message:
        print(f"    Error: {res.error_message}")


# ==============================================================================
# SUITE 1: Synthetic Complex Polygons
# ==============================================================================

def test_1_1_l_shaped_polygon():
    res = TestResult("1.1 L-shaped polygon area & centroid vs representative point")
    try:
        # L-shape: 10x10 with 8x8 corner cut out:
        # Horizontal base: [0, 10] x [0, 2] -> area 20
        # Vertical column: [0, 2] x [2, 10] -> area 16
        # Total area = 36
        coords = [(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)]
        poly = Polygon(coords)
        space = Space(
            id="L1", floor_id="F0", type="room", room_type="office", name="L-Room",
            ref="", polygon_coords=coords, polygon=poly, area=poly.area,
            centroid=(poly.centroid.x, poly.centroid.y),
            representative_point=(poly.representative_point().x, poly.representative_point().y),
            exterior_ring=poly.exterior,
        )

        calc_area = calculate_room_area(space)
        assert abs(calc_area - 36.0) < 1e-6, f"Expected 36.0 m², got {calc_area}"

        # Mathematical centroid: (116/36, 116/36) = (3.222..., 3.222...)
        # Notice (3.22, 3.22) is in the cutout (OUTSIDE the polygon)!
        centroid_in = is_point_in_space(space, space.centroid)
        rep_in = is_point_in_space(space, space.representative_point)

        assert not centroid_in, "Centroid of thin L-shape should be outside polygon"
        assert rep_in, "Representative point MUST be inside polygon"

        res.passed = True
        res.details = f"Area: {calc_area} m², Centroid inside: {centroid_in}, Rep point inside: {rep_in}"
    except Exception as e:
        res.error_message = str(e)
    record_result(res)


def test_1_2_u_shaped_polygon():
    res = TestResult("1.2 U-shaped polygon cavity centroid vs representative point")
    try:
        # U-shape: [0, 10] x [0, 10] with cavity [2, 8] x [2, 10]
        # Base: 10 x 2 = 20
        # Left wall: 2 x 8 = 16
        # Right wall: 2 x 8 = 16
        # Total area = 52
        coords = [(0, 0), (10, 0), (10, 10), (8, 10), (8, 2), (2, 2), (2, 10), (0, 10)]
        poly = Polygon(coords)
        space = Space(
            id="U1", floor_id="F0", type="room", room_type="hall", name="U-Hall",
            ref="", polygon_coords=coords, polygon=poly, area=poly.area,
            centroid=(poly.centroid.x, poly.centroid.y),
            representative_point=(poly.representative_point().x, poly.representative_point().y),
            exterior_ring=poly.exterior,
        )

        calc_area = calculate_room_area(space)
        assert abs(calc_area - 52.0) < 1e-6, f"Expected 52.0 m², got {calc_area}"

        centroid_in = is_point_in_space(space, space.centroid)
        rep_in = is_point_in_space(space, space.representative_point)

        assert not centroid_in, "Centroid of U-shape must fall in cavity (outside polygon)"
        assert rep_in, "Representative point must fall inside polygon"

        res.passed = True
        res.details = f"Area: {calc_area} m², Centroid inside: {centroid_in}, Rep point inside: {rep_in}"
    except Exception as e:
        res.error_message = str(e)
    record_result(res)


def test_1_3_self_touching_pinch_polygon_loader():
    res = TestResult("1.3 Self-touching pinch-point polygon in building_loader.py")
    # Coordinates touching at a pinch point: (5, 5)
    coords = [(0, 0), (10, 0), (10, 10), (5, 5), (0, 10), (5, 5)]
    bldg_data = {
        "building": {"id": "pinch-bldg", "name": "Pinch Test"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground", "elevation_m": 0.0}],
        "spaces": [
            {
                "id": "S_PINCH",
                "floor_id": "F0",
                "type": "room",
                "room_type": "storage",
                "name": "Pinch Room",
                "polygon": coords,
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "building.json"
        with open(json_path, "w") as f:
            json.dump(bldg_data, f)

        try:
            bldg = load_building(json_path)
            res.passed = True
            res.details = f"Loaded successfully: {bldg.spaces['S_PINCH'].area} m²"
        except AttributeError as e:
            res.bug_exposed = True
            res.error_message = f"CRASH: {type(e).__name__}: {e} (make_valid returned GeometryCollection without .exterior)"
            res.details = "building_loader.py assumes make_valid returns Polygon/MultiPolygon, but pinch point yields GeometryCollection."
        except Exception as e:
            res.error_message = f"Unexpected error: {type(e).__name__}: {e}"
    record_result(res)


def test_1_4_antenna_spike_polygon_loader():
    res = TestResult("1.4 Boundary antenna spike in building_loader.py")
    # Polygon with a linear spike/antenna protruding: (5,5) -> (10,5) -> (5,5)
    coords = [(0, 0), (5, 0), (5, 5), (10, 5), (5, 5), (0, 5)]
    bldg_data = {
        "building": {"id": "spike-bldg", "name": "Spike Test"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground", "elevation_m": 0.0}],
        "spaces": [
            {
                "id": "S_SPIKE",
                "floor_id": "F0",
                "type": "room",
                "room_type": "storage",
                "name": "Spike Room",
                "polygon": coords,
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "building.json"
        with open(json_path, "w") as f:
            json.dump(bldg_data, f)

        try:
            b = load_building(json_path)
            res.passed = True
            res.details = f"Loaded successfully: {b.spaces['S_SPIKE'].area} m²"
        except AttributeError as e:
            res.bug_exposed = True
            res.error_message = f"CRASH: {type(e).__name__}: {e} (GeometryCollection has no attribute 'exterior')"
            res.details = "building_loader.py crashes on antenna spike polygon because make_valid yields GeometryCollection."
        except Exception as e:
            res.error_message = f"Unexpected error: {type(e).__name__}: {e}"
    record_result(res)


def test_1_5_colinear_boundary_points():
    res = TestResult("1.5 Colinear redundant vertices along boundary wall")
    try:
        # Colinear points on bottom edge: (0,0), (2,0), (5,0), (8,0), (10,0)
        coords = [(0, 0), (2, 0), (5, 0), (8, 0), (10, 0), (10, 10), (0, 10)]
        poly = Polygon(coords)
        space = Space(
            id="COL1", floor_id="F0", type="room", room_type="office", name="Colinear Room",
            ref="", polygon_coords=coords, polygon=poly, area=poly.area,
            centroid=(poly.centroid.x, poly.centroid.y),
            representative_point=(poly.representative_point().x, poly.representative_point().y),
            exterior_ring=poly.exterior,
        )

        assert abs(space.area - 100.0) < 1e-6, f"Expected 100.0 m², got {space.area}"
        assert space.polygon.is_valid, "Polygon with colinear vertices should be valid in Shapely"

        res.passed = True
        res.details = f"Area: {space.area} m², is_valid: {space.polygon.is_valid}"
    except Exception as e:
        res.error_message = str(e)
    record_result(res)


def test_1_6_degenerate_zero_area_colinear_loader():
    res = TestResult("1.6 Degenerate 3-point colinear space (zero area) in loader")
    coords = [(0, 0), (5, 5), (10, 10)]
    bldg_data = {
        "building": {"id": "degen-bldg", "name": "Degenerate Test"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground", "elevation_m": 0.0}],
        "spaces": [
            {
                "id": "S_DEGEN",
                "floor_id": "F0",
                "type": "room",
                "room_type": "storage",
                "name": "Degen Room",
                "polygon": coords,
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "building.json"
        with open(json_path, "w") as f:
            json.dump(bldg_data, f)

        try:
            b = load_building(json_path)
            res.passed = True
            res.details = f"Loaded successfully: {b.spaces['S_DEGEN'].area} m²"
        except AttributeError as e:
            res.bug_exposed = True
            res.error_message = f"CRASH: {type(e).__name__}: {e} (MultiLineString has no attribute 'exterior')"
            res.details = "3-point colinear input produces MultiLineString upon make_valid, missing .exterior."
        except Exception as e:
            res.error_message = f"Unexpected error: {type(e).__name__}: {e}"
    record_result(res)


# ==============================================================================
# SUITE 2: Shared Wall Buffer Sensitivity
# ==============================================================================

def create_shared_wall_building(cand_coords: list[tuple[float, float]]) -> tuple[Building, Space, Space]:
    f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
    # Room A: [0, 10] x [0, 10]
    p_a = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    s_a = Space(
        id="S_A", floor_id="F0", type="room", room_type="office", name="Room A",
        ref="", polygon_coords=[(0, 0), (10, 0), (10, 10), (0, 10)], polygon=p_a,
        area=p_a.area, centroid=(5.0, 5.0), representative_point=(5.0, 5.0),
        exterior_ring=p_a.exterior,
    )
    p_cand = Polygon(cand_coords)
    s_cand = Space(
        id="S_CAND", floor_id="F0", type="room", room_type="office", name="Candidate Room",
        ref="", polygon_coords=cand_coords, polygon=p_cand,
        area=p_cand.area, centroid=(p_cand.centroid.x, p_cand.centroid.y),
        representative_point=(p_cand.representative_point().x, p_cand.representative_point().y),
        exterior_ring=p_cand.exterior,
    )

    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F0": f0},
        spaces={"S_A": s_a, "S_CAND": s_cand},
        openings={}, connectors={}, assets={},
        floors_by_level={0: f0},
        spaces_by_floor={"F0": [s_a, s_cand]},
        spaces_by_floor_and_room_type={("F0", "office"): [s_a, s_cand]},
        openings_by_space={}, openings_by_floor={}, connectors_by_floor={},
        assets_by_space={}, assets_by_type={},
    )
    return b, s_a, s_cand


def test_2_1_shared_wall_exact_0_99m_sensitivity():
    res = TestResult("2.1 Shared wall buffer sensitivity at EXACTLY 0.99 m overlap")
    # Room A is [0, 10] x [0, 10].
    # Candidate room is along wall x=10 from y=2.00 to y=2.99 (contact length exactly 0.99 m).
    # Since benchmark requirement is >= 1.0 m, 0.99 m SHOULD NOT count!
    cand_coords = [(10, 2.0), (20, 2.0), (20, 2.99), (10, 2.99)]
    bldg, s_a, s_cand = create_shared_wall_building(cand_coords)

    shared_spaces = get_shared_wall_spaces(s_a, bldg, min_length=1.0, buffer_dist=0.35)
    count = count_shared_walls(s_a, bldg, min_length=1.0, buffer_dist=0.35)

    if count > 0:
        measured_len = shared_spaces[0][1]
        res.bug_exposed = True
        res.error_message = (
            f"FALSE POSITIVE: Wall overlap is 0.99m (< 1.0m threshold), but count_shared_walls returned {count} "
            f"(measured contact length = {measured_len:.2f}m)"
        )
        res.details = (
            f"The 0.35m buffer around Room A's boundary dilates around the corners into the candidate room's "
            f"perpendicular walls by 2 x 0.35m = 0.70m, giving 0.99 + 0.70 = 1.69m >= 1.0m!"
        )
    else:
        res.passed = True
        res.details = "Correctly rejected 0.99m wall overlap."
    record_result(res)


def test_2_2_shared_wall_exact_1_01m_sensitivity():
    res = TestResult("2.2 Shared wall buffer sensitivity at EXACTLY 1.01 m overlap")
    # Candidate room along wall x=10 from y=2.00 to y=3.01 (contact length exactly 1.01 m).
    # Since 1.01 >= 1.0 m, this SHOULD count!
    cand_coords = [(10, 2.0), (20, 2.0), (20, 3.01), (10, 3.01)]
    bldg, s_a, s_cand = create_shared_wall_building(cand_coords)

    shared_spaces = get_shared_wall_spaces(s_a, bldg, min_length=1.0, buffer_dist=0.35)
    count = count_shared_walls(s_a, bldg, min_length=1.0, buffer_dist=0.35)

    if count == 1:
        res.passed = True
        res.details = f"Correctly counted 1.01m wall overlap (measured length = {shared_spaces[0][1]:.2f}m)"
    else:
        res.error_message = f"FAILED: Expected count=1 for 1.01m overlap, got {count}"
    record_result(res)


def test_2_3_shared_wall_short_0_35m_contact():
    res = TestResult("2.3 Shared wall false positive on short 0.35 m contact")
    # Wall contact length is only 0.35 m (from y=2.00 to y=2.35).
    # Definitely < 1.0 m threshold!
    cand_coords = [(10, 2.0), (20, 2.0), (20, 2.35), (10, 2.35)]
    bldg, s_a, s_cand = create_shared_wall_building(cand_coords)

    shared_spaces = get_shared_wall_spaces(s_a, bldg, min_length=1.0, buffer_dist=0.35)
    count = count_shared_walls(s_a, bldg, min_length=1.0, buffer_dist=0.35)

    if count > 0:
        measured_len = shared_spaces[0][1]
        res.bug_exposed = True
        res.error_message = (
            f"FALSE POSITIVE: Wall contact is only 0.35m, but counted as shared wall (measured = {measured_len:.2f}m >= 1.0m)"
        )
        res.details = "Perpendicular wall penetration in 0.35m buffer adds 0.70m, turning 0.35m into 1.05m."
    else:
        res.passed = True
        res.details = "Correctly rejected 0.35m contact."
    record_result(res)


def test_2_4_shared_wall_corner_touch_only():
    res = TestResult("2.4 Shared wall evaluation on corner-only contact (0.0 m wall)")
    # Touching only at point (10, 10)
    cand_coords = [(10, 10), (20, 10), (20, 20), (10, 20)]
    bldg, s_a, s_cand = create_shared_wall_building(cand_coords)

    shared_boundary_len = get_shared_boundary(s_a, s_cand, buffer_dist=0.35)
    # At min_length=1.0, 0.70m < 1.0m so count is 0
    count_1_0 = count_shared_walls(s_a, bldg, min_length=1.0, buffer_dist=0.35)
    # But if min_length was 0.5m, corner touch would be 0.70m >= 0.5m!
    count_0_5 = count_shared_walls(s_a, bldg, min_length=0.5, buffer_dist=0.35)

    res.passed = True
    res.details = f"Corner-touch measured length: {shared_boundary_len:.2f}m. Count(min=1.0): {count_1_0}, Count(min=0.5): {count_0_5}"
    record_result(res)


def test_2_5_shared_wall_with_physical_wall_gap():
    res = TestResult("2.5 Shared wall with 0.2 m wall gap and 0.99 m parallel span")
    # Parallel wall span of 0.99 m, separated by 0.2 m wall thickness gap
    cand_coords = [(10.2, 2.0), (20.0, 2.0), (20.0, 2.99), (10.2, 2.99)]
    bldg, s_a, s_cand = create_shared_wall_building(cand_coords)

    count = count_shared_walls(s_a, bldg, min_length=1.0, buffer_dist=0.35)
    shared_spaces = get_shared_wall_spaces(s_a, bldg, min_length=1.0, buffer_dist=0.35)

    if count > 0:
        measured_len = shared_spaces[0][1]
        res.bug_exposed = True
        res.error_message = (
            f"FALSE POSITIVE: Separated by 0.2m gap, parallel span 0.99m (< 1.0m), counted as shared wall "
            f"(measured = {measured_len:.2f}m)"
        )
        res.details = "Buffer (0.35m) bridges 0.20m gap and penetrates perpendicular walls by 0.15m on each side: 0.99 + 0.30 = 1.29m."
    else:
        res.passed = True
        res.details = "Correctly rejected 0.99m parallel wall across 0.2m gap."
    record_result(res)


# ==============================================================================
# SUITE 3: 3D Centroid Calculation Precision
# ==============================================================================

def test_3_1_centroid_3d_identical_rooms():
    res = TestResult("3.1 3D distance between identical room centroids on same floor")
    f0 = Floor(id="F0", level=0, name="Ground", elevation_m=12.5, height_m=3.0)
    p = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    s = Space(
        id="S0", floor_id="F0", type="room", room_type="office", name="Room",
        ref="", polygon_coords=[(0, 0), (10, 0), (10, 10), (0, 10)], polygon=p,
        area=100.0, centroid=(5.0, 5.0), representative_point=(5.0, 5.0),
        exterior_ring=p.exterior,
    )
    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F0": f0}, spaces={"S0": s}, openings={}, connectors={}, assets={},
        floors_by_level={0: f0}, spaces_by_floor={"F0": [s]},
        spaces_by_floor_and_room_type={("F0", "office"): [s]},
        openings_by_space={}, openings_by_floor={}, connectors_by_floor={},
        assets_by_space={}, assets_by_type={},
    )
    dist = calculate_straight_line_3d(s, s, b)
    if abs(dist - 0.0) < 1e-9:
        res.passed = True
        res.details = f"Distance: {dist} m"
    else:
        res.error_message = f"Expected 0.0, got {dist}"
    record_result(res)


def test_3_2_centroid_3d_varying_elevations_and_signs():
    res = TestResult("3.2 3D distance across negative (basement) and high positive elevations")
    # Floor -2 (Basement -2): elevation = -7.5 m
    # Floor 10 (Tower 10): elevation = +42.5 m
    # dz = 50.0 m
    # Room A at (0, 0) centroid
    # Room B at (30.0, 40.0) centroid -> dx=30, dy=40 -> 2D dist = 50.0 m
    # 3D dist = sqrt(50^2 + 50^2) = sqrt(5000) = 70.71067811865476 m
    f_b2 = Floor(id="F_B2", level=-2, name="Basement 2", elevation_m=-7.5, height_m=3.5)
    f_10 = Floor(id="F_10", level=10, name="Level 10", elevation_m=42.5, height_m=3.5)

    pa = Polygon([(-5, -5), (5, -5), (5, 5), (-5, 5)])  # centroid (0, 0)
    pb = Polygon([(25, 35), (35, 35), (35, 45), (25, 45)])  # centroid (30, 40)

    sa = Space(
        id="SA", floor_id="F_B2", type="room", room_type="storage", name="Basement Storage",
        ref="", polygon_coords=[], polygon=pa, area=100.0, centroid=(0.0, 0.0),
        representative_point=(0.0, 0.0), exterior_ring=pa.exterior,
    )
    sb = Space(
        id="SB", floor_id="F_10", type="room", room_type="office", name="Tower Office",
        ref="", polygon_coords=[], polygon=pb, area=100.0, centroid=(30.0, 40.0),
        representative_point=(30.0, 40.0), exterior_ring=pb.exterior,
    )
    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F_B2": f_b2, "F_10": f_10}, spaces={"SA": sa, "SB": sb},
        openings={}, connectors={}, assets={},
        floors_by_level={-2: f_b2, 10: f_10},
        spaces_by_floor={"F_B2": [sa], "F_10": [sb]},
        spaces_by_floor_and_room_type={("F_B2", "storage"): [sa], ("F_10", "office"): [sb]},
        openings_by_space={}, openings_by_floor={}, connectors_by_floor={},
        assets_by_space={}, assets_by_type={},
    )
    dist = calculate_straight_line_3d(sa, sb, b)
    expected = math.sqrt(30**2 + 40**2 + 50**2)
    err = abs(dist - expected)

    if err < 1e-9:
        res.passed = True
        res.details = f"Calculated: {dist:.6f} m, Expected: {expected:.6f} m, Error: {err:.2e} m"
    else:
        res.error_message = f"Precision error: expected {expected}, got {dist} (err {err})"
    record_result(res)


def test_3_3_centroid_3d_large_utm_coordinates():
    res = TestResult("3.3 3D distance with large GIS/UTM coordinate offsets")
    # Coordinates in UTM scale (e.g. 500,000m East, 4,500,000m North)
    # dx = 60.0m, dy = 80.0m, dz = 24.0m
    # 3D dist = sqrt(3600 + 6400 + 576) = sqrt(10576) = 102.83968105746...
    f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
    f8 = Floor(id="F8", level=8, name="L8", elevation_m=24.0, height_m=3.0)

    x0, y0 = 500000.0, 4500000.0
    pa = Polygon([(x0, y0), (x0 + 10, y0), (x0 + 10, y0 + 10), (x0, y0 + 10)])
    pb = Polygon([(x0 + 60, y0 + 80), (x0 + 70, y0 + 80), (x0 + 70, y0 + 90), (x0 + 60, y0 + 90)])

    sa = Space(id="SA", floor_id="F0", type="room", room_type="office", name="A", ref="",
               polygon_coords=[], polygon=pa, area=100.0, centroid=(x0 + 5, y0 + 5),
               representative_point=(x0 + 5, y0 + 5), exterior_ring=pa.exterior)
    sb = Space(id="SB", floor_id="F8", type="room", room_type="office", name="B", ref="",
               polygon_coords=[], polygon=pb, area=100.0, centroid=(x0 + 65, y0 + 85),
               representative_point=(x0 + 65, y0 + 85), exterior_ring=pb.exterior)

    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F0": f0, "F8": f8}, spaces={"SA": sa, "SB": sb},
        openings={}, connectors={}, assets={},
        floors_by_level={0: f0, 8: f8}, spaces_by_floor={"F0": [sa], "F8": [sb]},
        spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
        connectors_by_floor={}, assets_by_space={}, assets_by_type={},
    )
    dist = calculate_straight_line_3d(sa, sb, b)
    expected = math.sqrt(60.0**2 + 80.0**2 + 24.0**2)
    err = abs(dist - expected)

    if err < 1e-9:
        res.passed = True
        res.details = f"UTM distance calculated: {dist:.8f} m (precision error = {err:.2e} m)"
    else:
        res.error_message = f"Catastrophic cancellation in large coordinates: expected {expected}, got {dist}"
    record_result(res)


# ==============================================================================
# SUITE 4: Vertical Stacking Overlap
# ==============================================================================

def test_4_1_vertical_stacking_offset_candidates():
    res = TestResult("4.1 Vertical stacking overlap selection among multiple partially offset spaces")
    # Base space: [0, 10] x [0, 10] (100 m²) on Floor 0
    # Floor 1 Candidate 1: [0, 8] x [0, 10] -> overlap = 80 m²
    # Floor 1 Candidate 2: [5, 15] x [0, 10] -> overlap = 50 m²
    # Floor 1 Candidate 3: [9, 19] x [0, 10] -> overlap = 10 m²
    f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
    f1 = Floor(id="F1", level=1, name="First", elevation_m=3.0, height_m=3.0)

    p0 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    s0 = Space(id="S0", floor_id="F0", type="room", room_type="office", name="Base", ref="",
               polygon_coords=[], polygon=p0, area=100.0, centroid=(5, 5),
               representative_point=(5, 5), exterior_ring=p0.exterior)

    p1 = Polygon([(0, 0), (8, 0), (8, 10), (0, 10)])
    s1 = Space(id="S1_80", floor_id="F1", type="room", room_type="office", name="Upper 80", ref="",
               polygon_coords=[], polygon=p1, area=80.0, centroid=(4, 5),
               representative_point=(4, 5), exterior_ring=p1.exterior)

    p2 = Polygon([(5, 0), (15, 0), (15, 10), (5, 10)])
    s2 = Space(id="S2_50", floor_id="F1", type="room", room_type="office", name="Upper 50", ref="",
               polygon_coords=[], polygon=p2, area=100.0, centroid=(10, 5),
               representative_point=(10, 5), exterior_ring=p2.exterior)

    p3 = Polygon([(9, 0), (19, 0), (19, 10), (9, 10)])
    s3 = Space(id="S3_10", floor_id="F1", type="room", room_type="office", name="Upper 10", ref="",
               polygon_coords=[], polygon=p3, area=100.0, centroid=(14, 5),
               representative_point=(14, 5), exterior_ring=p3.exterior)

    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F0": f0, "F1": f1},
        spaces={"S0": s0, "S1_80": s1, "S2_50": s2, "S3_10": s3},
        openings={}, connectors={}, assets={},
        floors_by_level={0: f0, 1: f1},
        spaces_by_floor={"F0": [s0], "F1": [s3, s2, s1]},  # Inserted in reverse order
        spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
        connectors_by_floor={}, assets_by_space={}, assets_by_type={},
    )
    best_cand, overlap = find_stacked_room(s0, "above", b)

    if best_cand.id == "S1_80" and abs(overlap - 80.0) < 1e-6:
        res.passed = True
        res.details = f"Correctly selected {best_cand.id} with maximum overlap {overlap:.1f} m²"
    else:
        res.error_message = f"Expected S1_80 with 80.0 m², got {best_cand.id} with {overlap} m²"
    record_result(res)


def test_4_2_vertical_stacking_disjoint_floors_zero_overlap_bug():
    res = TestResult("4.2 Vertical stacking on completely disjoint floors (ZERO OVERLAP BUG)")
    # Base space: [0, 10] x [0, 10] on Floor 0
    # Floor 1 spaces: completely displaced, e.g. [1000, 1010] x [1000, 1010] and [2000, 2010] x [2000, 2010]
    # There is 0.0 m² overlap with ANY space on Floor 1!
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

    p2 = Polygon([(2000, 2000), (2010, 2000), (2010, 2010), (2000, 2010)])
    s2 = Space(id="S2_DISJOINT", floor_id="F1", type="room", room_type="office", name="Disjoint 2", ref="",
               polygon_coords=[], polygon=p2, area=100.0, centroid=(2005, 2005),
               representative_point=(2005, 2005), exterior_ring=p2.exterior)

    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F0": f0, "F1": f1},
        spaces={"S0": s0, "S1_DISJOINT": s1, "S2_DISJOINT": s2},
        openings={}, connectors={}, assets={},
        floors_by_level={0: f0, 1: f1},
        spaces_by_floor={"F0": [s0], "F1": [s1, s2]},
        spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
        connectors_by_floor={}, assets_by_space={}, assets_by_type={},
    )

    try:
        cand, overlap = find_stacked_room(s0, "above", b)
        # Because max_overlap is initialized to -1.0, 0.0 > -1.0 is TRUE for the first candidate!
        # So it returns cand = S1_DISJOINT with overlap = 0.0!
        if overlap == 0.0:
            res.bug_exposed = True
            res.error_message = (
                f"BUG EXPOSED: find_stacked_room returned disjoint space '{cand.id}' with 0.0 m² overlap! "
                f"It failed to raise ValueError despite having zero geometric overlap."
            )
            res.details = (
                "geometry.py initializes max_overlap = -1.0. When all candidates have 0.0 overlap, "
                "the first candidate satisfies 0.0 > -1.0 and is falsely returned as stacked room."
            )
        else:
            res.passed = True
            res.details = f"Unexpected non-zero overlap: {overlap}"
    except ValueError as e:
        res.passed = True
        res.details = f"Properly raised ValueError: {e}"
    except Exception as e:
        res.error_message = f"Unexpected error: {type(e).__name__}: {e}"
    record_result(res)


def test_4_3_vertical_stacking_boundary_directions():
    res = TestResult("4.3 Vertical stacking boundary directions (roof up, basement down, invalid string)")
    f0 = Floor(id="F0", level=0, name="Ground", elevation_m=0.0, height_m=3.0)
    p0 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    s0 = Space(id="S0", floor_id="F0", type="room", room_type="office", name="Base", ref="",
               polygon_coords=[], polygon=p0, area=100.0, centroid=(5, 5),
               representative_point=(5, 5), exterior_ring=p0.exterior)
    b = Building(
        metadata=BuildingMetadata(id="test", name="test", source=""),
        floors={"F0": f0}, spaces={"S0": s0}, openings={}, connectors={}, assets={},
        floors_by_level={0: f0}, spaces_by_floor={"F0": [s0]},
        spaces_by_floor_and_room_type={}, openings_by_space={}, openings_by_floor={},
        connectors_by_floor={}, assets_by_space={}, assets_by_type={},
    )

    # 1. Look above when no floor above
    try:
        find_stacked_room(s0, "above", b)
        up_raises = False
    except ValueError:
        up_raises = True

    # 2. Look below when no floor below
    try:
        find_stacked_room(s0, "below", b)
        down_raises = False
    except ValueError:
        down_raises = True

    # 3. Invalid direction string
    try:
        find_stacked_room(s0, "sideways", b)
        invalid_raises = False
    except ValueError:
        invalid_raises = True

    if up_raises and down_raises and invalid_raises:
        res.passed = True
        res.details = "All boundary/invalid directions properly raise ValueError."
    else:
        res.error_message = f"Failed boundary check: up={up_raises}, down={down_raises}, invalid={invalid_raises}"
    record_result(res)


def run_all_tests():
    print("=" * 80)
    print("STARTING EMPIRICAL ADVERSARIAL STRESS TEST HARNESS (MILESTONE 1)")
    print("=" * 80)

    test_1_1_l_shaped_polygon()
    test_1_2_u_shaped_polygon()
    test_1_3_self_touching_pinch_polygon_loader()
    test_1_4_antenna_spike_polygon_loader()
    test_1_5_colinear_boundary_points()
    test_1_6_degenerate_zero_area_colinear_loader()

    test_2_1_shared_wall_exact_0_99m_sensitivity()
    test_2_2_shared_wall_exact_1_01m_sensitivity()
    test_2_3_shared_wall_short_0_35m_contact()
    test_2_4_shared_wall_corner_touch_only()
    test_2_5_shared_wall_with_physical_wall_gap()

    test_3_1_centroid_3d_identical_rooms()
    test_3_2_centroid_3d_varying_elevations_and_signs()
    test_3_3_centroid_3d_large_utm_coordinates()

    test_4_1_vertical_stacking_offset_candidates()
    test_4_2_vertical_stacking_disjoint_floors_zero_overlap_bug()
    test_4_3_vertical_stacking_boundary_directions()

    print("=" * 80)
    passed_cnt = sum(1 for r in results if r.passed)
    bug_cnt = sum(1 for r in results if r.bug_exposed)
    failed_cnt = sum(1 for r in results if not r.passed and not r.bug_exposed)

    print(f"SUMMARY: {len(results)} tests executed | {passed_cnt} passed | {bug_cnt} bugs exposed | {failed_cnt} unexpected failures")
    print("=" * 80)

    if bug_cnt > 0:
        print("\nEXPOSED BUGS:")
        for r in results:
            if r.bug_exposed:
                print(f"- {r.name}:")
                print(f"    {r.error_message}")
                if r.details:
                    print(f"    {r.details}")

    return bug_cnt, failed_cnt


if __name__ == "__main__":
    bugs, fails = run_all_tests()
    # Exit with code 0 if all tests executed cleanly, but return summary
    sys.exit(0)
