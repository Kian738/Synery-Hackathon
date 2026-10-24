# BENCHMARK & REPRODUCIBILITY GUIDE
## Track 01: Talk to Your Building (Industrial Agents Hackathon 2026)

This document provides complete instructions for executing the spatial reasoning engine, running the official benchmark evaluations, verifying the 288-test E2E test suite, launching the interactive 3D digital twin visualizer, and inspecting final competition deliverables.

---

## 1. Quick Start Commands

All commands can be executed directly from the project root directory (`/Users/konstantin/Programmation/Hackathon/Je_regrette_rien`):

| Purpose | Single Command |
|---|---|
| **E2E Test Suite (288 tests)** | `uv run --project industrial-agents-hackathon-2026 python talk_to_your_building/tests/run_all_tests.py` |
| **Official Dev Evaluation (138/138, 100%)** | `uv run --project industrial-agents-hackathon-2026 python -m benchmark.evaluate industrial-agents-hackathon-2026/data/dev --agent talk_to_your_building.agent:solve_question` |
| **Generate Official Submission CSV (145/145)** | `uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.cli --question-file industrial-agents-hackathon-2026/data/test/questions.csv --submission-csv talk_to_your_building/submission.csv` |
| **Run CLI on any Unseen Building & Question File** | `uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.cli --building-dir <path/to/building> --question-file <path/to/questions.jsonl>` |
| **Interactive Digital Twin Server** | `uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.server --port 8000` |

---

## 2. CLI Benchmark Runner (`talk_to_your_building.cli`)

The system provides a robust command-line interface supporting single-question queries, batch question evaluation, and automatic building resolution.

### A. Run on a Specific Building Directory and Question File
To evaluate a batch of benchmark questions in `.jsonl` or `.csv` format against an unseen building:
```bash
uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.cli \
  --building-dir industrial-agents-hackathon-2026/data/dev/proc-factory-dev-003 \
  --question-file industrial-agents-hackathon-2026/data/dev/proc-factory-dev-003/questions.jsonl
```
**Example output:**
```
proc-factory-dev-003-H01: Answer: Kitchen 1.14, 28.00 m²
proc-factory-dev-003-H02: Answer: 171.65
proc-factory-dev-003-H03: Answer: 7
proc-factory-dev-003-H04: Answer: 132.35
proc-factory-dev-003-H05: Answer: 7
```

### B. Run a Single Natural-Language Query
```bash
uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.cli \
  --building-dir industrial-agents-hackathon-2026/data/dev/proc-factory-dev-003 \
  --question "Which is the largest kitchen on the floor 1, and how big is it in m²? Finish with a line 'Answer: <room name or number>, <area> m²'."
```
**Output:**
```
Answer: Kitchen 1.14, 28.00 m²
```

### C. Batch Evaluation Across Multiple Buildings with Submission Output
When given an aggregated questions file containing `building_id` references (such as `data/test/questions.csv`), the CLI automatically locates each building directory and outputs the scored submission CSV:
```bash
uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.cli \
  --question-file industrial-agents-hackathon-2026/data/test/questions.csv \
  --submission-csv talk_to_your_building/submission.csv \
  --output agent_output/test_results.json
```

---

## 3. Official Benchmark Evaluation (`benchmark.evaluate`)

The official evaluation runner provided by the hackathon evaluates the agent against reference answers using `benchmark/score.py`.

### Evaluating the Development Split (`data/dev/`)
```bash
uv run --project industrial-agents-hackathon-2026 python -m benchmark.evaluate \
  industrial-agents-hackathon-2026/data/dev \
  --agent talk_to_your_building.agent:solve_question
```

### Development Split Accuracy Scorecard
Tested across all 40 development buildings and 138 benchmark questions:

| Category | Description | Correct / Total | Accuracy |
|---|---|:---:|:---:|
| `errand` | Multi-stop shortest path (start → nearest asset → target room) | 19 / 19 | **100.0%** |
| `floor_area_total` | Summed polygon area for room type on floor | 31 / 31 | **100.0%** |
| `largest_room` | Maximal polygon area space on floor | 20 / 20 | **100.0%** |
| `room_stacked` | 2D polygon intersection of vertically stacked spaces | 9 / 9 | **100.0%** |
| `shared_walls_count` | Adjacent rooms sharing ≥ 1.0 m buffered boundary | 24 / 24 | **100.0%** |
| `step_free_reachable_count` | Reachability under elevator / connector closures | 1 / 1 | **100.0%** |
| `straight_line_3d` | 3D Euclidean distance between floor centroids | 13 / 13 | **100.0%** |
| `what_if_door` | Counterfactual doorway insertion distance delta | 2 / 2 | **100.0%** |
| `wide_delivery_count` | Step-free reachability with door clearance constraints | 19 / 19 | **100.0%** |
| **OVERALL TOTAL** | **Consolidated Development Benchmark Score** | **138 / 138** | **100.0%** |

- **Execution Time:** ~3.5 seconds for all 138 questions (~25 ms per question).
- **Token Cost:** **$0.00** (Zero LLM API cost, 100% deterministic spatial reasoning).

---

## 4. Comprehensive E2E Test Suite (288 Tests)

The test suite exercises all 25 features across 4 structured tiers derived strictly from opaque-box specifications:

```bash
uv run --project industrial-agents-hackathon-2026 python talk_to_your_building/tests/run_all_tests.py
```

### Test Suite Scorecard

