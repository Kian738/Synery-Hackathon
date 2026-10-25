# Status

Last updated: 25 October 2026. This page is a snapshot of what works and how we know. The dated log of every milestone up to this cleanup is in [archive/STATUS_LOG_2026-10.md](archive/STATUS_LOG_2026-10.md). Open work: [TASKLIST.md](TASKLIST.md) (short list) and [BACKLOG.md](BACKLOG.md) (long list).

Words used here: **verified** means an eval or test in this repository measures it and passes. **Partial** means it works, but part of it has not been checked by eye or on a device. **Unverified** means it is built but not measured. **Missing** means it is not built.

## Challenge levels

| Level | Capability | Status | Evidence |
|---|---|---|---|
| 1 Locate | Find rooms and items by name, number or type; show them on the plan and in 3D | verified | `e2e_basic` (locate and count families), `tests/test_visual_analytics.py` |
| 2 Route | Shortest route, step-free, closures, tours under the kit 1.1.0 rules | verified | `routes` 2130/2130 to the cm; `differential` graph-equal to the kit on all 280 buildings |
| 2 Route | Avoid places, soft avoid, minimum door width, forklift, bays | verified as properties (no gold exists) | `rules` 661/661, `tests/test_route_rules.py` |
| 2 Route | Drawn walking lines that never cross walls or furniture | verified on samples | `walls` 160/160, `walkability` 160/160; unsafe previews are withheld and counted |
| 3 Scale | Multi-floor (stairs, lifts) | verified | `routes`, `solver` |
| 3 Scale | Several buildings | partial | `core/campus.py` joins the 17 OSM buildings that have coordinates (`tests/test_campus.py`); the outdoor leg uses OpenRouteService or a labelled estimate; the UI is only build-checked |
| 4 Build | Rebuild from plan images | partial | 64/122 dev floors pass the strict pipeline check, 0/40 complete buildings pass automatically ([RECONSTRUCTION_VALIDATION_RESULTS.md](RECONSTRUCTION_VALIDATION_RESULTS.md)) |
| 4 Edit | Add, remove and widen doors; close and reopen; add, move and remove items; undo | verified | `tests/test_edit_capabilities.py`, `tests/test_door_e2e.py`, `edits` 72/72 against the kit's router |
| 5 Extend | Voice in and out | partial | `server/voice.py` (ElevenLabs proxy, cached TTS, character budget) with browser speech as fallback; `tests/test_voice.py` and `voice.spec.ts` run against a stubbed server; real audio and latency not measured |
| 5 Extend | Fire and evacuation scenarios | verified as solver contracts | `tests/test_evac_*.py`, `tests/test_scenario_*.py`, `tests/test_stress_*.py`; `eval scenarios`; not validated against real drills |
| 5 Extend | Phone companion | partial | Pairing, remote and instructions tested in two browser contexts (`phone-integration.spec.ts`, `tests/test_companion.py`); no physical phone |
| 5 Extend | AR route ribbon, VR Guide me | unverified | Built (`companion/ArRoute.tsx`, `components/VrRig.tsx`); never tried on a phone or headset |
| 5 Extend | Live positioning (BLE, Wi-Fi, camera) | missing | See [BACKLOG.md](BACKLOG.md#knowing-where-the-user-is) |

## Benchmark

| Item | Status |
|---|---|
| Nine benchmark kinds | Kit evaluator on dev: 138/138 (re-run 25 October 2026). Train + dev: 653/655, both misses diagnosed ambiguous names |
| Test package | `SUBMISSION/answers.json`: 145/145 questions answered by the rule parser, zero model calls; `fw submit` validates ids and route/answer consistency |
| Sunday command | `run_benchmark` reads JSON, JSONL or CSV and writes JSON (with route node ids and lengths) or CSV |
| Unknown wording | The LLM parser handles phrasings the rules do not cover; `gold` 3755/3755 plus holdout 1530/1530 on rephrased questions, deterministic parser only |

## Interaction

| Item | Status |
|---|---|
| Chat agent with tools | Claude-first. Text streams over SSE; a failed turn rolls back cleanly; tool schemas stay fixed per conversation |
| Live packs | 30-conversation browser pack: 25/30 (three wording failures, two out of budget), run `20261025-004659_live_chat_bb773074`. A separate three-rehearsal showcase passed 3/3. These are LLM-judged, not human-reviewed |
| Asking back | Ambiguous names come back as 2 to 4 tappable choices (`ask_choice`); missing scenario inputs are asked for, never guessed |
| Human trials | Not done: three people who do not know the app still need to try it without help |

## Offline gates

Last full run: 25 October 2026, with the source unchanged during the run. All 18 gates passed. The numbers are in the [README](../README.md#results); reproduce them with `uv run fw check`. Python suite: 567 tests collected.

## Known risks

1. The Sunday question format is not announced; the adapter accepts JSON, JSONL and CSV.
2. Question kinds outside our families go to the chat agent, and their quality is not measured.
3. Plan import from real (not procedural) plans is weak.
4. Hardware (phone motion, AR, VR, microphone, projector) is untested.
