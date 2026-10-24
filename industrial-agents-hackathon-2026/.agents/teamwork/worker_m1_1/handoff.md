# Handoff Report — Milestone 1: Core Spatial Geometry & Reasoning Engine

**Date:** 2026-10-24  
**Agent:** `teamwork_preview_worker` (worker_m1_1)  
**Milestone:** Milestone 1 (Features 1, 2, 3, 4, 5)  
**Parent Task ID:** `99a36772-9103-445c-a001-17463bb30980`  
**Handoff Type:** Hard (Complete)

---

## 1. Observation

### 1.1 Requirements and Scope
Per dispatch instructions and `PROJECT.md`, Milestone 1 requires implementing the core spatial geometry and data models layer with exclusive ownership of:
- `spatial_engine/__init__.py`
- `spatial_engine/models.py`
- `spatial_engine/building_loader.py`
- `spatial_engine/geometry.py`
- `tests/unit/test_spatial_geometry.py`

### 1.2 Implemented Components
1. **`spatial_engine/models.py`** (195 lines):
   - Defined `BuildingMetadata`, `Floor`, `Space`, `Opening`, `Connector`, `AssetFootprint`, `Asset`, and `Building`.
   - Used dataclasses with slots for maximum memory efficiency and speed.
   - Built indexed lookups on `Building`: `floors_by_level`, `spaces_by_floor`, `spaces_by_floor_and_room_type`, `openings_by_space`, `openings_by_floor`, `connectors_by_floor`, `assets_by_space`, `assets_by_type`.
   - Included helpers on `Opening` (`other_side`, `is_entrance`), `Connector` (`is_lift`, `is_stairs`), and `Space` (`contains_point`).

2. **`spatial_engine/building_loader.py`** (254 lines):
   - `load_building(path: str | Path) -> Building`: Loads `building.json` from file or folder.
   - Validates coordinates, repairs non-simple/invalid polygons via `shapely.validation.make_valid`, and pre-computes:
     - `area = float(poly.area)`
     - `centroid = (float(poly.centroid.x), float(poly.centroid.y))`
     - `representative_point = (float(rep_pt.x), float(rep_pt.y))`
     - `exterior_ring = poly.exterior`
   - `load_equipment_csv(csv_path: str | Path) -> list[Asset]`: Ingests equipment CSVs with fallback for missing JSON assets.

3. **`spatial_engine/geometry.py`** (298 lines):
   - `calculate_room_area(space: Space) -> float`: Returns polygon surface area in m².
   - `calculate_floor_area_total(building: Building, floor_id: str | int | Floor, room_type: str) -> float`: Computes aggregate surface area of all rooms of given type on a floor.
   - `find_largest_room(building: Building, floor_id: str | int | Floor, room_type: str) -> tuple[Space, float]`: Finds room with maximum area.
   - `calculate_straight_line_3d(space_a: Space, space_b: Space, building: Building) -> float`: Computes 3D Euclidean distance between polygon centroids across elevation levels ($z = \text{floor.elevation\_m}$).
   - `find_stacked_room(space: Space, target_direction: str, building: Building) -> tuple[Space, float]`: Maximizes 2D polygon intersection area on adjacent floor levels (`above` $\to \text{level} + 1$, `below` $\to \text{level} - 1$).
   - `count_shared_walls(target_space: Space, building: Building, min_length: float = 1.0, buffer_dist: float = 0.35) -> int`: Counts distinct qualifying rooms sharing a boundary $\ge 1.0\text{ m}$ (dilated by $0.35\text{ m}$), strictly excluding corridors, stairwells, lifts, balconies, and outdoor spaces.
   - Supporting routines: `get_shared_wall_spaces`, `get_shared_boundary`, `is_point_in_space`, `resolve_floor`.

4. **`spatial_engine/__init__.py`** (47 lines):
   - Clean public package interface exposing all models and geometry functions.

5. **`tests/unit/test_spatial_geometry.py`** (481 lines):
   - Complete 24-test suite covering synthetic test fixtures, unit tests for all operations, dev benchmark questions on `proc-factory-dev-012` and `osm-way22744230`, and exhaustive validation across all 97 spatial benchmark questions in `data/dev/`.

### 1.3 Test Execution Output
Executed command:
`/Users/konstantin/.local/bin/uv run python tests/unit/test_spatial_geometry.py -v`

