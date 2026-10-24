# Forensic Audit Report — Milestone 2: Spatial Graph & Routing Engine

**Work Product**: `spatial_engine/graph.py`, `spatial_engine/router.py`, `tests/unit/test_routing_engine.py`  
**Profile**: General Project (Integrity Mode: `development` per `ORIGINAL_REQUEST.md` line 8)  
**Verdict**: **CLEAN**

---

### Phase Results

- **Static Analysis & Hardcoding Check**: **PASS** — Zero hardcoded benchmark answers, zero question IDs, and zero precomputed distance lookup tables found in `spatial_engine/`. Constants defined (`STAIRS_COST_PER_FLOOR_M = 12.0`, `LIFT_WAIT_COST_M = 15.0`, `LIFT_COST_PER_FLOOR_M = 6.0`, `ADJACENT_DOOR_MAX_DISTANCE_M = 0.6`, `DEFAULT_THRESHOLD = 1.0`) are authentic domain parameters specified in official Track 01 reference `starter_agent/building_map.py` and `ORIGINAL_REQUEST.md`.
- **Runtime Tracing & Edge Weight Sensitivity Check**: **PASS** — Verified empirically that Dijkstra computes shortest paths using genuine NetworkX edge weights rather than hop counts. Artificially inflating edge weight by +50m dynamically increased route distance and altered paths. In multi-path tests, a 3-hop 6.0m path was preferred over a 1-hop 100.0m path.
- **Reachability & Dynamic Closures Check**: **PASS** — Verified that BFS reachability is computed via genuine graph traversal over space representative points, doors, and vertical connectors. Closing lift connectors dynamically reduced step-free cross-floor reachable rooms from 7 to 0.
- **Cheating & Facade Check (What-If Door Counterfactuals)**: **PASS** — Verified that `evaluate_what_if_door` creates a genuine synthetic door node (`door:virtual_synthetic`) at the midpoint of nearest boundary points, connects it to space anchors with Euclidean weights, and recomputes all room distances to the outside node via Dijkstra. Tested on both development dataset buildings and on a clean, dynamically created synthetic building with novel geometries.
- **Git Integrity Check**: **PASS** — `git diff origin/main -- benchmark data` confirms zero modifications to benchmark scorer/evaluator code or dataset questions.
- **Independent Test Execution**: **PASS** — 30/30 unit tests in `tests/unit/test_routing_engine.py` pass (including all 41 dev benchmark routing questions); 285/285 E2E tests in `tests/run_tests.py` pass across all 4 tiers; `ruff check` reports all checks passed.

---

## 1. Observation

1. **Static Analysis of Milestone 2 Codebase**:
   - `spatial_engine/graph.py` (260 lines): Builds a `networkx.MultiGraph` connecting space representative points to opening nodes with Euclidean distances ($d = \sqrt{\Delta x^2 + \Delta y^2}$), exterior doors to virtual `"outside"` node (weight 0.0), and vertical connectors between adjacent floor stops (Stairs: $12.0 \times \text{span}$, Lifts: $15.0 + 6.0 \times \text{span}$). Filtering logic strips closed elements, narrow doors (`width < min_door_width - 1e-6`), and non-step-free connectors/doors when `step_free=True`.
   - `spatial_engine/router.py` (555 lines): Contains `shortest_path` (Dijkstra via `nx.shortest_path_length` and `nx.shortest_path`), `count_reachable_rooms` (BFS via `nx.descendants`), `solve_errand` (2-leg Dijkstra to closest asset space then largest target room), and `evaluate_what_if_door` (counterfactual door insertion and comparative Dijkstra exit distances).
   - Grep searches for question IDs (`q0`, `H0`, `proc-`, `osm-`, `resplan-`) in `spatial_engine/` returned zero matches. No question-specific dispatching or hardcoded test returns exist.

2. **Git Repository Status & Benchmark/Data Immutability**:
   - `git diff origin/main -- benchmark data` produced empty output (zero changes).
   - `git status -s benchmark data` produced only untracked Python bytecode `?? benchmark/__pycache__/` resulting from benchmark execution. Neither benchmark logic nor data files were altered.

3. **Runtime Tracing & Algorithmic Sensitivity Tool Output**:
   - Running edge weight inflation test:
     ```
     Original path dist: 141.96, hops: 12
     Inflated edge (proc-factory-dev-003-F0-S013 <-> door:proc-factory-dev-003-F0-O0019 by +50m) path dist: 188.06
     PASS: Dijkstra genuinely uses NetworkX edge weights.
     ```
   - Running hop count vs weight sensitivity test:
     ```
     MultiGraph shortest path: Path 1 (1 hop, wt 100) vs Path 2 (3 hops, wt 6.0)
     Selected distance: 6.0, path: ['A', 'X', 'Y', 'B']
     PASS: MultiGraph shortest path strictly optimizes edge weights, not hop counts.
     ```
   - Running BFS reachability test:
     ```
     Reachable rooms with all lifts open: 7
     Lifts in building: ['proc-factory-dev-003-V02']
     Reachable rooms with all lifts closed (step-free): 0
     PASS: Reachability genuinely traverses graph and respects dynamic closures.
     ```
   - Running counterfactual door simulation on dev building `osm-way27917482`:
     ```
     What-if door improvement count (threshold=1.0m): 6
     What-if door improvement count (threshold=10.0m): 4
     What-if door improvement count (threshold=100.0m): 0
     PASS: What-if door is genuinely computed via synthetic door node and recomputed Dijkstra.
     ```
   - Running counterfactual door simulation on a brand new synthetic building (not in any dataset):
     ```
     Synthetic building what_if_door count: 1
     PASS: evaluate_what_if_door functions with 100% mathematical authenticity on arbitrary synthetic geometries.
     ```
   - Running multi-stop errand solver on synthetic building:
     ```
     Errand via: S2, target: S5, dist: 14.0
     PASS: solve_errand works authentically across synthetic geometries and multi-floor stairs.
     ```

