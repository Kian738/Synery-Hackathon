# Handoff Report — Milestone 2: Multi-Floor Routing & Constraint Engine

**Date:** 2026-10-24  
**Agent:** `teamwork_preview_worker` (Milestone 2 Worker)  
**Parent Task ID:** `99a36772-9103-445c-a001-17463bb30980`  
**Handoff Type:** Hard (Complete)  
**Target Files Owned & Produced:**
- `spatial_engine/graph.py`
- `spatial_engine/router.py`
- `tests/unit/test_routing_engine.py`

---

## 1. Observation

1. **Benchmark Routing Requirements**:
   - `ORIGINAL_REQUEST.md` (lines 25–27, 44–45) specifies:
     * Multi-floor routing across stairs and lifts.
     * Step-free accessibility constraints.
     * Door clearance thresholds (`min_width`).
     * Multi-stop errands (start → nearest asset space → largest target room).
     * Dynamic closures of spaces, doors, or connectors.
     * Optimal routing distances within $\pm 1\%$ (or $\pm 1\text{ m}$) of Dijkstra path lengths.
     * What-if door simulation calculating room counts on target floors whose exit distance improves by $> 1.0\text{ m}$.
2. **Benchmark Distribution**:
   - Querying `data/dev/` reveals exactly 41 routing benchmark questions across 40 buildings:
     * `errand`: 19 questions
     * `wide_delivery_count`: 19 questions
     * `step_free_reachable_count`: 1 question
     * `what_if_door`: 2 questions
3. **Existing Model Structure**:
   - `spatial_engine/models.py` provides pre-parsed geometries:
     * `Building`, `Floor`, `Space`, `Opening`, `Connector`, `Asset`.
     * Precomputed `representative_point`, `polygon`, `area`, `centroid`, and category indexing.
4. **Code Quality and Test Results**:
   - Execution of unit test suite:
     ```
     /Users/konstantin/.local/bin/uv run python tests/unit/test_routing_engine.py
     Ran 30 tests in 1.004s
     OK
     ```
   - Execution of unified E2E test suite:
     ```
     /Users/konstantin/.local/bin/uv run python tests/run_tests.py
     ALL | TOTAL CONSOLIDATED SUITE | 285 passed | 0 failed | 0 skipped | 6.924s
     >>> OVERALL RESULT: ALL TESTS PASSED (100% SUCCESS) <<<
     ```
   - Lint verification:
     ```
     /Users/konstantin/.local/bin/uv run ruff check spatial_engine/graph.py spatial_engine/router.py tests/unit/test_routing_engine.py
     All checks passed!
     ```

---

## 2. Logic Chain

1. **Routing Graph Model (`spatial_engine/graph.py`)**:
   - **Nodes**:
     * Representative points of each active space polygon form the primary space nodes.
     * Opening positions form door nodes with prefix `door:{opening_id}`.
     * A virtual node `"outside"` represents exterior access.
   - **Edges**:
     * Space anchors connect to door nodes with Euclidean distance $d = \sqrt{(x_a - x_d)^2 + (y_a - y_d)^2}$.
     * Openings with `"outside"` in their `space_ids` connect to `"outside"` with weight $0.0$.
     * Multi-floor vertical connectors join stops between consecutive floors:
       - Stairs: weight $= 12.0 \times \text{span}$.
       - Lifts: weight $= 15.0\text{ m wait} + 6.0 \times \text{span}$.
   - **Constraint Filtering**:
     * `closed`: Excludes space nodes, opening nodes, and vertical connector edges specified in the closed set.
     * `step_free`: Excludes all stair connectors (`kind in ('stairs', 'stair')`) and non-accessible openings (`step_free == False`).
     * `min_door_width`: Excludes openings with `width_m < min_door_width - 1e-6`.
   - **MultiGraph Support**: Preserves parallel edges between spaces that share both a stairwell and an elevator.

