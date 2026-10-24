# Status: what works, what is untested, what is missing

Last updated: 2026-10-24. **verified** = measured by an eval or test in this repo; **live-tested** = ran against a real LLM; **untested** = written but never run; **missing** = not built.

## Challenge levels

| Level | Capability | Status | Evidence |
|---|---|---|---|
| 1 Locate | find items and rooms by name, type, number | verified | `e2e_basic` locate 553/553, count 239/239 |
| 1 Locate | show them on a view | verified (old UI) | highlight events; screenshots |
| 2 Route | shortest route, step-free, closures, tours | verified | `routes` 2130/2130 (to the cm) |
| 2 Route | avoid X and Y, soft avoid, no stairs/lifts, min door width | verified in unit tests | `tests/test_core.py`; no gold exists |
| 3 Scale | multi-floor (stairs, lifts) | verified | `routes`, `solver` |
| 3 Scale | several buildings linked by walkways | **missing** | data has single buildings |
| 4 Build | rebuild from plan images | verified on procedural; weak on OSM/Swiss | `build`: procedural rooms 1.00, doors 1.00; OSM doors 0.72; Swiss doors 0.67 |
| 4 Build | scale without a scale bar | user gives one width; **door-width estimate missing** | |
| 4 Build | room names from images | vision labeller **untested** (Claude only; Groq models here have no vision) | |
| 4 Edit | add door (preview → apply), close/reopen, move item | verified (session tests); preview/undo UI partial | |
| 5 Extend | voice in/out | browser speech only; Groq Whisper/Orpheus available, not wired | |
| 5 Extend | AR | **missing** (plan: QR-seeded WebXR on Android, see UX_PLAN) | |

## Benchmark

| Item | Status |
|---|---|
| 9 benchmark kinds | verified: kit evaluator dev 138/138; train+dev 653/655 (2 = 9-way duplicate name "Büro") |
| test submission | `submissions/team_floorwise_test.csv`, 145/145 parsed by rules, 0 fallbacks |
| Sunday command | `fw bench` / `run_benchmark`, CSV or JSON (route node IDs, lengths). The Sunday file format is not yet announced; the adapter is flexible |
| unknown wording | LLM parser fallback: live on Groq 36/40 dev sample; untested on Claude |
| unknown question kinds | chat agent fallback, live on Groq; not evaluated |

## Interaction (25 %)

| Item | Status |
|---|---|
| chat agent with tools | live-tested on Groq (`openai/gpt-oss-120b`) |
| interaction suite (8 personas + judge) | runs on Groq; first 3 scenarios: wheelchair 5.0, vague 5.0, wrong_room 3.8 (failed the "said it doesn't exist" check) |
| known agent flaws seen live | asks back when both matches are in the same room; did not call `remember_person` on "I use a wheelchair" (applied step-free per call instead) |
| research-backed behaviour (ask-gate, answer-first header, landmark chunking, floor-change steps, voice step mode) | **missing**; planned in `UX_PLAN.md` |

## UI

| Item | Status |
|---|---|
| Navigator app (old MVP) | works: plan, 3D stack, click-to-route, chat, closures, door preview, build dialog. The design is generic and being replaced |
| Benchmark lab (admin) | **missing**; planned in `UX_PLAN.md` |
| Playwright UI tests | **missing**; the plugin is installed (active after a Claude Code restart) |

## Known risks

1. Sunday format is unknown, and question kinds outside our 15 families have unknown quality.
2. Interaction quality is only measured on Groq models, not Claude.
3. Building from scanned (non-generated) plans is weak.