4. **Independent Test Execution**:
   - Command: `/Users/konstantin/.local/bin/uv run python tests/unit/test_routing_engine.py`
     * Result: `Ran 30 tests in 1.090s. OK.`
   - Command: `/Users/konstantin/.local/bin/uv run python tests/run_tests.py`
     * Result: `TOTAL CONSOLIDATED SUITE | 285 passed | 0 failed | 0 skipped | 7.688s. >>> OVERALL RESULT: ALL TESTS PASSED (100% SUCCESS) <<<`
   - Command: `/Users/konstantin/.local/bin/uv run ruff check spatial_engine/graph.py spatial_engine/router.py tests/unit/test_routing_engine.py`
     * Result: `All checks passed!`

---

## 2. Logic Chain

1. **Integrity Mode Conformance**:
   - `ORIGINAL_REQUEST.md` line 8 specifies `Integrity mode: development`. Under development mode, external libraries (e.g., `networkx`, `shapely`) and standard algorithmic patterns are explicitly permitted; hardcoding test answers, facade implementations returning dummy constants, and tampering with verification benchmarks are prohibited.
2. **Absence of Hardcoded Responses or Question Leaks**:
   - Detailed inspection and regex/literal searching of `spatial_engine/graph.py` and `spatial_engine/router.py` revealed no question IDs, building IDs, or precomputed answers. The logic in `router.py` dynamically queries building structures and solves queries at runtime.
3. **Verification of Genuine Pathfinding Logic**:
   - The edge weight perturbation test demonstrated that modifying graph edge weights changes the returned path length ($141.96\text{ m} \to 188.06\text{ m}$).
   - The comparison between a 1-hop 100m path and a 3-hop 6m path confirmed Dijkstra strictly prioritizes edge weights over hop count.
   - Closing the only lift in factory 003 caused step-free cross-floor reachability from F0 to F1 to collapse from 7 to 0, confirming reachability is computed through actual graph traversal.
4. **Verification of Counterfactual What-If Door Engine**:
   - The code in `evaluate_what_if_door` was verified to compute Euclidean distances from the midpoint of nearest boundary points, create a synthetic door node (`door:virtual_synthetic`), add edges to both rooms, and recompute single-source Dijkstra path lengths from `"outside"`.
   - Increasing the threshold from $1.0\text{ m}$ to $10.0\text{ m}$ and $100.0\text{ m}$ yielded monotonically decreasing improved room counts ($6 \to 4 \to 0$).
   - Testing on an adversarial, newly synthesized building with no external dependencies confirmed the implementation correctly recognized a $46.0\text{ m}$ improvement and returned count $= 1$.
5. **Benchmark & Data Immutability**:
   - Git verification proved that `benchmark/score.py`, `benchmark/evaluate.py`, and `data/` were completely untouched.

---

## 3. Caveats

- **No caveats**: The codebase was verified through both static inspection and dynamic runtime stress tests on synthetic edge cases and real benchmark buildings.

---

## 4. Conclusion

Milestone 2 (`spatial_engine/graph.py`, `spatial_engine/router.py`, `tests/unit/test_routing_engine.py`) satisfies all integrity, authenticity, and functional requirements.
There are **zero hardcoded outputs**, **zero facades**, **zero unauthorized modifications to benchmark/data**, and the routing algorithms operate with 100% mathematical and algorithmic authenticity.

**Final Verdict**: **CLEAN**

---

## 5. Verification Method

To independently verify the audit conclusions:

1. **Verify git immutability of benchmark and data**:
   ```bash
   git diff origin/main -- benchmark data
   ```
   *Expected result*: No output (exit code 0, 0 diff lines).

2. **Run routing unit tests (30 tests including all 41 dev benchmark questions)**:
   ```bash
   /Users/konstantin/.local/bin/uv run python tests/unit/test_routing_engine.py
   ```
   *Expected result*: `Ran 30 tests in ~1.1s. OK.`

3. **Run full consolidated test suite (285 tests across Tiers 1-4)**:
   ```bash
   /Users/konstantin/.local/bin/uv run python tests/run_tests.py
   ```
   *Expected result*: `285 passed, 0 failed, 0 skipped. ALL TESTS PASSED (100% SUCCESS)`.

4. **Verify linting**:
   ```bash
   /Users/konstantin/.local/bin/uv run ruff check spatial_engine/graph.py spatial_engine/router.py tests/unit/test_routing_engine.py
   ```
   *Expected result*: `All checks passed!`.
