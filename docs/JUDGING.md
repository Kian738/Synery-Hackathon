# Floorwise evidence map

Each row names the command that reproduces it. The latest full gate run (25 October 2026) is summarised in the [README](../README.md#results), and the current state is in [STATUS.md](STATUS.md). Rows with a date or milestone are historical: re-run the command before quoting them.

Floorwise turns a supplied building model into grounded answers, indoor routes, closure consequences and verified hypothetical repairs. Run locally with `uv run fw start` and check it with `uv run fw check`. No hidden evaluation instructions are used.

| Capability | Evidence command | Observed result | Implementation |
|---|---|---|---|
| Exact benchmark route model | fw eval routes --split train,dev | 2130/2130 | core/graph.py |
| Geometry and aggregate calculations | fw eval solver --split train,dev | 655/655 | core/ops.py |
| Question text to benchmark answer | fw eval e2e --split train,dev | 653/655 | agent/answer.py |
| Basic questions from text | fw eval e2e_basic --split train,dev | 2122/2130 | agent/spec.py |
| Independent router comparison | fw eval differential --split train,dev,test | 8960/8960 (graph equality with the kit's `building_map.py` on all 280 buildings, plus route and closure comparisons); the gate runs a dev sample (256/256) | eval/differential.py |
| Step-free closure consequence | pytest tests/test_insights.py | Office lift cuts off 29 of 56 step-free rooms; general cut-off count is 0 | agent/session.py |
| Verified width repair | pytest tests/test_insights.py | campus O0015 0.9 to 1.1 m; preview does not mutate | core/fixes.py |
| Human walking geometry | fw eval walkability --split dev --pairs 4 | 160/160 sampled pairs pass (withheld previews are counted separately in the run summary, never drawn) | core/walk.py |
| UI, chat recovery and interventions | fw ui-test | 39 Playwright spec files, desktop and phone projects | web/tests/ |
| Unseen test split has no ambiguous or near-tie questions; independent router agrees on test buildings | uv run python -m eval unseen; uv run python -m eval differential --split test | 145/145; 3348/3348 comparisons | eval/unseen.py |
| Verified multi-hop scenario (hazard, exits, responders, door fixes) | pytest tests/test_scenario_api.py tests/test_reason_findings.py; uv run python -m eval scenarios; uv run python -m eval.sensitivity | 7 API/tool tests; dataset stress test 479/479 checks; top door fix identical in 6/6 flow cases up to the estimated occupancy on campus-dev-000 (changes at 1.5x occupancy) | reason/, evacuation/, server/scenario.py |
| Live Claude conversations | fw test live; fw test demo | 30-conversation pack 25/30 (three wording failures, two out of budget); showcase 3/3. LLM-judged, not human-reviewed | eval/product.py, web/tests/live-runner.cjs |

## Demo

Use campus-dev-000: step-free Lab 2.17 to Lab 4.26 is 60.15 m under the judges' route rules (door to door, stairs 2 m per metre, lifts 15 m + 1 m per metre); close Lift 3, which that route uses, and the alternative via Lift 2 is 73.00 m. Floor transitions are explicit. Remeasured after the kit 1.1.0 rule change; older figures (49.7 / 96.1 m) belonged to the superseded model.

For the impact shock shot, use factory-dev-003 and close Office lift: 29/56 rooms lose step-free exit access. For repair, request Main lobby to Print room 0.16 for a 1.1 m trolley. A verified hypothetical widening is offered; Apply changes the session's model, not a physical door.

## Limits

Labelled train/dev questions that stay wrong end to end (2 of 655 in `e2e`, 8 of 2,130 in `e2e_basic`) all name a room that has several readings; each one is diagnosed in `eval/known_issues.json`. Test questions have no hand-labeled answers. 3D is schematic, not a BIM reconstruction: window geometry and physical stair flights are absent. Some openings cannot be matched to room boundaries; their routes cannot use eye-level playback. Voice hardware and projector legibility need an on-site check. PNG-import labels and doors are inferred; SVG-first ingest is not shipped. Frame-rate targets are not yet measured on the presentation hardware.

The fallback recording under runs/demo is deliberately scripted at the chat transport boundary and exercises real deterministic backend operations. It is not evidence of live voice or live Claude latency. Live model transcripts are evaluated separately.

## Additional evidence: speed, fragility across the dataset, and the fix card

| Capability | Evidence command | Observed result | Implementation |
|---|---|---|---|
| Ranking every single point of failure is fast and equals the slow definition (rebuild the whole graph once per closed element) | `uv run pytest tests/test_resilience_equivalence.py` | 6 passed. The 1,623-space OSM building takes about 3 s; the per-element rebuild took 102 s | `core/resilience.py` |
| Weak doors are named by the two places they join, never by id | same test file, `test_weak_point_names_are_readable_never_raw_ids` | passes | `core/resilience.py` |
| One number for a building: share of rooms that still reach an exit after the worst single interior closure (N-1 contingency, entrances excluded) | `uv run pytest tests/test_fix_and_worst_case.py` | `factory-dev-003`: (56 - 29) / 56 = 0.482 for step-free users | `core/resilience.py` |
| A verified fix reports how many rooms are reachable from the start before and after it | same test file | counts equal an independent recomputation | `core/fixes.py` |
| In this kit, one building in four has a single lift whose closure strands at least a quarter of the step-free building | `uv run python -m eval atlas` | last row: 280 buildings, 16223 rooms, 100% / 69% / 12% reach for anyone / step-free / 1.1 m trolley, 73 lift cases, 138 interior-door cases | `eval/atlas.py` |
| The route answer carries every graph node, including door nodes, and the nodes form a real walk of the stated length | `uv run pytest tests/test_route_output.py` | 3 passed | `floorwise/cli.py` |
| The fix card names the door and shows the checked before and after counts | `fw ui-test` (`web/tests/fixcard.spec.ts`) | passes on desktop and phone | `web/src/lib/impact.ts` |

The atlas counts generated and inferred elements of the kit data. Read it as a dataset-scale test of the tool, not as a statistic about real buildings. Interior doors exclude entrances and stairs, which are expected to strand what lies behind them.

The independent router comparison above was also mutation-tested: forcing `RouteGraph._opening_allowed` to return `True` made 116 differential rows fail, and none fail unmodified.
