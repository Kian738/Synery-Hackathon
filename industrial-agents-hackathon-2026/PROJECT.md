# Project: Talk to Your Building (Industrial Agents Hackathon 2026 — Track 01)

## Architecture

The system is structured into four decoupled, production-grade layers:
1. **Spatial Geometry Layer (`spatial_engine/geometry.py`, `spatial_engine/models.py`, `spatial_engine/building_loader.py`)**:
   - High-precision Shapely polygon operations, valid coordinate parsing, polygon centroid calculation, 3D Euclidean distances across elevation levels, vertical stacking polygon intersections, and wall boundary buffering for shared wall detection.
2. **Routing & Constraint Graph Layer (`spatial_engine/graph.py`, `spatial_engine/router.py`)**:
   - NetworkX multi-floor graph builder connecting space representative points to opening nodes and vertical connectors (stairs and lifts).
   - Dynamic constraint filtering for door clearances (`min_width`), step-free accessibility (excluding stairs and non-accessible doors), and dynamic space/connector closures.
   - Optimal multi-stop Dijkstra pathfinding for errands (start → closest asset space → largest target room) and counterfactual what-if door impact simulation.
3. **Deterministic Solver & Benchmark Interface (`spatial_engine/solver.py`, `benchmark_runner.py`)**:
   - Zero-token-cost, sub-second solver answering all 9 benchmark question categories with strictly compliant `Answer: ...` formatting.
   - Comprehensive test evaluation pipeline generating `submission.csv` for all 145 test questions and CLI benchmark runner documented in `BENCHMARK.md`.
4. **Interactive Visualizer & Real-Time Operational Dispatcher (`visualizer/`)**:
   - Zero-dependency Python standard library HTTP/REST backend (`visualizer/server.py`) serving static assets and dynamic routing/dispatch endpoints.
   - Interactive HTML5/WebGL frontend with Three.js rendering 2D/3D stacked multi-floor plans, exploded layer slider, animated navigation routes, interactive door creation tool, connector/room closure toggles, and Web Speech API hands-free voice guidance.

---

## Code Layout

```
industrial-agents-hackathon-2026/
├── PROJECT.md                             # Global project specification & milestone index
├── BENCHMARK.md                           # Single CLI command evaluation documentation
├── submission.csv                         # Ground truth formatted submission for 145 test questions
├── spatial_engine/                        # Core spatial reasoning and routing engine (M1, M2, M3)
│   ├── __init__.py
│   ├── models.py                          # Data models: Building, Floor, Space, Opening, Connector, Asset
│   ├── building_loader.py                 # Robust loader with coordinate validation & spatial indexing
│   ├── geometry.py                        # Polygon area, 3D centroids, stacking overlap, wall buffering
│   ├── graph.py                           # Multi-floor routing graph with constraint filtering
│   ├── router.py                          # Dijkstra, multi-stop errand solver, what-if counterfactuals
│   ├── solver.py                          # 9-category deterministic benchmark solver & regex classifier
│   └── tools.py                           # High-level spatial query tools for agent/API integration
├── visualizer/                            # Interactive Web Visualizer & Dispatcher (M4)
│   ├── __init__.py
│   ├── __main__.py                        # CLI entrypoint (`python -m visualizer [building_dir]`)
│   ├── server.py                          # ThreadingHTTPServer REST API backend
│   └── static/                            # Single Page Application
│       ├── index.html                     # Visualizer UI layout & control panels
│       ├── app.js                         # Three.js 2D/3D multi-floor engine & event handlers
│       ├── voice.js                       # Web Speech API recognition & synthesis engine
│       ├── style.css                      # Modern responsive industrial dark UI
│       └── vendor/                        # Offline standalone Three.js and OrbitControls
├── tests/                                 # E2E test suite (E2E Testing Track)
│   ├── run_tests.py                       # Unified test runner with tier breakdown
│   ├── test_tier1_features.py             # Tier 1: Feature coverage (>=5 tests per feature)
│   ├── test_tier2_boundaries.py           # Tier 2: Boundary & corner cases (>=5 per feature)
│   ├── test_tier3_combinations.py         # Tier 3: Pairwise cross-feature interactions
│   └── test_tier4_scenarios.py            # Tier 4: Real-world operational scenarios
```

