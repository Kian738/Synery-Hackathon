# Test Infrastructure Specification: Talk to Your Building (Track 01)

## 1. Overview & Architecture

The testing infrastructure provides an opaque-box, requirement-driven, multi-tier End-to-End (E2E) verification suite covering all 24 features documented in `PROJECT.md`. The suite adheres to rigorous black-box testing principles: tests depend strictly on documented interface contracts, mathematical specifications, competition benchmark scoring rules, and authoritative dataset ground truths.

```
industrial-agents-hackathon-2026/
├── TEST_INFRA.md                          # Test infrastructure architecture & run manual (this file)
├── TEST_READY.md                          # Readiness report & feature checklist
└── tests/
    ├── __init__.py                        # Tests package marker
    ├── helpers.py                         # Authoritative ReferenceOracle, dataset paths, mock REST dispatcher
    ├── run_tests.py                       # Unified test runner with per-tier scorecard reporting
    ├── test_tier1_features.py             # Tier 1: Feature Coverage (>=5 test cases per feature across all 24)
    ├── test_tier2_boundaries.py           # Tier 2: Boundary & Corner Cases (>=5 test cases per feature)
    ├── test_tier3_combinations.py         # Tier 3: Pairwise Cross-Feature Interactions (>=30 combinations)
    └── test_tier4_scenarios.py            # Tier 4: Real-World Operational Scenarios (>=15 industrial workflows)
```

---

## 2. Test Tier Hierarchy & Methodology

### Tier 1: Feature Coverage
- **Objective**: Verify that every individual feature in `PROJECT.md` operates correctly under standard operational conditions.
- **Quota**: At least 5 distinct test cases per feature across all 24 features (total $\ge 120$ test cases).
- **Scope**:
  - Spatial Geometry (Features 1–5: `largest_room`, `floor_area_total`, `straight_line_3d`, `room_stacked`, `shared_walls_count`).
  - Routing & Constraints (Features 6–13: multi-floor graph, step-free filtering, door clearance, `wide_delivery_count`, `step_free_reachable_count`, `errand`, `what_if_door`, dynamic closures).
  - Benchmark & Solver Interfaces (Features 14–17: deterministic classifier, dev accuracy $\ge 95\%$, submission generator, `BENCHMARK.md` docs).
  - Interactive Visualizer REST APIs (Features 18–22: layout hierarchy, exploded slider, animated route waypoints, live dispatch editor, voice-assisted navigation).
  - Test Suite & Adversarial Integrity (Features 23–24: runner diagnostics, encoding & escaping integrity).

### Tier 2: Boundary & Corner Cases
- **Objective**: Probe edge conditions, mathematical boundaries, invalid configurations, and zero/extreme dimensions.
- **Quota**: At least 5 boundary test cases per feature (total $\ge 120$ test cases).
- **Scope**:
  - Geometric extremities: microscopic rooms ($< 0.01\text{ m}^2$), massive factory halls ($> 50,000\text{ m}^2$), concave and L-shaped polygons, negative floor elevations (sub-basements).
  - Topological corner cases: disconnected rooms, zero-clearance door thresholds ($0.0\text{ m}$), extreme door thresholds ($100.0\text{ m}$), closing all building exits.
  - Ambiguity resolution: duplicate room names/refs (e.g., OpenStreetMap duplicate "Saal" or "Generic room"), runner-up rejection order.
  - Strict benchmark single-number constraints: extraneous numbers, Markdown asterisks, unit formatting (`m²` vs `m^2`).
  - REST error handling: missing query parameters, malformed JSON, out-of-range coordinates, and unparseable voice transcripts.

### Tier 3: Cross-Feature Combinations
- **Objective**: Verify compound and pairwise interactions between interdependent subsystems.
- **Quota**: At least 30 integration test cases.
- **Scenarios**:
  - Multi-Floor + Step-Free + Minimum Door Width (wheelchair transit through lifts across wide double doors).
  - Multi-Floor Errand + Connector Closures (rerouting through alternative elevators when stairs are closed).
  - What-If Door + Dynamic Connector Closures (evaluating egress improvement when secondary exits are blocked).
  - Geometric Consistency: `largest_room` area $\le$ `floor_area_total`; shared walls only between co-floor spaces.
  - Visualizer REST cycle: load building $\to$ query route $\to$ mark closure $\to$ punched-through door $\to$ route diff.
  - Benchmark solver regex extraction against official `benchmark/score.py` validator.

### Tier 4: Real-World Operational Scenarios
- **Objective**: Execute full-system simulations reflecting authentic factory operations, safety incidents, and industrial logistics.
- **Quota**: At least 15 comprehensive workflows.
- **Scenarios**:
  - Realistic Automated Guided Vehicle (AGV) factory floor dispatch across `proc-factory-dev-003`.
  - Industrial emergency evacuation audit: fire in central stairwell blocks primary egress; compute emergency routes to outside.
  - Heavy cargo forklift delivery with minimum clearance and lift load constraints.
  - Multi-floor warehouse inventory inspection run.
  - Complete 40-building dev benchmark dataset evaluation sweep achieving $\ge 95\%$ accuracy.
  - Test submission pipeline verification: strict validation of 145 question IDs and non-empty committed answer lines.
  - Voice-guided technician maintenance cycle.

---

## 3. Authoritative Source of Expected Output (Oracle Strategy)

Every test case derives its expected output from an authoritative source:
1. **Reference Datasets**: Ground truth answers and tolerances in `data/dev/*/questions.jsonl` provided by the competition organizers.
2. **Official Benchmark Scorer**: Exact regex patterns, numerical extraction, and tolerance logic from `benchmark/score.py`.
3. **Reference Oracle (`tests/helpers.py`)**: Exact mathematical implementations of polygon surface integration, 3D Euclidean centroid distances, boundary buffering ($0.35\text{ m}$ buffer, $1.0\text{ m}$ threshold), and NetworkX multi-floor graph construction.
4. **Progressive Testability**:
   - Tests verify against `spatial_engine` and `visualizer` when implemented.
   - For modules in active milestone development, tests automatically fall back to reference oracle verification or skip with clear milestone status annotations.

---

## 4. Execution Manual

The test suite requires zero external dependencies beyond the project's standard virtual environment.

### Single-Command Execution (All Tiers)
```bash
/Users/konstantin/.local/bin/uv run python tests/run_tests.py
```

### Running Specific Tiers
```bash
# Run Tier 1 only (Feature Coverage)
/Users/konstantin/.local/bin/uv run python tests/run_tests.py --tier 1

# Run Tier 2 only (Boundary & Corner Cases)
/Users/konstantin/.local/bin/uv run python tests/run_tests.py --tier 2

# Run Tier 3 only (Cross-Feature Combinations)
/Users/konstantin/.local/bin/uv run python tests/run_tests.py --tier 3

# Run Tier 4 only (Real-World Operational Scenarios)
/Users/konstantin/.local/bin/uv run python tests/run_tests.py --tier 4
```

### Verbose Execution
```bash
/Users/konstantin/.local/bin/uv run python tests/run_tests.py --verbose
```
