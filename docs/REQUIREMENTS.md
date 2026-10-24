# Requirements from Synera, broken down and traced

Sources: the kit README and CHANGELOG at **v1.1.0** (branch `patch/fix-answers-ruleset`, commit 6a2cdec, fetched 2026-10-24), and Synera's messages on the hackathon channel (route scoring, the rule list, the question about `BENCHMARK.md`). Status words: **verified** = a test or eval in this repo measures it and passes; **assumed** = we had to interpret the wording, the interpretation is stated and listed under "To confirm with Synera"; **open** = not done.

## A. How a building is modelled (channel message, README section 3)

| # | Requirement | Where implemented | Evidence | Status |
|---|---|---|---|---|
| A1 | Building = spaces (rooms, corridors, aisles, stairwells, lifts) joined by doors, openings, stairs, lifts | `core/model.py`, `core/graph.py` | graph equals the kit's edge for edge on all 280 buildings (`eval.differential`) | verified |
| A2 | Walking is measured inside each space, door to door, **15 cm off the walls**, round corners, never through walls | `core/spacewalk.py` (`buffer(-0.15)`, visibility graph, covers with `buffer(0.02)`) | 2130/2130 gold routes to the cm; `eval.rules` walking checks; hand-built corner test | verified |
| A3 | A door lands 30 cm inside each space; edge lengths rounded to 3 decimals | `spacewalk.door_landing`, `graph.LENGTH_DECIMALS` | 5.000 m hand case; graph equality | verified |
| A4 | Nodes: a space at `representative_point()` of its (repaired) outline, an opening at its position | `spacewalk.outline`, `graph.anchor` | graph equality | verified |
| A5 | **Stairs 2 m per metre climbed** (floor `elevation_m` difference) | `graph.STAIRS_M_PER_RISE` | `eval.rules` vertical, unit test (7.6 m for 3.8 m) | verified |
| A6 | **Lift 15 m once per ride + 1 m per metre**; a lift joins every pair of its stops | `graph.LIFT_FIXED_M`, `LIFT_M_PER_RISE`, `itertools.combinations` | unit test (22.6 m over two floors, one fee); `eval.rules` | verified |
| A7 | Furniture, equipment and machines are not obstacles for distances | graph never reads assets | `eval.rules` furniture check on every building; unit test | verified |
| A8 | A route to a machine or item ends in the room or bay holding it | `ops.errand` holders by `space_id` | 93/93 errand answers (`solver`), kit evaluator 138/138 | verified |
| A9 | **No way round the outside**: two parts that only meet outside have no route | entrances are door nodes of one space; `Constraints.outside="none"` default | 233 gold `reachable: false`; unit test; `eval.rules` outside | verified |
| A10 | Parallel connections (stair and lift between the same spaces, two doors between two rooms) are kept | `nx.MultiGraph` | unit test; graph equality | verified |
| A11 | What-if door: placed mid-wall; "walk out of the building" = route-model distance to the nearest entrance | `ops.what_if_door`, `outside="exits"` | 6/6 gold, the entrance-door-node reading matches 4/4 train+dev where the entrance-room reading matches 1/4 | verified (small gold set) |

## B. Rules that apply to some questions (channel message)