---

## Feature Inventory

Every feature surveyed from `ORIGINAL_REQUEST.md` and codebase analysis is cataloged below with its assigned milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `largest_room` query | Identify room with largest polygon area on target floor for given room type, output name and area | M1 | Survey (R1) |
| 2 | `floor_area_total` query | Compute aggregate polygon surface area for all rooms of a given type on a target floor | M1 | Survey (R1) |
| 3 | `straight_line_3d` query | Compute 3D Euclidean distance between polygon centroids of two rooms across elevation levels | M1 | Survey (R1) |
| 4 | `room_stacked` query | Find space on adjacent floor (above/below) maximizing 2D polygon intersection area | M1 | Survey (R1) |
| 5 | `shared_walls_count` query | Count rooms sharing >= 1.0 m wall boundary (buffered by 0.35 m), excluding corridors/stairs/lifts/balconies | M1 | Survey (R1) |
| 6 | Multi-floor routing graph | Multi-floor NetworkX graph connecting space representative points, openings, and stairs/lifts | M2 | Survey (R2) |
| 7 | Step-free route filtering | Filter routing graph to step-free paths (lifts only, excluding stairs and stepped openings) | M2 | Survey (R2) |
| 8 | Door clearance filtering | Filter routing graph to openings meeting minimum width threshold (`min_width`) | M2 | Survey (R2) |
| 9 | `wide_delivery_count` query | Count reachable rooms on target floor under step-free and minimum door width constraints | M2 | Survey (R1, R2) |
| 10 | `step_free_reachable_count` | Count reachable rooms under step-free and dynamic connector closure constraints | M2 | Survey (R1, R2) |
| 11 | `errand` multi-stop solver | Dijkstra route: start → nearest space with target asset → largest room of target type on target floor | M2 | Survey (R1, R2) |
| 12 | `what_if_door` simulation | Counterfactual impact: count rooms whose distance to outside improves by > 1.0 m if door added | M2 | Survey (R1, R2) |
| 13 | Dynamic closures engine | Dynamically mark spaces, connectors, or openings as closed and recompute reachable/optimal paths | M2 | Survey (R2) |
| 14 | Deterministic solver interface | Complete classifier & answer generator conforming to `benchmark/score.py` regex `^\W*answer\W*:\s*(.+)$` | M3 | Survey (R1) |
| 15 | Dev benchmark accuracy >= 95% | Pass all 9 categories on `data/dev/` achieving >= 95% accuracy (target: 100%) | M3 | Survey (R1) |
| 16 | Test submission generator | Run benchmark over `data/test/questions.csv` generating compliant `submission.csv` (145 questions) | M3 | Survey (R4) |
| 17 | `BENCHMARK.md` CLI docs | Clear documentation of single CLI evaluation command for unseen buildings and question sets | M3 | Survey (R4) |
| 18 | Stacked 2D/3D floor visualizer | Interactive Three.js multi-floor building layout with elevations, rooms, doors, assets | M4 | Survey (R3) |
| 19 | Exploded floor stack view | Adjustable vertical spacing slider (1.0x to 4.0x) to inspect lower floors without occlusion | M4 | Survey (R3) |
| 20 | Animated route navigation | Animated 3D route tube with traveling beacon/avatar demonstrating navigation paths | M4 | Survey (R3) |
| 21 | Live layout editor & dispatcher| Interactively add doors between adjacent rooms, toggle lift/room closures, and trigger live reroute | M4 | Survey (R3) |
| 22 | Voice-assisted navigation | Browser Web Speech API push-to-talk speech recognition, voice commands, and speech synthesis guidance | M4 | Survey (R3) |
| 23 | E2E Test Suite (Tiers 1-4) | Comprehensive opaque-box test suite validating all features across all 4 tiers | Final Milestone | Survey (Dual Track) |
| 24 | Adversarial coverage hardening | Tier 5 adversarial stress testing, boundary condition verification, and coverage audit | Final Milestone | Survey (Dual Track) |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Spatial Geometry & Reasoning Engine | Features 1, 2, 3, 4, 5 (`models.py`, `building_loader.py`, `geometry.py`) | none | DONE |
| M2 | Multi-Floor Routing & Constraint Engine | Features 6, 7, 8, 9, 10, 11, 12, 13 (`graph.py`, `router.py`) | M1 | DONE |
| M3 | Deterministic Benchmark Solver & Submission | Features 14, 15, 16, 17 (`solver.py`, `submission.csv`, `BENCHMARK.md`) | M1, M2 | DONE |
| M4 | Interactive Visualizer & Real-Time Dispatcher | Features 18, 19, 20, 21, 22 (`visualizer/` server & SPA) | M1, M2 | IN_PROGRESS |
| M5 | Final Milestone: E2E Validation & Adversarial Hardening | Features 23, 24 (Tiers 1-4 pass + Tier 5 adversarial coverage) | M3, M4, E2E Track | PLANNED |

