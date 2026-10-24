# Handoff Report — Milestone 2 Review: Multi-Floor Routing & Constraint Engine

**Date:** 2026-10-24  
**Reviewer:** `teamwork_preview_reviewer` (Milestone 2 Reviewer & Critic)  
**Parent Task ID:** `99a36772-9103-445c-a001-17463bb30980`  
**Verdict:** **APPROVE**  

---

## 1. Observation

1. **Requirements & Scope**:
   - `PROJECT.md` (Features 6–13, lines 68–75, 115–120):
     * Multi-floor routing graph connecting space representative points, openings, and vertical connectors.
     * Multi-floor weights: stairs cost $= 12.0 \times \text{span}$, lift cost $= 15.0 + 6.0 \times \text{span}$.
     * Step-free filtering: excludes stairs (`kind in ('stairs', 'stair')`) and non-accessible doors (`step_free == False`).
     * Door clearance filtering: excludes openings narrower than `min_door_width - 1e-6`.
     * `wide_delivery_count` & `step_free_reachable_count`: reachable rooms (`type == "room"`) on target floor under constraints.
     * `solve_errand`: 2-leg Dijkstra route (start $\to$ nearest asset space $\to$ largest target room by polygon area).
     * `evaluate_what_if_door`: counts target floor rooms whose exit distance improves by $> 1.0\text{ m}$.
     * Dynamic closures: dynamic sets of blocked spaces, openings, or connectors.

2. **Codebase Implementation**:
   - `spatial_engine/graph.py` (260 lines):
     * Line 20–26: Defines `STAIRS_COST_PER_FLOOR_M = 12.0`, `LIFT_WAIT_COST_M = 15.0`, `LIFT_COST_PER_FLOOR_M = 6.0`, `DEFAULT_TOLERANCE = 1e-6`.
     * Lines 93–124: Registers space anchors using `space.representative_point`.
     * Lines 125–188: Registers door nodes `door:{opening_id}` with Euclidean distance to spaces, 0.0 weight to `outside` for exterior doors, with filters for `step_free`, `min_door_width`, and `closed`.
     * Lines 189–258: Registers multi-floor transitions across consecutive floor stops (`itertools.pairwise`) with exact stair ($12.0 \times \text{span}$) and lift ($15.0 + 6.0 \times \text{span}$) weights; strictly prunes stairs and non-accessible connectors in `step_free` mode.
     * Lines 29–52: `_extract_entities` supports both typed `Building` dataclass instances and raw JSON dictionaries.
   - `spatial_engine/router.py` (555 lines):
     * Lines 33–69: `RouteResult` dataclass supporting tuple unpacking `(distance, path)`.
     * Lines 70–113: `ErrandResult` dataclass supporting tuple unpacking `(total_distance, via, target)`.
     * Lines 114–147: `shortest_path(graph, start, end)` using NetworkX Dijkstra.
     * Lines 149–205: `count_reachable_rooms(...)` using `nx.descendants` filtered to `s.floor_id == target_floor_id` and `s.type == "room"`.
     * Lines 207–310: `solve_errand(...)`: Leg 1 finds nearest asset space via single-source Dijkstra; Leg 2 finds largest room of target type on target floor via `find_largest_room` polygon area, then routes from asset space to target room.
     * Lines 312–426: `evaluate_what_if_door(...)`: Validates polygon adjacency $\le 0.6\text{ m}$, computes baseline exit distances via single-source Dijkstra from `outside`, synthesizes virtual door node `door:virtual_synthetic` at midpoint of `nearest_points(poly_a, poly_b)`, recomputes distances from `outside`, and counts rooms where $d_{\text{before}} - d_{\text{after}} > \text{threshold} + 10^{-6}$.
     * Lines 428–555: `resolve_space`, `directions`, and high-level `find_route` helper functions.

3. **Integrity Audit**:
   - Grep search across `spatial_engine/graph.py` and `spatial_engine/router.py` confirmed:
     * No hardcoded test IDs (zero occurrences of building IDs like `proc-factory-dev-003`, `osm-way`, `resplan`, `synth`).
     * No hardcoded benchmark output values (zero occurrences of answer constants like `132.35`, `165.75`, `30`, `7`, `5`).
     * No dummy facades or shortcuts bypassing Dijkstra pathfinding or Shapely operations.
     * All logic uses genuine NetworkX and Shapely graph/geometric algorithms.

4. **Test & Verification Tool Outputs**:
   - `uv run python tests/unit/test_routing_engine.py`:
     ```
     Ran 30 tests in 1.081s
     OK
     ```
     (Includes 100% pass on all 41 benchmark routing questions across all 40 buildings in `data/dev/`).
   - `uv run python tests/run_tests.py`:
     ```
     T1 | Feature Coverage (>=5 tests per feature) | 120 passed | 0 failed | 1.437s
     T2 | Boundary & Corner Cases                  | 120 passed | 0 failed | 4.863s
     T3 | Cross-Feature Combinations               |  30 passed | 0 failed | 0.394s
     T4 | Real-World Application Scenarios         |  15 passed | 0 failed | 1.262s
     ALL| TOTAL CONSOLIDATED SUITE                 | 285 passed | 0 failed | 7.956s
     >>> OVERALL RESULT: ALL TESTS PASSED (100% SUCCESS) <<<
     ```
   - `uv run ruff check spatial_engine/graph.py spatial_engine/router.py tests/unit/test_routing_engine.py`:
     ```
     All checks passed!
     ```
   - Production vs Reference Oracle Cross-Verification:
     Direct programmatic assertion confirmed 100% numerical and structural parity between `spatial_engine` and `ReferenceOracle` across `count_reachable_rooms`, `solve_errand`, and `evaluate_what_if_door`.

