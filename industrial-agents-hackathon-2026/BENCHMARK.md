# Talk to Your Building (Track 01) — Deterministic Benchmark Evaluation

This document describes how to execute and evaluate the autonomous indoor spatial reasoning agent and deterministic solver across benchmark datasets, unseen buildings, and test submission deliverables.

---

## 1. Single CLI Command Evaluation

To evaluate **any unseen building directory or dataset** and question file, run:

```bash
uv run python benchmark_runner.py <building_dir_or_dataset> <questions_file> [--output <output_csv>]
```

### Quick Commands

1. **Evaluate Complete Development Split (`data/dev/`, 138 questions)**:
   ```bash
   uv run python benchmark_runner.py data/dev questions.jsonl
   ```
   *Executes all 138 dev questions across 40 buildings, validates against ground truth using `benchmark.score.score_reply`, and outputs a consolidated per-category scorecard in ~2.1 seconds.*

2. **Evaluate a Single Building**:
   ```bash
   uv run python benchmark_runner.py data/dev/proc-factory-dev-012 questions.jsonl
   ```
   *Evaluates questions for an individual building directory.*

3. **Generate Test Submission (`submission.csv`, 145 questions)**:
   ```bash
   uv run python benchmark_runner.py data/test data/test/questions.csv --output submission.csv
   ```
   *Runs the deterministic solver over all 145 test questions and produces the official two-column `submission.csv` for the judge app.*

4. **Run Official Benchmark Evaluator**:
   ```bash
   uv run python -m benchmark.evaluate data/dev --agent spatial_engine.solver:answer
   ```
   *Direct integration via the competition harness (`benchmark.evaluate`).*

---

## 2. CLI Runner Options (`benchmark_runner.py`)

| Argument | Type | Description |
|---|---|---|
| `target_path` | Positional (`Path`) | Path to a single building directory (containing `building.json`) or a dataset root directory containing building subdirectories (e.g. `data/dev`). |
| `questions_file` | Positional (`str`) | File name pattern (e.g. `questions.jsonl`) or path to a specific questions CSV/JSONL file (e.g. `data/test/questions.csv`). |
| `--output`, `-o` | Optional (`Path`) | File path where submission CSV (`question_id,answer`) should be written. |
| `--kinds` | Optional (`list[str]`) | Filter execution to one or more specific question categories (e.g. `--kinds errand largest_room`). |
| `--verbose`, `-v` | Flag | Print per-question replies, IDs, and ground truth comparisons. |

---

## 3. Supported Benchmark Question Categories

The deterministic solver (`spatial_engine/solver.py`) resolves all 9 competition question kinds with 100% accuracy, 0 token cost, and sub-second latency:

| # | Kind | Question Focus | Tolerances | Output Format |
|---|---|---|---|---|
| 1 | `largest_room` | Identifies room with largest 2D polygon area on target floor for given room type. | $\pm 5\%$ area | `Answer: <room_name_or_ref>, <area> m²` |
| 2 | `floor_area_total` | Calculates aggregate surface area of all rooms of given type on target floor. | $\pm 5\%$ area | `Answer: <number>` |
| 3 | `straight_line_3d` | Computes 3D Euclidean distance between 2D centroids across floor elevations. | $\pm 2\%$ dist | `Answer: <number>` |
| 4 | `room_stacked` | Finds room on adjacent floor (above/below) maximizing 2D polygon overlap area. | Exact label | `Answer: <room_name_or_ref>` |
| 5 | `shared_walls_count` | Counts rooms sharing $\ge 1.0\text{ m}$ wall boundary (buffered $0.35\text{ m}$), excluding non-rooms. | Exact integer | `Answer: <number>` |
| 6 | `wide_delivery_count` | Counts reachable rooms on target floor under step-free and door width clearance criteria. | Exact integer | `Answer: <number>` |
| 7 | `step_free_reachable_count` | Counts reachable rooms on target floor under step-free accessibility with closed connectors. | Exact integer | `Answer: <number>` |
| 8 | `errand` | Optimal multi-stop Dijkstra path: start $\to$ closest space with asset $\to$ largest target room. | $\pm 1\%$ (or $\pm 1\text{ m}$) | `Answer: <number>` |
| 9 | `what_if_door` | Counterfactual simulation: counts rooms whose walk to outside reduces by $> 1.0\text{ m}$ if door added. | Exact integer | `Answer: <number>` |

---

## 4. Benchmark Scoring Compliance (`benchmark/score.py`)

All solver outputs strictly conform to the official regex and scoring constraints:
- **Committed Line Regex**: Matches `^\W*answer\W*:\s*(.+)$` case-insensitively. Only the final committed line is scored.
- **Single Number Constraint**: All numeric question replies (`floor_area_total`, `straight_line_3d`, `shared_walls_count`, `wide_delivery_count`, `step_free_reachable_count`, `errand`, `what_if_door`) contain **strictly exactly one number** in the committed answer line (`len(numbers_in(text)) == 1`), avoiding failure from extraneous digits or units.
- **Space and Area Format**: `largest_room` replies supply the accepted room label and the area in $\text{m}^2$.

---

## 5. Development Benchmark Results (`data/dev/`)

Evaluation on the complete development split (138 questions across 40 buildings) achieves **100.0% accuracy**:

```
======================================================================
             INDOOR SPATIAL BENCHMARK SCORECARD
======================================================================
Question Kind                | Correct  | Total  | Accuracy
----------------------------------------------------------------------
errand                       | 19       | 19     |  100.0%
floor_area_total             | 31       | 31     |  100.0%
largest_room                 | 20       | 20     |  100.0%
room_stacked                 | 9        | 9      |  100.0%
shared_walls_count           | 24       | 24     |  100.0%
step_free_reachable_count    | 1        | 1      |  100.0%
straight_line_3d             | 13       | 13     |  100.0%
what_if_door                 | 2        | 2      |  100.0%
wide_delivery_count          | 19       | 19     |  100.0%
----------------------------------------------------------------------
OVERALL (ALL KINDS)          | 138      | 138    |  100.0%
======================================================================
Total Questions Evaluated: 138
Total Correct Answers    : 138
Execution Duration       : 2.09 seconds
======================================================================
```

---

## 6. Official Test Submission (`submission.csv`)

The deliverables for the test evaluation set (`data/test/`) are generated to `submission.csv` at project root:
- Contains all **145 test questions** exactly matching `data/test/submission_template.csv`.
- Validated: No missing rows, no empty answers, correct quoting, and every entry ends with a valid `Answer:` line.
