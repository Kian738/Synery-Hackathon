# Handoff Report — Milestone 3: Deterministic Benchmark Solver & Submission Deliverables

**Agent:** `teamwork_preview_worker` (Milestone 3 Implementer / QA)  
**Parent Task ID:** `99a36772-9103-445c-a001-17463bb30980`  
**Date:** 2026-10-24  
**Handoff Type:** Hard (Complete)

---

## 1. Observation

### 1.1 Requirements & Delivered Files
Under exclusive ownership for Milestone 3, the following 5 deliverables were produced and verified:
1. `spatial_engine/solver.py`: Deterministic natural language question classifier and solver across all 9 competition categories with strictly compliant committed `Answer: ...` lines.
2. `benchmark_runner.py`: Universal evaluation CLI runner evaluating single buildings or full datasets, scoring with `benchmark.score.score_reply`, and outputting submission CSVs.
3. `submission.csv`: Complete ground truth formatted submission for all 145 test set questions in `data/test/questions.csv`.
4. `BENCHMARK.md`: Comprehensive benchmark documentation detailing single CLI command evaluation for unseen datasets.
5. `tests/unit/test_solver.py`: 28 unit tests covering all question solvers, classification, formatting constraints, and runner CLI operations.

### 1.2 Evaluation Results & Tool Verifications
- **Development Dataset (`data/dev/`)**:
  - Command: `uv run python benchmark_runner.py data/dev questions.jsonl`
  - Result: **138 / 138 (100.0%) correct** across all 40 dev buildings in **2.09 seconds**.
  - Category breakdown:
    * `errand`: 19 / 19 (100.0%)
    * `floor_area_total`: 31 / 31 (100.0%)
    * `largest_room`: 20 / 20 (100.0%)
    * `room_stacked`: 9 / 9 (100.0%)
    * `shared_walls_count`: 24 / 24 (100.0%)
    * `step_free_reachable_count`: 1 / 1 (100.0%)
    * `straight_line_3d`: 13 / 13 (100.0%)
    * `what_if_door`: 2 / 2 (100.0%)
    * `wide_delivery_count`: 19 / 19 (100.0%)
- **Official Evaluator Module**:
  - Command: `uv run python -m benchmark.evaluate data/dev --agent spatial_engine.solver:answer`
  - Result: **138 / 138 (100.0%) passed**.
- **Test Set Submission (`submission.csv`)**:
  - Command: `uv run python benchmark_runner.py data/test data/test/questions.csv --output submission.csv`
  - Total rows: 145 rows (plus 1 header line `question_id,answer`).
  - Validation:
    * All 145 question IDs exactly match `data/test/submission_template.csv` in identical order.
    * Every answer is non-empty and contains a valid committed `Answer: ...` line.
    * Numeric answers contain strictly one number (`len(numbers_in(text)) == 1`).
    * `largest_room` answers contain room name/ref and area in `m²`.
- **Unit and Consolidated E2E Test Suite**:
  - Command: `uv run python -m unittest tests/unit/test_solver.py -v`
  - Result: **28 / 28 passed** in 2.72s.
  - Command: `uv run python tests/run_tests.py`
  - Result: **285 / 285 passed (100% success)** across Tiers 1-4 in 8.80s.

---

## 2. Logic Chain

### 2.1 Deterministic Question Classification
- In `spatial_engine/solver.py`, `classify_question` classifies question text by identifying canonical keyphrases:
  - `floor_area_total`: `"total floor area"`
  - `errand`: `"grab a"` or `"carry it to"`
  - `shared_walls_count`: `"share a wall with it"` or `"soundproofing"`
  - `straight_line_3d`: `"straight-line distance"` or `"wireless sensor link"`
  - `room_stacked`: `"directly below"` or `"directly above"`
  - `what_if_door`: `"what if we add a door"`
  - `step_free_reachable_count`: `"out of service"` or `"wheelchair user"`
  - `wide_delivery_count`: `"can it be delivered"`, `"delivered"`, or `"moving a "`
  - `largest_room`: `"largest"` and (`"how big"`, `"m²"`, or `"<area>"`)
- Tested across all 138 dev questions and all 145 test questions with **0 mismatches (100% precision)**.

### 2.2 Robust Space & Floor Entity Extraction
- Floor level parsing (`parse_floor_level`):
  - Normalizes "Ground floor" $\to 0$, "Floor N" $\to N$, "Basement N" $\to -N$, and signed integers $\to \text{int}$.