| # | Requirement | Where implemented | Evidence | Status |
|---|---|---|---|---|
| B1 | Without stairs: lifts, ramps and doors only | `Constraints.step_free` (drops stairs and openings with `step_free: false`); parser phrases "without/no stairs", "can't use stairs" | gold step-free 240/240; `eval.rules` step_free; parser test | **assumed**: "without stairs" read as the step-free rule |
| B2 | Forklift: forklift aisles and openings only (3 m or wider); pedestrian walkways do not count | `Constraints.forklift`: openings ≥ 3 m, passable spaces are non-bay corridor/hall/outdoor spaces that hold a 3 m circle, no stairs or lifts, other spaces only as destinations | unit tests; `eval.rules` forklift (monotonic, valid, rule-respecting) | **assumed**: the data has no "forklift aisle" flag |
| B3 | Closed or blocked areas must be avoided | `Constraints.closed` (spaces, openings, connectors); `closed`, `closed_more`, `avoid` in the question spec | gold closure 138/138; `eval.rules` closed; unit test | verified |
| B4 | Factory production bays are destinations: deliver into one, never cross one as a shortcut | `Constraints.bays_are_destinations` (terminal spaces: reachable, never crossed; the route's own start is exempt) | unit tests (also for tours); `eval.rules` bays | **assumed**: "bays" = hall spaces whose room type ends in `_zone` |
| B5 | If no route exists under the rules, the correct answer is to say so | `Answer: no route`; `reachable: false` in JSON | `eval.sunday` "no route" counts only when the dataset says none; unit test | verified |

## C. How a route answer is scored (channel message)

| # | Requirement | Where implemented | Evidence | Status |
|---|---|---|---|---|
| C1 | The answer is the ordered list of spaces passed through | reply ends `Answer: id -> id -> ...`; JSON `route` | `eval.sunday` reads the reply back | verified |
| C2 | Each step goes through a real door, opening, stair or lift; rules hold | `eval/judge.py` replicates the check with the kit's graph | `eval.sunday`, `eval.generated`; a lucky length on the wrong rooms now scores 0 | verified |
| C3 | The judges measure our route with their rule; our own distance numbers do not matter | `judge.measure` (layered shortest path restricted to the listed spaces, on the kit's own graph) | `eval.sunday` 1329/1338, all 9 misses diagnosed ambiguous names; `eval.generated` 1573/1573 on all 280 buildings | verified |
| C4 | Score = best / ours; within 1 % full marks; invalid scores 0 | `judge.score` | unit test; `eval.sunday` | verified |
| C5 | A space is never listed twice in a row | `routing` and `solve._join_paths` dedupe (a walk can touch a door of a room it never leaves) | found by `eval.rules`; 1313/1313 leg paths identical to gold | verified |

## D. Benchmark questions (README section 4, 6)

| # | Requirement | Evidence | Status |
|---|---|---|---|
| D1 | Nine benchmark kinds, answered from the text with the official scorer | `e2e` 653/655 (the two misses are diagnosed ambiguous names); kit `benchmark.evaluate` 138/138 on dev | verified |
| D2 | Tolerances: area ±5 %, distance ±1 % (min 1 m), 3D ±2 %, counts exact; room before runner-up | official `benchmark/score.py` used unchanged | verified |
| D3 | Reply ends with an `Answer:` line, exactly one number for numeric answers | solver replies; `eval.e2e` | verified |
| D4 | Latest organizer message: `SUBMISSION` contains exactly `BENCHMARK.md` and `answers.json`; retain earlier CSV for compatibility | `fw submit` validates unique complete IDs and structured answers, packages two files and writes legacy CSV | implemented; fresh release evidence in `docs/UX_COGNITIVE_LOAD_AUDIT.md` |
| D5 | No hand-labelling, no building-specific code, the Sunday building is unseen | no ids or names in `floorwise/`; `eval.generated` writes questions for all 280 buildings from code | verified |
| D6 | Questions with a repeated name: do not guess silently | every reading is solved and the vote reported as a best guess (`docs/parallel/benchmark-handoff.md`) | verified (11 diagnosed unanswerable) |

## E. Sunday run

| # | Requirement | Evidence | Status |
|---|---|---|---|
| E1 | A `run_benchmark` command that goes from (building, questions) to answers, no manual steps (channel question about `BENCHMARK.md`) | `uv run run_benchmark ...`, `BENCHMARK.md` | verified; keep `BENCHMARK.md` and the command name as they are |
| E2 | Works on any building in the format, including large ones | cold start of the largest supplied building (1,623 spaces) takes about 8 s; walk caches are stored in `runs/.walk-cache` | verified |
| E3 | Sunday question format may differ (route lists, rules in the text) | route answers are the ordered list; unfamiliar wording goes to the LLM parser, which now knows the rule fields | partly open: needs an API key on the day |

## To confirm with Synera on site

1. Is "without stairs" the **step-free** rule (also drops openings with `step_free: false`) or only "no stair connectors"?
2. What is a **forklift aisle**: we use corridor/hall/outdoor spaces that are not bays and fit a 3 m circle. Is there a flag or a naming rule?
3. Which spaces are **production bays**: we use hall spaces with a room type ending `_zone` (production, assembly, additive, warehouse, logistics). Does that include warehouse and logistics zones?
4. Do the forklift and bay rules also apply to the **errand** and **tour** questions, or to route questions only? (We apply them wherever the text states them.)
5. Is the Sunday route answer the `Answer:` line, a JSON list, or the structured `route` field? We provide all three; tell us which is read.
6. Questions that name a space which exists several times on one floor: is a hidden id expected? (11 train/dev questions cannot be answered from their text.)