---

## Interface Contracts

### `spatial_engine.models` & `spatial_engine.building_loader`
- `load_building(path: str | Path) -> Building`: Loads `building.json` and parses floors, spaces, openings, connectors, assets into validated dataclasses/Pydantic models with pre-computed Shapely geometries.

### `spatial_engine.geometry`
- `calculate_room_area(space: Space) -> float`: Polygon area in square meters.
- `calculate_floor_area_total(building: Building, floor_id: str, room_type: str) -> float`: Sum of room areas.
- `find_largest_room(building: Building, floor_id: str, room_type: str) -> tuple[Space, float]`: Largest room by area.
- `calculate_straight_line_3d(space_a: Space, space_b: Space, building: Building) -> float`: 3D Euclidean distance between polygon centroids.
- `find_stacked_room(space: Space, target_direction: str, building: Building) -> tuple[Space, float]`: Room on adjacent level with maximum polygon overlap.
- `count_shared_walls(target_space: Space, building: Building, min_length: float = 1.0, buffer_dist: float = 0.35) -> int`: Count of distinct rooms sharing >= min_length boundary.

### `spatial_engine.graph` & `spatial_engine.router`
- `build_routing_graph(building: Building, step_free: bool = False, min_door_width: float | None = None, closed: set[str] | None = None) -> nx.MultiGraph`: Constructs graph with space anchors, openings, and vertical connectors.
- `shortest_path(graph: nx.MultiGraph, start_node: str, end_node: str) -> RouteResult`: Returns distance and node sequence.
- `solve_errand(building: Building, start_id: str, asset_type: str, target_room_type: str, target_floor_id: str) -> ErrandResult`: Computes two-leg shortest path length.
- `count_reachable_rooms(building: Building, start_id: str, target_floor_id: str, step_free: bool, min_width: float | None, closed: set[str] | None) -> int`: Count of reachable spaces with `type == "room"`.
- `evaluate_what_if_door(building: Building, space_a_id: str, space_b_id: str, target_floor_id: str, threshold: float = 1.0) -> int`: Rooms on target floor with exit distance reduction > threshold.

### `spatial_engine.solver`
- `solve_question(building_dir: Path, question_text: str) -> str`: Formulates compliant string ending with `Answer: ...`.
- `evaluate_dataset(dataset_dir: Path) -> dict[str, float]`: Runs evaluation over questions and computes category accuracies.

### `visualizer` REST API
- `GET /api/building`: Returns building hierarchy, floor polygons, openings, connectors, and asset coordinates.
- `POST /api/route`: `{start: str, end: str, step_free: bool, min_width: float, closed: list[str]}` -> `{distance: float, path: list[dict], legs: list}`.
- `POST /api/closures`: `{closed: list[str]}` -> `{status: "ok"}`.
- `POST /api/door`: `{space_a: str, space_b: str}` -> `{status: "ok", door_id: str, position: [x, y]}`.
- `POST /api/voice_command`: `{transcript: str}` -> `{intent: str, response_text: str, action: dict}`.