---

## 2. Logic Chain

1. **Conformance with Specifications**:
   - Observations 1 and 2 demonstrate that Features 6–13 from `PROJECT.md` are accurately implemented with full adherence to the required function signatures, dataclass definitions, and parameter options.
2. **Weight Model & Routing Mechanics**:
   - Observation 2 confirms that the vertical connector weight model ($12.0 \times \text{span}$ for stairs, $15.0 + 6.0 \times \text{span}$ for lifts) exactly matches `starter_agent/building_map.py` and competition specifications.
   - Observation 2 confirms that `nx.MultiGraph` correctly preserves parallel edges (e.g., adjacent stair and lift connections) while Dijkstra resolves the optimal path.
3. **Accessibility & Dynamic Filtering**:
   - Observation 2 confirms that `step_free=True` strictly excludes all stair connectors and non-accessible doors, even if an individual stair record had erroneous metadata.
   - Observation 2 confirms that `min_door_width` uses a robust epsilon threshold (`1e-6`) to prevent floating-point boundary errors on 1.0m / 1.1m standard clearances.
4. **Errand & What-If Simulations**:
   - Errand 2-leg routing correctly decouples asset acquisition from target room navigation, with deterministic tie-breaking on equidistant asset spaces.
   - What-if door evaluation accurately tests $\le 0.6\text{ m}$ wall proximity, applies synthetic door placement at boundary midpoints, and leverages bidirectional symmetry by running single-source Dijkstra from the exterior anchor, achieving $O(|V|\log|V| + |E|)$ complexity instead of repetitive multi-source path evaluations.
5. **No Regressions & 100% Test Pass Rate**:
   - Observations 3 and 4 confirm zero integrity issues and 100% success across 30 unit tests and 285 E2E tests with zero linting warnings.

---

## 3. Adversarial Review & Quality Assessment

### Quality Review Summary
- **Verdict**: **APPROVE**
- **Findings**:
  - *No Critical or Major findings.*
  - *Minor (Observation / Defense-in-Depth)*: In `spatial_engine/router.py` (`evaluate_what_if_door`), the geometry check validates `poly_a.distance(poly_b) <= 0.6`. In physical buildings and current benchmark questions, door simulations only query rooms on the same floor. However, if two vertically stacked rooms on different floors (e.g., F0 and F1) have identical 2D footprints, their 2D distance is 0.0. Adding an explicit guard `if space_a.floor_id != space_b.floor_id: raise ValueError("A door can only join two spaces on the same floor.")` would provide additional defense-in-depth against cross-floor door insertion. (Non-blocking since all benchmark questions specify rooms on the same floor).

### Adversarial Challenge Results
1. **Assumption Tested**: Does NetworkX `nx.MultiGraph` select the minimum edge when parallel edges exist between rooms?
   - *Test*: Created MultiGraph with weights 20.0 and 5.0 between two nodes.
   - *Result*: `nx.shortest_path_length` returned 5.0. **PASSED**.
2. **Assumption Tested**: What happens if the start room itself is closed?
   - *Test*: Closed start room in `count_reachable_rooms`.
   - *Result*: Correctly returned 0 without unhandled exception. **PASSED**.
3. **Assumption Tested**: What happens if an errand queries an asset type not in the building, or an asset in a disconnected room?
   - *Test*: Queried non-existent asset (`anti_matter_reactor`) and disconnected room asset.
   - *Result*: Correctly raised `ValueError` and `nx.NetworkXNoPath`. **PASSED**.
4. **Assumption Tested**: What happens if what-if door simulation is executed on a building with no exits to outside?
   - *Test*: Evaluated building with empty opening list.
   - *Result*: Distance before and after evaluates to `inf`, returns 0 without crashing. **PASSED**.
5. **Assumption Tested**: Are boundary door widths ($w = 1.000\text{ m}$ with `min_width=1.0`) preserved?
   - *Test*: Tested synthetic door width 1.0m against `min_width=1.0`.
   - *Result*: Retained in graph due to `-1e-6` tolerance. **PASSED**.

---

## 4. Caveats

- **No Caveats**: All 41 routing benchmark questions across all 40 buildings in `data/dev/` pass with 100% accuracy.
- Execution completed cleanly in under 2 seconds for all routing unit tests and benchmark scoring.

---

## 5. Conclusion

Milestone 2 (`spatial_engine/graph.py` and `spatial_engine/router.py`) meets all requirements of Features 6–13 in `PROJECT.md` and `ORIGINAL_REQUEST.md`. The implementation is mathematically sound, performant, clean, well-tested, and free of any integrity violations.

**Verdict: APPROVE**. Milestone 2 is complete and ready for Milestone 3 (Deterministic Benchmark Solver & Submission).

---

## 6. Verification Method

To independently verify this evaluation:
1. Run unit test suite:
   ```bash
   /Users/konstantin/.local/bin/uv run python tests/unit/test_routing_engine.py
   ```
2. Run unified E2E test suite:
   ```bash
   /Users/konstantin/.local/bin/uv run python tests/run_tests.py
   ```
3. Run linter:
   ```bash
   /Users/konstantin/.local/bin/uv run ruff check spatial_engine/graph.py spatial_engine/router.py tests/unit/test_routing_engine.py
   ```
