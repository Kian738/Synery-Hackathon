# Floorwise evidence map

Floorwise turns a supplied building model into grounded answers, indoor routes, closure consequences and verified hypothetical repairs. Run locally with `uv run fw start` and check it with `uv run fw check`. No hidden evaluation instructions are used.

| Capability | Evidence command | Observed result | Implementation |
|---|---|---|---|
| Exact benchmark route model | fw eval routes --split train,dev | 2130/2130 | core/graph.py |
| Geometry and aggregate calculations | fw eval solver --split train,dev | 655/655 | core/ops.py |
| Question text to benchmark answer | fw eval e2e --split train,dev | 653/655 | agent/answer.py |
| Basic questions from text | fw eval e2e_basic --split train,dev | 2124/2130 | agent/spec.py |
| Independent router comparison | fw eval differential | 7200/7200 comparisons over 240 train/dev buildings, including closure cases | eval/differential.py |
| Step-free closure consequence | pytest tests/test_insights.py | Office lift cuts off 29 of 56 step-free rooms; general cut-off count is 0 | agent/session.py |
| Verified width repair | pytest tests/test_insights.py | campus O0015 0.9 to 1.1 m; preview does not mutate | core/fixes.py |
| Human walking geometry | fw eval walkability --split dev --pairs 4 | 134 validated routes; 26/160 sampled pairs withheld; no invalid emitted route in this sample | core/walk.py |
| UI, chat recovery and interventions | fw ui-test | 46/46 desktop + phone at milestone 2 | web/tests/navigator.spec.ts |
| Live Claude route and closure | fw eval rehearse | five repetitions, both state checks pass; unsupported/dangerous prompts also reviewed | eval/rehearse.py |

## Demo

Use campus-dev-000: step-free Lab 2.17 to Lab 4.26 is 49.7 horizontal walking metres; close Lift 2 and the alternative is 96.1 m. Floor transitions are explicit. These numbers were remeasured after collision validation and replace the handoff PDF's older values.

For the impact shock shot, use factory-dev-003 and close Office lift: 29/56 rooms lose step-free exit access. For repair, request Main lobby to Print room 0.16 for a 1.1 m trolley. A verified hypothetical widening is offered; Apply changes the session's model, not a physical door.

## Limits

Eight labeled train/dev questions remain wrong end to end because names have multiple room readings. Test questions have no hand-labeled answers. 3D is schematic, not a BIM reconstruction: window geometry and physical stair flights are absent. Some openings cannot be matched to room boundaries; their routes cannot use eye-level playback. Voice hardware and projector legibility need an on-site check. PNG-import labels and doors are inferred; SVG-first ingest is not shipped. Frame-rate targets are not yet measured on the presentation hardware.

The fallback recording under runs/demo is deliberately scripted at the chat transport boundary and exercises real deterministic backend operations. It is not evidence of live voice or live Claude latency. Live model transcripts are evaluated separately.
