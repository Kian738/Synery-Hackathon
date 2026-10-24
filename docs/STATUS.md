# Status: what works, what is untested, what is missing

Last updated: 2026-10-24 (implementation milestone 1). **verified** = measured by an eval or test in this repo; **live-tested** = ran against a real LLM; **untested** = written but never run; **missing** = not built.

## Challenge levels

| Level | Capability | Status | Evidence |
|---|---|---|---|
| 1 Locate | find items and rooms by name, type, number | verified | `e2e_basic` locate 553/553, count 239/239 |
| 1 Locate | show them on a view | verified (old UI) | highlight events; screenshots |
| 2 Route | shortest route, step-free, closures, tours | verified | `routes` 2130/2130 (to the cm) |
| 2 Route | avoid X and Y, soft avoid, no stairs/lifts, min door width | verified in unit tests | `tests/test_core.py`; no gold exists |
| 2 Route | humane drawn routes (inside rooms, around furniture, no entrance teleport) | validated/withheld | latest: 134 valid routes and 26 withheld cases in 160 dev samples; no collision-crossing fallback |
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
| chat agent with tools | live-tested on Groq and Claude; five Claude route/closure repetitions verified |
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
| not yet ported to the new UI | draft import is now ported, with source reference overlay and explicit confirmation |

## Known risks

1. Sunday format is unknown, and question kinds outside our 15 families have unknown quality.
2. Claude state checks and sampled transcript review now exist; hardware voice and uncoached on-site usability are still unverified.
3. Building from scanned (non-generated) plans is weak.


## Verified building demo: milestone 1

- Profile-aware closure impact verified: factory Office lift reports general 0 cut off, step-free 29/56, and reopening reconnects 29.
- Door-width repair verified on campus print room: O0015, 0.9 to 1.1 m, preview does not mutate; apply restores graph connectivity. This is a hypothetical edit requiring physical work, not certification of a trolley path.
- Weak-point analysis groups closures by stranded room sets. Unlike the handoff's assumption, ordinary room doors are also weak points (one room each on the demo factory).
- Claude now has typed tools for exact counts, shared walls, 3D distance, errands, read-only door effects and weak points.
- Human routes no longer fall back to free outside hops. Exact furniture validation withholds guidance when a safe modeled passage cannot be established.
- Offline check: 21 unit tests; route model 2130/2130; solver and train/dev parser 655/655; test parser 145/145; e2e 653/655; basic train+dev 2124/2130; robust 630/630; metamorphic 898/898.
- Walkability: 134 validated routes, 26 cases with guidance withheld, zero invalid routes in 160 sampled pairs. This is not 100% route availability. Earlier 145/149 results omitted unreachable cases and tolerated dataset-blocked furniture crossings.
- Normal Claude coffee requests succeeded; the reported white-screen crash has not yet been reproduced. Frontend recovery/validation work is in progress. Voice remains unverified on physical hardware.


## Verified building demo: milestone 2

- Reproduced the white-screen failure in the browser: conversation auto-scroll returned a value from a React effect, which React later called as a cleanup function. The effect now returns nothing; repeated-message regression and live Claude coffee request pass. Error boundaries retain recovery UI.
- New dark 3D Navigator has batched floor geometry, instanced asset footprints, opening gaps, closure markers, ghost previous route, room picking, eye-level preview, manual waypoints and reduced-motion static guidance.
- Fresh-server Playwright run: 46/46 desktop + phone tests, including streaming errors, empty routes, promise-returning scroll API, 29/56 closure impact, verified widening/apply, reduced motion and microphone denial. Physical microphone/speaker performance remains unverified.
- All 280 buildings compile to schematic scenes in a local survey (3.38 seconds before the stricter per-side opening check). Unmatched opening references are reported; eye-level preview is disabled for routes using them. No as-built completeness claim.
- Independent official-router differential: 7200/7200 length/reachability/closed-element comparisons across all 240 train/dev buildings. Command: fw eval differential.
- Demo route remeasured after stricter path validation: Lab 2.17 to Lab 4.26 step-free is 49.7 m; after closing Lift 2 it is 96.1 m. These replace the PDF's earlier 49.5/95.6 m values.
- Draft PNG import and source-image reference overlay are restored. Source overlay is not a calibrated registration; inferred doors require review. SVG-first parsing is not implemented.
- Newly added compound-place tool intersects room type, floor, contained asset and above/below filters. No office with a coffee machine is fabricated.


## Final implementation verification

The updated effect is verified in a real browser and with a promise-returning scroll API regression. Unit tests also cover step-distance sums, profile-triggered rerouting, exact route-node output and independent closure routing. Rehearsal on the new session-context prompt passed an additional route/closure pair plus unsupported and dangerous-request state checks. Current map context is refreshed each turn and never overrides an explicit requested origin.

The recorded deterministic fallback and screenshots are under runs/demo; the capture uses real backend geometry and operations with a scripted chat transport. It has no live Claude or microphone audio. The three-minute speaking script is docs/DEMO.md. SVG-first import, the optional bridge/articulation proof, undo UI, a slide deck, physical voice tests, projector checks and Sunday release execution remain outside this completed app milestone; no claims are made that they shipped.