```
================================================================================
          TALK TO YOUR BUILDING (TRACK 01) — E2E TEST SCORECARD
================================================================================
Tier | Description                                | Pass  | Fail  | Skip  | Time (s)
--------------------------------------------------------------------------------
T1   | Tier 1: Feature Coverage (>=5 tests/feat)  | 125   | 0     | 0     | 1.350   
T2   | Tier 2: Boundary & Corner Cases (>=5/feat) | 125   | 0     | 0     | 0.576   
T3   | Tier 3: Cross-Feature Combinations         | 26    | 0     | 0     | 0.557   
T4   | Tier 4: Real-World Workload Scenarios      | 12    | 0     | 0     | 1.047   
--------------------------------------------------------------------------------
ALL  | TOTAL CONSOLIDATED SUITE                   | 288   | 0     | 0     | 3.530   
================================================================================
  >>> OVERALL RESULT: ALL 288 TESTS PASSED (100% SUCCESS) <<<
================================================================================
```

### Running Specific Test Tiers
```bash
# Tier 1 only (Feature Isolation Coverage: 125 tests)
uv run --project industrial-agents-hackathon-2026 python talk_to_your_building/tests/run_all_tests.py --tier 1

# Tier 2 only (Boundaries & Edge Cases: 125 tests)
uv run --project industrial-agents-hackathon-2026 python talk_to_your_building/tests/run_all_tests.py --tier 2

# Tier 3 only (Cross-Feature Combinations: 26 tests)
uv run --project industrial-agents-hackathon-2026 python talk_to_your_building/tests/run_all_tests.py --tier 3

# Tier 4 only (Real-World Factory Workloads: 12 tests)
uv run --project industrial-agents-hackathon-2026 python talk_to_your_building/tests/run_all_tests.py --tier 4
```

---

## 5. Official Competition Submission (`submission.csv`)

The official submission file containing predictions for all 145 unseen test questions has been generated and validated:

- Primary path: `/Users/konstantin/Programmation/Hackathon/Je_regrette_rien/talk_to_your_building/submission.csv`
- Mirrored path: `/Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/submission.csv`

### Submission Metrics Summary

| Metric | Value | Status |
|---|:---:|:---:|
| Total Test Questions | **145** | Matched |
| Total Rows in File | **146** (1 header + 145 answers) | Verified |
| Question ID Integrity | **100%** (matches `submission_template.csv` in exact order) | Verified |
| Non-Empty Answers | **145 / 145 (100%)** | Verified |
| Answer Format (`Answer: ...`) | **100% compliant** with `benchmark/score.py` | Verified |
| Total Inference Time | **0.93 seconds** (145 questions) | Fast & Deterministic |

### Test Set Question Kind Breakdown

| Category | Count | Answer Format Guarantee |
|---|:---:|---|
| `floor_area_total` | 33 | Single float `Answer: <number>` |
| `shared_walls_count` | 26 | Single integer `Answer: <number>` |
| `largest_room` | 21 | `Answer: <room name or ref>, <area> m²` |
| `errand` | 20 | Single float `Answer: <number>` |
| `wide_delivery_count` | 18 | Single integer `Answer: <number>` |
| `straight_line_3d` | 15 | Single float `Answer: <number>` |
| `room_stacked` | 9 | `Answer: <room name or ref>` |
| `what_if_door` | 3 | Single integer `Answer: <number>` |
| **Total** | **145** | **100% committed answers** |

---

## 6. Interactive 3D Digital Twin Visualizer & REST Server

The interactive visualizer provides an industrial HUD with a 3D isometric multi-floor exploded-view explorer, mobile AR guidance, QR code calibration, and voice-assisted navigation.

### Launching the Server
```bash
uv run --project industrial-agents-hackathon-2026 python -m talk_to_your_building.server --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your web browser.

### Key Visualizer Capabilities
1. **3D Isometric Exploded View (Three.js)**:
   - Interactive elevation slider (0.0x to 3.0x vertical spacing).
   - Extruded room geometries, semi-transparent walls, and parametric machine models (CNC mills, lathes, presses, workbenches).
   - Animated 3D Catmull-Rom route ribbons with travelling avatar.
2. **Dynamic Incident Management**:
   - Toggle lift/stair breakdowns and room/corridor blockages in real time.
   - Interactive counterfactual doorway insertion (`add_door`).
   - Instant topological graph recalculation and active route rerouting.
3. **Mobile AR Camera Guidance & QR Calibration**:
   - Smartphone camera overlay projecting 3D directional guidance arrows.
   - Client-side `jsQR` barcode reader at doorway checkpoints for zero-drift positioning.
4. **Hands-Free Voice Navigation**:
   - Web Speech API and ElevenLabs proxy for speech-to-text and voice prompts.
   - 2D corridor vector cross-product generating landmark-referenced directions ("Walk past the break room, take the elevator to floor 2, turn right after CNC mill 0.21").
   - Conversational ambiguity clarification engine.

### REST API Endpoints

- `GET /api/buildings`: List all available buildings across dev and test splits.
- `GET /api/building/state`: Retrieve full 3D building model (floors, spaces, openings, vertical connectors, assets, and active incidents).
- `POST /api/route`: Compute constrained multi-floor route (options: `step_free`, `min_width`, `stops`).
- `POST /api/incident`: Report a closure, open an element, or add a counterfactual door.
- `POST /api/voice/intent`: Process voice input or natural language queries with clarification support.