2. **Routing Algorithms & Query Engine (`spatial_engine/router.py`)**:
   - **`shortest_path(graph, start_node, end_node)`**:
     * Runs NetworkX Dijkstra returning `RouteResult(distance, path)`.
     * Implements `__iter__` to allow seamless unpacking `length, path = shortest_path(...)`.
   - **`count_reachable_rooms(building, start_id, target_floor_id, step_free, min_width, closed)`**:
     * Builds constrained graph.
     * Calculates reachable set $R = \text{descendants}(G, \text{start}) \cup \{\text{start}\}$.
     * Counts candidate spaces where `floor_id == target_floor_id` and structural `type == "room"`.
   - **`solve_errand(building, start_id, asset_type, target_room_type, target_floor_id)`**:
     * Leg 1: Single-source Dijkstra from `start_id` to find closest space $v^*$ containing an asset of `asset_type`.
     * Leg 2: Resolves largest room $t^*$ of `target_room_type` on `target_floor_id` by polygon area, then computes Dijkstra shortest path from $v^*$ to $t^*$.
     * Returns `ErrandResult(total_distance, via_space_id, target_space_id, path, ...)`, unpacking cleanly as `(dist, via, target)`.
   - **`evaluate_what_if_door(building, space_a_id, space_b_id, target_floor_id, threshold=1.0)`**:
     * Checks polygon distance $\le 0.6\text{ m}$; raises `ValueError` if distant.
     * Runs single-source Dijkstra from `"outside"` on base graph to obtain baseline exit distances $d_{\text{before}}(r)$ for all rooms on the target floor.
     * Inserts synthetic door `door:virtual_synthetic` at the midpoint of `nearest_points(poly_a, poly_b)` with Euclidean weights to space representative points.
     * Runs single-source Dijkstra from `"outside"` on the updated graph to obtain new distances $d_{\text{after}}(r)$.
     * Counts rooms where $d_{\text{before}}(r) - d_{\text{after}}(r) > \text{threshold} + 10^{-6}$.

3. **Interoperability**:
   - All graph and router functions accept both `Building` dataclass instances and raw JSON dictionaries (`dict[str, Any]`), enabling both high-performance compiled access and flexible integration.

---

## 3. Caveats

- **No Caveats**: All 41 routing benchmark questions in `data/dev/` pass with 100% accuracy, matching official `benchmark/score.py` scoring criteria.
- **Edge cases handled**: Disconnected components, start node equal to destination, missing asset types, distant door creation (>0.6m), and empty closed sets are all verified with targeted test cases.

---

## 4. Conclusion

Milestone 2 (Multi-Floor Routing & Constraint Engine) is completely implemented, verified, and passes all unit and integration test suites:
- Features 6, 7, 8, 9, 10, 11, 12, 13 are fully delivered.
- `spatial_engine/graph.py` and `spatial_engine/router.py` are production-ready with zero external dependencies beyond `networkx` and `shapely`.
- `tests/unit/test_routing_engine.py` provides 30 comprehensive unit tests including an automated end-to-end evaluation of all 41 benchmark routing questions in `data/dev/`.
- 100% pass rate achieved on both unit tests and the 285-test E2E test suite.

---

## 5. Verification Method

To independently verify the implementation:

1. **Run Routing Unit Tests & Benchmark Suite**:
   ```bash
   /Users/konstantin/.local/bin/uv run python tests/unit/test_routing_engine.py
   ```
   *Expected result:* 30 tests ran in ~1.0s, status `OK`.

2. **Run Unified E2E Test Suite**:
   ```bash
   /Users/konstantin/.local/bin/uv run python tests/run_tests.py
   ```
   *Expected result:* 285/285 tests passed across Tiers 1–4, status `ALL TESTS PASSED (100% SUCCESS)`.

3. **Run Code Linting**:
   ```bash
   /Users/konstantin/.local/bin/uv run ruff check spatial_engine/graph.py spatial_engine/router.py tests/unit/test_routing_engine.py
   ```
   *Expected result:* `All checks passed!`.

4. **Inspect Files**:
   - `spatial_engine/graph.py`
   - `spatial_engine/router.py`
   - `tests/unit/test_routing_engine.py`
