# AGENTS.md: how to work in this repository

This file is the contract for any coding agent (Claude Code, Codex, Cursor) or teammate working here. Read it before changing anything. `CLAUDE.md` points here.

## What this is

**Floorwise** is our entry for Synera Track 01, "Talk to your building", at the Industrial Agents Hackathon 2026. It is an indoor navigation agent: people ask a building where things are, how to get somewhere (step-free, avoiding areas, multi-stop), and report changes (closed lift, new door). The building can be rebuilt from floor-plan images.

Grading: 55 % automated correctness (the hidden "Sunday" building plus the test set), 25 % interaction rubric ("asks only what it needs, shows what it understood, gives directions a person can follow; voice counts"), 10 % creativity, 10 % demo video. The challenge text is in `docs/industrial-agents-hackathon-2026/README.md` and `docs/Hackathon Challenge - Talk to Your Building.pdf`.

## The one rule of the architecture

**Every fact comes from deterministic code. The LLM only parses language and words answers that have already been computed.**

- `floorwise/core` computes everything: geometry, routes, reachability, what-if edits. There is no LLM in it.
- The LLM turns text into a `QuerySpec` (`agent/parse_*`), drives tools (`agent/tools.py`), and phrases results.
- Never let a model estimate a distance, an area, a count or a route. If the model needs a fact, add a tool.

Why: LLMs are unreliable at geometry (FloorplanQA, ICML 2026), and the benchmark checks exact numbers. See `reports/Indoor wayfinding agent UX.md`.

## Map of the code

| Path | What it is | Status |
|---|---|---|
| `floorwise/core/analytics.py` | complete chat counts, item rankings/ties, content filters and grouped stats; benchmark semantics unchanged | unit-tested |
| `floorwise/core/scene.py` | cached schematic walls and opening gaps; display-only wall deduplication | unit-tested |
| `floorwise/agent/local.py` | free deterministic chat dispatch and validated parser-to-session adapter | unit-tested |
| `floorwise/core/model.py` | `Building`: typed, cached view of one `building.json` | verified |
| `floorwise/core/graph.py` | `RouteGraph`: the dataset's exact route model plus `Constraints` (step-free, min width, closed, avoid, soft-avoid, extra doors) | verified (L0 100 %) |
| `floorwise/core/geometry.py` | areas, 3D centroids, shared walls (0.35 m, ≥1 m), stacking, wall midpoint | verified (L1 100 %) |
| `floorwise/core/ops.py` | one operator per question family | verified (L1 100 %) |
| `floorwise/core/routing.py` | `plan_route`, tours, polyline | verified (L0 100 %) |
| `floorwise/core/walk.py` | humane walking lines per room: grid A* around furniture with clearance, door-exact smoothing; no entrance teleports for people (`Constraints(outside="none")`) | exact collision validation; dev: 134 validated / 160 sampled, 26 withheld |
| `floorwise/core/instructions.py` | followable directions: decision points, salient landmarks, floor-change steps, spoken overview (research §3) | unit-checked; wording reviewed by hand |
| `floorwise/core/resolve.py` | entity linking: floors, rooms, room types, item types, lifts; fuzzy, with candidates | verified on train/dev/test text |
| `floorwise/agent/spec.py` | `QuerySpec` (mentions) → solver inputs; ambiguity readings | verified |
| `floorwise/agent/parse_rules.py` | free regex parser for known phrasings | verified 655/655 + perturbations |
| `floorwise/agent/parse_llm.py` | LLM parser for unknown phrasings | live on Groq: 36/40 dev; Claude parser 39/40 in recorded prior run |
| `floorwise/agent/solve.py` | kind + inputs → result + reply ending in `Answer:` | verified |
| `floorwise/agent/answer.py` | benchmark entry `answer(dir, text)` | verified (kit evaluator 138/138 dev) |
| `floorwise/agent/session.py` | per-user state: closures, edits, profile, UI events | unit-tested |
| `floorwise/agent/tools.py` | LLM tools wrapping `Session` | live on Groq |
| `floorwise/agent/chat.py` | `ChatAgent` (provider-neutral) | live on Groq and Claude; five route/closure rehearsals verified |
| `floorwise/llm/` | provider layer: `anthropic` (prod), `groq`/`openrouter` (testing) | Groq verified |
| `floorwise/build/` | floor plan images → `building.json` (CV + learned palette + optional vision labels) | procedural 100 %; OSM/Swiss weaker |
| `floorwise/cli.py` | `run_benchmark` (Sunday command) | verified offline |
| `floorwise/fw.py` | `fw`: the one command | verified |
| `eval/` | eval suites L0–L7, ledger, report | see `docs/EVALS.md` |
| `server/app.py` | FastAPI: geometry, sessions, route/close/door, SSE chat, build | tested; chat live on Groq |
| `server/companion.py`, `web/src/companion/` | confirmed paired-phone relay and controller; `/phone`, touch/optional secure-context gyro | protocol + two-browser tested; physical hardware pending |
| `web/src/scene-assets/` | bounded illustrative procedural visuals for all supplied asset types | catalogue + footprint tests |
| `server/checks.py` | the Lab's inspection sheet: every check in plain words, target, cost, grading group | |
| `server/lab.py` | Benchmark Lab API: runs, compare, dataset, launch suites with live logs | tested |
| `web/src/navigator/` | Navigator UI (signage design, route sign, steps, step mode, voice) | desktop + phone regression coverage; see docs/STATUS.md |
| `web/src/lab/` | Benchmark Lab UI (overview, launcher, runs, drill-down on plan, compare, dataset) | Playwright |
| `docs/` | our docs plus the kit (`docs/industrial-agents-hackathon-2026`, read-only) | |
| `research_notes/`, `reports/` | sourced research behind the decisions | |

