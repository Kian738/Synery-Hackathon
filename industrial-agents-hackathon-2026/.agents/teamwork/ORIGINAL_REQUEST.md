# Original User Request

## 2026-10-24T13:56:56Z

Autonomous indoor spatial reasoning agent and interactive navigation system for industrial complexes and factory halls (Industrial Agents Hackathon 2026 — Track 01: Talk to Your Building). The system deterministically solves complex geometric, topological, and reachability benchmark queries with 100% accuracy, and delivers an interactive multi-floor visualizer with voice-driven navigation and dynamic facility dispatching.

Working directory: /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026
Integrity mode: development

## Verification Resources

- Official benchmark scorer: `benchmark/score.py`
- Official evaluation runner: `benchmark/evaluate.py`
- Starter agent and graph model: `starter_agent/`
- Reference datasets:
  - Development dataset: `data/dev/` (40 buildings with reference answers in `questions.jsonl` and `questions_basic.jsonl`)
  - Test evaluation set: `data/test/` (40 buildings with 145 benchmark questions)
  - Submission template: `data/test/submission_template.csv`

## Requirements

### R1. Deterministic Spatial Reasoning & Benchmark Solver
Provide an automated solver and agent interface capable of answering all 9 benchmark question categories (`largest_room`, `floor_area_total`, `wide_delivery_count`, `errand`, `shared_walls_count`, `step_free_reachable_count`, `room_stacked`, `straight_line_3d`, `what_if_door`) across any building adhering to the competition schema. All answers must strictly conform to the format required by `benchmark/score.py` (including precise `Answer: ...` commitment lines).

### R2. Multi-Floor Routing & Constraint Engine
Provide a robust pathfinding engine handling multi-floor routing across stairs and lifts, step-free accessibility constraints, door clearance thresholds, multi-stop errands, and dynamic closures of spaces or connectors.

### R3. Interactive Visualizer & Real-Time Operational Dispatcher
Provide a graphical interface displaying building layouts across all elevation levels, asset and equipment locations, and animated navigation routes. The interface must allow real-time layout updates (adding openings, toggling closures, updating obstacle zones) and support voice-assisted interaction for hands-free industrial navigation.

### R4. Benchmark Execution & Submission Deliverables
Generate a complete, strictly compliant `submission.csv` for all 145 test questions in `data/test/questions.csv`. Provide a documented single-command benchmark runner in `BENCHMARK.md` capable of evaluating any unseen building dataset end-to-end without manual intervention.

## Acceptance Criteria

### Benchmark Accuracy & Score
- [ ] Automated evaluation on all questions in `data/dev/` via `benchmark/score.py` achieves >= 95% accuracy across all 9 question kinds.
- [ ] The generated `submission.csv` contains all 145 test question IDs from `data/test/submission_template.csv` with properly quoted non-empty answers ending in a valid `Answer:` line.
- [ ] Execution on the entire 145-question test set completes without crashes or timeouts.

### Spatial Engine Correctness
- [ ] Area calculations match geometric polygon surfaces within +- 5%.
- [ ] Euclidean 3D straight-line distances between floor centroids match within +- 2%.
- [ ] Routing distances match optimal Dijkstra path lengths within +- 1% (or +- 1 m).
- [ ] Shared wall counts, wide delivery reachable counts, step-free counts, and what-if door room counts match ground truth exactly.

### Operational Application & Documentation
- [ ] An interactive web application runs locally, visualizes 2D/3D stacked floor plans, and animates computed routes.
- [ ] Live map modification (e.g. adding a door or reporting a closed lift) dynamically alters subsequent route calculations and visual feedback.
- [ ] `BENCHMARK.md` exists and documents the exact single CLI command to run on a new building directory and question file.
