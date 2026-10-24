## 2026-10-24T14:13:48Z
Your identity: teamwork_preview_worker (Milestone 1: Core Spatial Geometry & Reasoning)
Your working directory: /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/.agents/teamwork/worker_m1_1/
Parent conversation ID: 99a36772-9103-445c-a001-17463bb30980

MANDATORY FIRST STEP: Read the authoritative requirements files:
1. /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/.agents/teamwork/ORIGINAL_REQUEST.md
2. /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/PROJECT.md
Also review survey findings and proven algorithms:
- /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/.agents/teamwork/teamwork_preview_explorer_survey_2/handoff.md
- /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/.agents/teamwork/teamwork_preview_spec_miner_survey_1/handoff.md

Exclusive File Ownership:
You exclusively own and write:
- `spatial_engine/__init__.py`
- `spatial_engine/models.py`
- `spatial_engine/building_loader.py`
- `spatial_engine/geometry.py`
- `tests/unit/test_spatial_geometry.py`
DO NOT modify files outside this scope.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Objective:
Implement Milestone 1: Core Spatial Geometry & Reasoning Engine.
1. `spatial_engine/models.py`:
   - Data models for Building, Floor, Space, Opening, Connector, Asset.
   - Clean dataclass / Pydantic structures with pre-parsed Shapely polygons.
2. `spatial_engine/building_loader.py`:
   - Fast, robust ingestion of `building.json` and `equipment.csv`.
   - Validate geometry, compute representative points, centroids, exterior rings, and floor index.
3. `spatial_engine/geometry.py`:
   - `calculate_room_area(space) -> float` (polygon.area in m²)
   - `calculate_floor_area_total(building, floor_id, room_type) -> float`
   - `find_largest_room(building, floor_id, room_type) -> tuple[Space, float]`
   - `calculate_straight_line_3d(space_a, space_b, building) -> float` (3D Euclidean distance between polygon centroids)
   - `find_stacked_room(space, target_direction, building) -> tuple[Space, float]` (maximum polygon overlap on adjacent floor level)
   - `count_shared_walls(target_space, building, min_length=1.0, buffer_dist=0.35) -> int` (shared boundary >= 1.0m, excluding corridors, stairwells, lifts, balconies, outdoor spaces).
4. `tests/unit/test_spatial_geometry.py`:
   - Comprehensive unit tests covering all geometry functions on dev buildings (e.g. `data/dev/proc-factory-dev-012`).
5. Run your unit tests using `/Users/konstantin/.local/bin/uv run python tests/unit/test_spatial_geometry.py` (or pytest). Ensure 100% pass.
6. Write your handoff report to `.agents/teamwork/worker_m1_1/handoff.md` detailing implementation, test outputs, and verification methods. Send a completion message to the parent (99a36772-9103-445c-a001-17463bb30980).