- Space entity resolution (`resolve_space_by_text`):
  - Extracts room name and floor name from expressions like `Toilet 0.36 (Ground floor)` or `Generic room -1.14 (Basement 1)`.
  - Filters candidates on the target floor level:
    1. Exact name match
    2. Exact reference match
    3. Word boundary / token match (e.g. matching ref `0.34` inside string `Office 0.34`)
    4. Substring inclusion
  - Tested across 102/102 room references in `data/dev` with 100% resolution accuracy.

### 2.3 Strict Benchmark Scoring Compliance (`benchmark/score.py`)
- Regex match: `^\W*answer\W*:\s*(.+)$`
- Single number constraint: In `benchmark/score.py:61`, number questions require `len(numbers) == 1`.
  - Solver formats numeric answers as: `Answer: {val}` (e.g. `Answer: 106.3` or `Answer: 4`).
  - No extraneous numbers, units, or floor descriptions are emitted in the committed line.
- Dual space + area constraint: For `largest_room`, `score.py:65` checks room label precedence and area within 5%.
  - Solver formats as: `Answer: {space_label}, {area:.1f} m²`.
  - Room label incorporates `ref` disambiguation (`f"{lbl} {space.ref}"` if not already present) to prevent collisions in OSM duplicate names.

### 2.4 High-Performance Caching
- `_BUILDING_CACHE` in `spatial_engine/solver.py` caches parsed `Building` models keyed by absolute directory path.
- Reduces repetitive JSON parsing and Shapely polygon construction during batch evaluations, accelerating 138 dev queries from 5.1s to 2.09s.

---

## 3. Caveats

1. **Test Set Ground Truth Held-Out**: Official ground truth answers for `data/test/` are held out by the organizers. However, all 145 test questions were parsed, resolved against their building geometries, and produced valid format-compliant committed answer lines without errors.
2. **Global Coordinate Alignment in Swiss Dwellings**: Swiss Dwellings buildings are floor-local; as designed by the competition authors, `room_stacked` questions are restricted to procedural and OSM buildings.
3. **Connector Closures**: `step_free_reachable_count` relies on resolving connector names (e.g. `Lift 1`) against `building.connectors`, which is fully supported and verified.

---

## 4. Conclusion

- **Milestone 3 is 100% complete**.
- `spatial_engine/solver.py` deterministically answers all 9 spatial reasoning question categories with **100.0% accuracy on dev (138/138)** at 0 token cost in ~2 seconds.
- `benchmark_runner.py` provides a unified CLI for evaluating unseen buildings and datasets.
- `submission.csv` is fully generated, validated against `submission_template.csv`, and ready for the judge app.
- `BENCHMARK.md` clearly documents single-command execution.
- All 28 unit tests in `tests/unit/test_solver.py` and all 285 consolidated E2E tests pass.

---

## 5. Verification Method

To independently verify all Milestone 3 deliverables:

1. **Run Unit Test Suite**:
   ```bash
   uv run python -m unittest tests/unit/test_solver.py -v
   ```
   *Expected: 28 tests pass in ~2.7s.*

2. **Evaluate Full Development Benchmark (`data/dev/`)**:
   ```bash
   uv run python benchmark_runner.py data/dev questions.jsonl
   ```
   *Expected: 138/138 correct (100.0%) across all 9 categories.*

3. **Verify Official Benchmark Evaluator Integration**:
   ```bash
   uv run python -m benchmark.evaluate data/dev --agent spatial_engine.solver:answer
   ```
   *Expected: All 138 questions pass (`OK`).*

4. **Verify Generated `submission.csv` Deliverable**:
   ```bash
   uv run python -c "
   import csv
   from benchmark.score import ANSWER_LINE

   with open('data/test/submission_template.csv') as f:
       template_ids = [r['question_id'] for r in csv.DictReader(f)]

   with open('submission.csv') as f:
       sub_rows = list(csv.DictReader(f))

   assert len(sub_rows) == 145
   assert [r['question_id'] for r in sub_rows] == template_ids
   for r in sub_rows:
       assert r['answer'].strip()
       assert ANSWER_LINE.findall(r['answer'])
   print('submission.csv verified: 145 valid answers matching template.')
   "
   ```

5. **Run Consolidated E2E Test Suite**:
   ```bash
   uv run python tests/run_tests.py
   ```
   *Expected: 285/285 tests pass (100% success).*
