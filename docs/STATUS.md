# Status: what works, what is untested, what is missing

Last updated: 2026-10-24 (evening). **verified** = measured by an eval or test in this repo; **live-tested** = ran against a real LLM; **untested** = written but never run; **missing** = not built.

## Challenge levels

| Level | Capability | Status | Evidence |
|---|---|---|---|
| 1 Locate | find items and rooms by name, type, number | verified | `e2e_basic` locate 553/553, count 239/239 |
| 1 Locate | show them on a view | verified (old UI) | highlight events; screenshots |
| 2 Route | shortest route, step-free, closures, tours | verified | `routes` 2130/2130 (to the cm) |
| 2 Route | avoid X and Y, soft avoid, no stairs/lifts, min door width | verified in unit tests | `tests/test_core.py`; no gold exists |
| 2 Route | humane drawn routes (inside rooms, around furniture, no entrance teleport) | verified | `walkability` 226/226 dev, 347/347 train sample; 15 rooms where the data's furniture blocks a door are flagged |
| 3 Scale | multi-floor (stairs, lifts) | verified | `routes`, `solver` |
| 3 Scale | several buildings linked by walkways | **missing** | data has single buildings |
| 4 Build | rebuild from plan images | verified on procedural; weak on OSM/Swiss | `build`: procedural rooms 1.00, doors 1.00; OSM doors 0.72; Swiss doors 0.67 |
| 4 Build | scale without a scale bar | user gives one width; **door-width estimate missing** | |
| 4 Build | room names from images | vision labeller **untested** (Claude only; Groq models here have no vision) | |
| 4 Edit | add door (preview → apply), close/reopen, move item | verified (session tests); preview/undo UI partial | |
| 5 Extend | voice in/out | browser speech only; Groq Whisper/Orpheus available, not wired | |
| 5 Extend | 3D building view (rooms, walls, furniture by type, route across floors) | done (`Building3D.tsx`), base for AR |
| 5 Extend | AR, BLE/WiFi positioning | **missing**: see `docs/BACKLOG.md` (QR + WebXR on Android first; BLE/WiFi need a native app) | |

## Benchmark

| Item | Status |
|---|---|
| 9 benchmark kinds | verified: kit evaluator dev 138/138; train+dev 653/655 (2 = 9-way duplicate name "Büro") |
| test submission | `submissions/team_floorwise_test.csv`, 145/145 parsed by rules, 0 fallbacks |
| Sunday command | `fw bench` / `run_benchmark`, CSV or JSON (route node IDs, lengths). The Sunday file format is not yet announced; the adapter is flexible |
| unknown wording | LLM parser fallback: **Claude Haiku 39/40** (< 1 cent), Groq 36/40 |
| unknown question kinds | chat agent fallback, live on Groq; not evaluated |

## Interaction (25 %)

| Item | Status |
|---|---|
| chat agent with tools | live-tested on Groq (`openai/gpt-oss-120b`) |
| flaws seen before the protocol fixes | asked back when both matches were in the same room; skipped `remember_person`. Both are fixed: the ask-gate is in `Session.place`, and the prompt was rewritten |
| research-backed behaviour | done: nearest-match ask-gate, answer-first header (prompt + UI route sign), landmark chunking and floor-change steps (`instructions.py`), spoken overview of 4 parts or fewer, step mode with next/repeat/back |
| live check (Groq, via web SSE) | wheelchair + location → `remember_person`, nearest toilet without asking, header line, 2 steps, alternative mentioned |
| interaction suite on Groq | 7 of 8 scenarios score 4.7–5.0; the judge is a lenient open model |
| interaction suite on Claude (partial: 4 of 8 conversations before the machine ran low on memory and the run was stopped) | first_day 4.5, wheelchair 3.8, technician 4.3, facility_manager 4.2. Real findings, all fixed since: totals did not match the step distances (now walking metres); newcomers were shown room codes (now: assume the main entrance, describe by kind); "keep it short" ignored (now max 3 one-line steps); the judge could not see tool results (now in the transcript). **Re-run needed** |

## UI

| Item | Status |
|---|---|
| Navigator (rebuilt) | signage design; categories; tap a room for "Go here" / "I'm here"; route sign + steps; step mode; voice; closures from the room card; deep links `?at=&to=&step_free=1` |
| Benchmark Lab `/lab` | overview with CIs and trends, launch any suite with live logs, runs list, drill-down (question, expected, reply, trace, places and route on the plan), compare runs, dataset browser |
| Playwright UI tests | 18/18 (desktop 1440 px + phone 390 px), `fw ui-test` |
| Lab front page | inspection sheet: every check in plain words, target vs result, pass/fail, cost, run button, "see failures" |
| UX audit fixes | start defaults to the main entrance (one-tap categories), start picker, floors in their own column, map key on demand, labels sized in screen pixels, examples built from the building's data |
| Playwright | 28/28 (14 flows × desktop + phone) |
| not yet ported to the new UI | build-from-plans dialog (the API exists) |

## Known risks

1. Sunday format is unknown, and question kinds outside our 15 families have unknown quality.
2. Interaction quality is only measured on Groq models, not Claude.
3. Building from scanned (non-generated) plans is weak.