Output:
```
test_building_loaded_structure (__main__.TestDevBuildingGeometry.test_building_loaded_structure) ... ok
test_load_building_from_file_path (__main__.TestDevBuildingGeometry.test_load_building_from_file_path) ... ok
test_load_equipment_csv (__main__.TestDevBuildingGeometry.test_load_equipment_csv) ... ok
test_question_h01_largest_room (__main__.TestDevBuildingGeometry.test_question_h01_largest_room) ... ok
test_question_h02_floor_area_total (__main__.TestDevBuildingGeometry.test_question_h02_floor_area_total) ... ok
test_question_h05_shared_walls_count (__main__.TestDevBuildingGeometry.test_question_h05_shared_walls_count) ... ok
test_question_h06_straight_line_3d (__main__.TestDevBuildingGeometry.test_question_h06_straight_line_3d) ... ok
test_all_dev_floor_area_total_questions (__main__.TestDevDatasetExhaustiveGeometry.test_all_dev_floor_area_total_questions) ... ok
test_all_dev_largest_room_questions (__main__.TestDevDatasetExhaustiveGeometry.test_all_dev_largest_room_questions) ... ok
test_all_dev_room_stacked_questions (__main__.TestDevDatasetExhaustiveGeometry.test_all_dev_room_stacked_questions) ... ok
test_all_dev_shared_walls_questions (__main__.TestDevDatasetExhaustiveGeometry.test_all_dev_shared_walls_questions) ... ok
test_all_dev_straight_line_3d_questions (__main__.TestDevDatasetExhaustiveGeometry.test_all_dev_straight_line_3d_questions) ... ok
test_question_h05_room_stacked_below (__main__.TestOSMBuildingStacking.test_question_h05_room_stacked_below) ... ok
test_question_h06_room_stacked_below (__main__.TestOSMBuildingStacking.test_question_h06_room_stacked_below) ... ok
test_calculate_floor_area_total (__main__.TestSyntheticSpatialGeometry.test_calculate_floor_area_total) ... ok
test_calculate_room_area (__main__.TestSyntheticSpatialGeometry.test_calculate_room_area) ... ok
test_calculate_straight_line_3d (__main__.TestSyntheticSpatialGeometry.test_calculate_straight_line_3d) ... ok
test_count_shared_walls (__main__.TestSyntheticSpatialGeometry.test_count_shared_walls) ... ok
test_find_largest_room (__main__.TestSyntheticSpatialGeometry.test_find_largest_room) ... ok
test_find_stacked_room (__main__.TestSyntheticSpatialGeometry.test_find_stacked_room) ... ok
test_opening_and_connector_helpers (__main__.TestSyntheticSpatialGeometry.test_opening_and_connector_helpers) ... ok
test_point_in_space_and_boundary (__main__.TestSyntheticSpatialGeometry.test_point_in_space_and_boundary) ... ok
test_resolve_floor (__main__.TestSyntheticSpatialGeometry.test_resolve_floor) ... ok
test_space_queries_and_lookups (__main__.TestSyntheticSpatialGeometry.test_space_queries_and_lookups) ... ok

----------------------------------------------------------------------
Ran 24 tests in 2.375s

OK
```

---

## 2. Logic Chain

1. **Polygon Pre-computation**:
   Loading and indexing buildings up-front with pre-parsed Shapely geometries eliminates geometry re-instantiation overhead on every query. Centroids, areas, representative points, and exterior rings are cached directly on the `Space` model.
2. **Floor Resolution**:
   `resolve_floor` handles string IDs (e.g. `proc-factory-dev-012-F0`), integer levels (0, 1, -1), integer level strings ("0", "1"), and case-insensitive floor names ("Ground floor"). This ensures upstream callers (solvers, graph builders, REST API endpoints) never fail due to floor referencing formats.
3. **Shared Wall Boundary Filter**:
   Industrial halls and rooms share boundaries with walls of nominal thickness (~0.1m - 0.3m). Buffering the target space boundary by $0.35\text{ m}$ bridges the physical wall gap, and intersecting with adjacent exterior boundaries produces exact contact lengths. Excluding `corridor`, `stair`, `stairwell`, `lift`, `balcony`, and `outdoor` ensures that soundproofing queries match ground truth with 100% precision (24/24 on dev).
4. **Stacked Overlap Calculation**:
   Intersection area between base polygon and adjacent floor polygons identifies the vertically aligned space above/below. Handled both positive and negative levels (basement level -1). Achieved 9/9 (100%) on dev stacking questions.
5. **Centroid-Based 3D Euclidean Distance**:
   Takes 2D centroid $(x, y)$ of both space polygons and elevation $z$ from their respective floors to compute $\sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$. Matches ground truth within $< 0.05\%$ (well within the $\pm 2\%$ benchmark tolerance). Achieved 13/13 (100%) on dev.

---

## 3. Caveats

- **Coordinate System Consistency**:
  Vertical stacking overlap calculations require that floor polygons share a global building coordinate system. In Swiss Dwellings datasets, floor plans are centered independently, but the hackathon benchmark explicitly restricts `room_stacked` questions to procedural and OSM buildings.
- **Representative Point vs Centroid**:
  For routing and anchor placement (M2), `space.representative_point` should be used instead of `space.centroid` because representative points are guaranteed to fall inside concave or L-shaped rooms. Both are pre-computed on each `Space`.

---

## 4. Conclusion

Milestone 1 is complete. All 5 geometry features (`calculate_room_area`, `calculate_floor_area_total`, `find_largest_room`, `calculate_straight_line_3d`, `find_stacked_room`, `count_shared_walls`) and all data models (`Building`, `Floor`, `Space`, `Opening`, `Connector`, `Asset`) are implemented, tested, and verified with 100% pass rate across all 97 relevant spatial benchmark questions in `data/dev/`.

---

## 5. Verification Method

To independently verify this implementation:

```bash
# 1. Run all unit tests with full verbosity:
/Users/konstantin/.local/bin/uv run python tests/unit/test_spatial_geometry.py -v

# 2. Verify compilation of all modules:
/Users/konstantin/.local/bin/uv run python -m py_compile spatial_engine/__init__.py spatial_engine/models.py spatial_engine/building_loader.py spatial_engine/geometry.py tests/unit/test_spatial_geometry.py

# 3. Quick smoke test in Python REPL:
/Users/konstantin/.local/bin/uv run python -c "
from spatial_engine import load_building, find_largest_room, calculate_floor_area_total, count_shared_walls, calculate_straight_line_3d
b = load_building('data/dev/proc-factory-dev-012')
largest, area = find_largest_room(b, 'proc-factory-dev-012-F0', 'kitchen')
print(f'Largest kitchen: {largest.name} ({area:.1f} m²)')
assert largest.id == 'proc-factory-dev-012-F0-S030'
"
```