The full status matrix is in `docs/STATUS.md`. Update it whenever you change what works.

## Commands (everything goes through `fw`)

```bash
uv sync                      # once
uv run fw                    # list commands
uv run fw doctor             # check setup (keys, data, web build)
uv run fw start              # app at http://localhost:8000
uv run fw start --lan        # same app reachable by a phone on this network
uv run fw dev                # hot-reload dev (backend :8000, frontend :5173)
uv run fw check              # all offline tests + eval gates; must stay green
uv run fw ui-test            # Playwright UI tests (desktop + phone) against a fresh server
uv run fw submit             # regenerate submissions/team_floorwise_test.csv
uv run fw bench B Q OUT      # Sunday run (see BENCHMARK.md)
uv run fw eval <suite> ...   # one suite (docs/EVALS.md)
```

## Rules for changes

1. **Run `uv run fw check` before committing.** L0, L1, L2 and parser-test coverage must stay at 100 %. Any drop in `e2e`, `robust` or `metamorphic` must be explained in the commit message.
2. **No building-specific code.** Never put building IDs, room names or test-set strings in `floorwise/`. Test questions have no answers; never hand-label them (that is against the rules). The Sunday building is unseen.
3. **Semantics are settled against gold, then frozen.** Examples: "rooms" in reach counts means `type == "room"` including the start; shared walls exclude corridors, stairs and lifts but include halls. If you change one, re-run L1 on train+dev.
4. **LLM code must work on both providers.** Use `floorwise.llm` (`Conversation`, `structured.parse`, `tool`). Never import `anthropic` or `openai` outside `floorwise/llm/`, except in the build-vision labeller.
5. **Secrets live only in `.env`** (gitignored). The Groq key is for testing; no live Claude call has been verified on the current setup (Anthropic API or AWS Bedrock only, never Vertex).
6. **Keep docs true.** After a change, update `docs/STATUS.md`, and also this file if paths or commands change.
7. **UI work follows `docs/UX_PLAN.md`** and the design rules in it, not generic dashboard defaults.

## Data facts agents get wrong

- Coordinates are **metres** in one frame per building (some Swiss floors are centred per floor). Plan images have **no scale**: the builder needs one real dimension (or uses its door-width estimate).
- Route anchors are `representative_point()`, not centroids. Centroids are only for `straight_line_3d`.
- Stairs cost 12 m per floor; lifts cost 15 m plus 6 m per floor; entrances join at a free `outside` node. **That free hop is benchmark-only**: navigation for people uses `outside="none"` and the walking layer, and reports walking metres.
- LLM spend is capped per process (`FLOORWISE_MAX_TOKENS`, default 400k) with request timeouts. Lab jobs time out after 20 min and can be cancelled.
- OSM buildings repeat names (e.g. 9 × "Büro" on one floor). The benchmark path then solves every reading and votes; chat asks back.
