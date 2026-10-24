# Status: what works, what is untested, what is missing

Last updated: 2026-10-24 (UX overhaul milestones 1–3). **verified** = measured by an eval or test in this repo; **live-tested** = ran against a real LLM; **untested** = written but never run; **missing** = not built.

## Challenge levels

| Level | Capability | Status | Evidence |
|---|---|---|---|
| 1 Locate | find items and rooms by name, type, number | verified | `e2e_basic` locate 553/553, count 239/239 |
| 1 Locate | show them on a view | verified | complete visual events, linked views and desktop/phone regression tests |
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

## UX overhaul milestone 1 (2026-10-24)

Implemented a shared preview timeline, frame-independent progress, bounded camera rotation, seek/speed controls, distinct arrival state, landmark guidance, explicit floor scopes, persistent manual-position markers, a linked expandable plan, and a collapsed route itinerary. Preview never changes declared location. Verified: `fw check` (27 unit tests and all offline gates; existing ambiguous-name misses unchanged); 40 initial desktop/phone checks passed, four corrected-flow checks passed on rerun, and two new seek/arrival/replay checks passed. Physical voice and uncoached teammate testing remain manual.

## UX overhaul milestones 2–3 (2026-10-24)

The building workspace now has linked/focused plan and model selection, manual location/facing separate from preview position, compact mobile guidance with an expandable stage, camera memory, instanced oriented door frames, illustrative ceilings and recognizable equipment. Duplicate/coplanar display walls are unioned without changing analytical geometry. Supplied stair assets are illustrative; unsurveyed connector interiors use landing transitions, not invented continuous flights.

Chat now dispatches supported counts, item rankings, highlights, area queries and references deterministically, including without an API key. Unknown simple wording uses the configured parser; edits, complex constraints and multi-step work use the full agent. Required parser fields are checked before execution. All geometry facts stay deterministic. Specialized tool schemas load on demand on both providers.

Complete visual result events and session-scoped paged results support every question family. Search no longer limits computed highlights to 12. New analytics include inclusive, labeled chair-family counts, optional floor/room counts, room rankings with ties, AND equipment/minimum-count filters, and area/count groups. Source capacity, bookings, access and windows remain unavailable rather than inferred. Per-turn usage includes cache tokens and latency; price estimates require explicit `FLOORWISE_MODEL_PRICES_JSON` rates (USD per million tokens).

The eval ledger now creates unique run directories and gates identify their own process's summaries, fixing same-second evidence overwrites. Latest verification details and the 25-issue mapping are in `docs/UX_AUDIT.md`. Physical voice, projector/FPS measurement and the three-person uncoached study remain manual; no claim of having completed them is made.

### Latest measured evidence

- `fw check`: 57 unit tests passed; all offline gates passed. Routing 2130/2130, solver/parser 655/655, test parser 145/145, robustness 630/630, metamorphic 898/898, differential 240/240. The eight pre-existing ambiguous-name e2e misses are unchanged.
- `fw ui-test`: 64 desktop/phone checks passed; the two opt-in recording cases are skipped in routine runs.
- All 280 supplied buildings compiled successfully: 175,456 display-wall segments in 11.11 seconds total on this machine. This is compilation throughput, not an FPS measurement.
- Live Claude and Groq passed unfamiliar-count wording and closure tools; the final closure smoke passed with deferred tool schemas on both providers. Known simple chat questions are verified to make zero model calls.
- Visual audit evidence: `runs/ux-overhaul/`; complete issue mapping and human acceptance script: `docs/UX_AUDIT.md`.

The updated deterministic fallback recording passed its opt-in capture test and is saved at `runs/demo/fallback.webm`, including a real zero-model chair-ranking turn after the scripted route/closure/fix transport. It is not a live voice recording.

## CIT walking regression and straight corridors (2026-10-24)

Fixed grid-region connectivity to match the pathfinder's no-corner-cutting rule. The reported CIT route 03.05.061 → 00.05.058 now produces validated walking geometry. Empty, convex, elongated corridors use a verified central straight run with door approaches instead of raster-induced slalom. Source graph/benchmark distances and obstacle collision checks are unchanged. Verified by targeted regressions and `fw check`; subsequent UI redesign is in progress.

## Guidance and rendering second pass (2026-10-24)

Guide me now uses the full scene and one compact media player with direct play, seeking, chapter navigation, speed and replay. Map and conversation are opt-in drawers. Room selection preserves camera framing; Focus room and Fit animate explicit changes. Pointer-intent handling prevents pan/rotate gestures from selecting rooms, including drags returning to their origin. Dense plan labels avoid collisions; route/selected connector labels use fixed-size icons. Raised opaque route geometry and tighter camera depth ranges replace overlapping route strips. Interiors retain ceilings. Manual-location and simulated-progress markers are distinct.

Integrated the reviewed Claude asset catalogue: all 96 supplied types have bounded, illustrative procedural silhouettes rendered in instanced batches. Repeated tools are grouped by turn and name with inspectable inputs and computed summaries. The closure stress-test panel now explains its actual reachability computation and assumptions.

Verification: `fw check` passed all offline gates; the eight existing ambiguous-name e2e misses are unchanged. Full desktop/phone UI run: 90 passed, four opt-in capture/contact-sheet cases skipped. TypeScript check passed after the concurrent companion package's typing fix. Screenshot evidence is under `runs/ux2/`; design rationale and incomplete stair/sensor/human checks are documented in `docs/UX_REVIEW_SECOND_PASS.md`. The phone companion and benchmark-resolution packages remain separate work until their READY handoffs are reviewed; this milestone does not claim they are integrated.

## Paired phone integration and ambiguity review (2026-10-24)

The companion is now mounted at `/phone` with confirmed, expiring pairing, synchronized computed instructions, remote chapter/repeat controls, touch/optional gyro camera orientation, recenter, revocation and reconnect. `fw start --lan` exposes the single-process server to the selected same-network phone setup. Added the required WebSocket transport dependency. The default LAN HTTP setup supports touch; motion requires a trusted secure context and an explicit user action. No physical phone, iOS hardware or real LAN trial is claimed. Setup and the short jury beat are in `docs/PHONE_DEMO.md`.

The real two-context integration test exposed a connector-label DOM teardown race. Labels now project into the ordinary React overlay with wall occlusion rather than creating independent DOM roots inside the canvas. First-person orientation looks farther along visible walking sections, ray-tested against walls, while positions remain on the validated route. Phone orientation does not update the declared location. Read-aloud also works when explicitly enabled during playback.

Reviewed the benchmark package: larger bounded sampling and ambiguity diagnostics are integrated; the proposed same-room pruning was rejected to preserve valid zero-length/repeated-room interpretations. The eight insufficiently specified end-to-end misses remain unchanged. Final `fw check`: 108 unit tests and all offline gates passed. Full UI run: 113 passed; 27 duplicate-project/opt-in cases skipped. The final wall-visible camera adjustment passed 11 targeted checks, including real paired navigation, with one duplicate-project skip. Typechecking and production build passed through `fw ui-test`.

The multi-hop capacity/evacuation proposal and landmark/multisensory evidence are saved under `research_notes/scenario-simulation/`; integer scheduling/discretization concerns are recorded in the integration review. This is research only. Capacity units are still an outstanding user decision; no occupancy, throughput, stair flights, hazard progression or responder tactics have been invented. Continuous surveyed stair traversal, physical voice/sensor rehearsal and unfamiliar-user acceptance remain incomplete.
