# Architecture

Floorwise has one Python package for all computation (`floorwise/`), a FastAPI server (`server/`), a React app (`web/`) and an evaluation harness (`eval/`). The rule that shapes everything: **facts come from deterministic code, and the language model only parses and words** ([ADR 001](adr/001-deterministic-facts.md)).

```
                 ┌──────────── web/ (React, Vite, three.js) ─────────────┐
 text / voice ──►│ Navigator: chat, 2D plan, 3D scene, Guide me, Lab     │◄── phone companion (/phone, WebSocket)
                 └───────────────┬──────────────────────▲────────────────┘
                     REST + SSE  │                      │ UI events (highlights, routes, scenarios)
                 ┌───────────────▼──────────────────────┴────────────────┐
                 │ server/app.py + routers (lab, scenario, stress, voice, │
                 │ companion, campus, insight)                            │
                 └───────────────┬────────────────────────────────────────┘
                                 │
        ┌────────────────────────▼─────────────────────────┐
        │ floorwise/agent: ChatAgent ─► tools ─► Session   │──► floorwise/llm (Anthropic | Groq | OpenRouter)
        └────────────────────────┬─────────────────────────┘
                                 │ typed calls, no model in this layer or below
   ┌─────────────────────────────▼─────────────────────────────────────────────┐
   │ floorwise/core: model, graph, spacewalk, routing, walk, instructions,      │
   │ geometry, ops, resolve, resilience, fixes, scene, stair_scene, campus      │
   ├──────────────────────┬──────────────────────┬─────────────────────────────┤
   │ floorwise/evacuation │ floorwise/reason     │ floorwise/stress            │
   │ exact flow over time │ multi-hop plans      │ per-person queue simulation │
   └──────────────────────┴──────────────────────┴─────────────────────────────┘
        ▲
        │ building.json (kit data, or a reviewed draft from floorwise/build)
```

## Building model and routing

- [`core/model.py`](../floorwise/core/model.py): `Building`, a typed and cached view of one `building.json` (floors, spaces, openings, items). Coordinates are metres, one frame per building.
- [`core/spacewalk.py`](../floorwise/core/spacewalk.py): the judges' walking rule from kit 1.1.0. Walking is measured door to door inside each space, 15 cm off the walls, around corners, and a door lands 30 cm inside the space. The result is cached on disk per building (`runs/.walk-cache`).
- [`core/graph.py`](../floorwise/core/graph.py): `RouteGraph` with stairs at 2 m per metre climbed and lifts at 15 m per ride plus 1 m per metre climbed. It has no outside shortcut. `Constraints` covers step-free, minimum width, closed and avoided places, soft avoid, forklift and production bays. The graph is checked edge for edge against the kit's own `starter_agent/building_map.py` (`eval/differential.py`).
- [`core/routing.py`](../floorwise/core/routing.py): `plan_route`, tours and polylines. The search is Dijkstra on the building graph; inside a room, the drawn walking line uses A* over a visibility graph ([`core/walk.py`](../floorwise/core/walk.py)).
- [`core/instructions.py`](../floorwise/core/instructions.py): turns a route into decision-point steps with landmarks, floor changes as separate steps, and a short spoken overview.

**Three meanings of distance** ([ADR 002](adr/002-three-routing-semantics.md)) are never mixed:

1. **Benchmark cost:** the official route model above. Furniture is ignored.
2. **Human walking line:** drawn around recorded furniture. A preview that would cross a wall or furniture is withheld and counted, never drawn ([`core/preview_check.py`](../floorwise/core/preview_check.py)).
3. **Exit-rooted impact:** which rooms keep a way to any exit after a closure ([`core/resilience.py`](../floorwise/core/resilience.py)). It reports graph cost, not metres walked.

## Language layer

- **Benchmark path:** [`agent/answer.py`](../floorwise/agent/answer.py) `answer(dir, text)` calls the rule parser ([`parse_rules.py`](../floorwise/agent/parse_rules.py)), which produces a `QuerySpec` ([`spec.py`](../floorwise/agent/spec.py)). The solver ([`solve.py`](../floorwise/agent/solve.py)) then returns a reply that ends in `Answer: ...`. Route answers list the spaces passed through, or `no route`. Only wording the rules do not cover goes to the LLM parser ([`parse_llm.py`](../floorwise/agent/parse_llm.py)). When a name has several readings, the benchmark path solves each reading and votes; chat asks back instead.
- **Chat path:** [`agent/chat.py`](../floorwise/agent/chat.py) `ChatAgent` runs a tool loop ([`llm/loop.py`](../floorwise/llm/loop.py)) over typed tools ([`agent/tools.py`](../floorwise/agent/tools.py), [`agent/insight_tools.py`](../floorwise/agent/insight_tools.py)). The tools wrap a per-user `Session` ([`agent/session.py`](../floorwise/agent/session.py)), which holds closures, edits with undo, the person's profile (for example step-free), the declared start, and the UI events for the app. Tool schemas stay fixed for a whole conversation, so the provider's thinking signatures stay valid. Token spend is capped per process (`FLOORWISE_MAX_TOKENS`) and requests have timeouts ([`llm/budget.py`](../floorwise/llm/budget.py)).
- **Providers:** `FLOORWISE_PROVIDER=anthropic|groq|openrouter` ([`llm/__init__.py`](../floorwise/llm/__init__.py)). Code outside `floorwise/llm/` never imports a provider SDK. The one exception is the vision labeller in `floorwise/build/label.py`.

## Scenarios

| Module | Model | Used by |
|---|---|---|
| [`floorwise/evacuation`](../floorwise/evacuation) | Exact quickest evacuation on a time-expanded capacity graph: binary search on the horizon, minimum cut for bottlenecks, responder routes, greedy door add or widen that is re-solved on an edited copy, and a CCRP baseline | Fire test panel, `plan_scenario` chat tool, `/api/sessions/{id}/scenario` |
| [`floorwise/reason`](../floorwise/reason) | Multi-hop plans as typed operator DAGs (hazard, people, exits, evacuation, bottleneck, responders, door candidates). Each step has a postcondition; if a step fails, the plan abstains and names the step. | `plan_scenario` |
| [`floorwise/stress`](../floorwise/stress) | Per-person queue simulation on `RouteGraph`. Uses SFPE door flow (1.316 persons/s per metre of effective width), a log-normal pre-movement delay and spread walking speeds. Door ideas that worsen the 95th percentile are flagged and never offered. | Evacuation test panel, `/api/sessions/{id}/stress` |

The stress simulation takes every length and rule from the same `RouteGraph` as navigation, so the two cannot disagree ([`tests/test_stress_sim.py`](../tests/test_stress_sim.py) checks that a free-flow walk equals `plan_route`). Every result returns its assumptions. None of these modules models smoke or fire spread.

## Scene compile (3D)

[`core/scene.py`](../floorwise/core/scene.py) compiles schematic walls and door gaps from the analytical polygons. Duplicate and coplanar display walls are merged, and the analytical geometry is never changed. [`core/stair_scene.py`](../floorwise/core/stair_scene.py) fits display-only stair shafts that stay inside the shared stair polygons. If no honest fit exists, the flight is withheld. On the web side, `Building3D.tsx` owns the scene, focus and camera; `Connectors3D.tsx` the stairs; `LiftShafts.tsx` the animated lifts; and `SceneAssets.tsx` with `scene-assets/` the procedural models for the 96 supplied item types. AGENTS.md rules 8 to 17 describe the UI and 3D rules.

## Floor-plan import

[`floorwise/build`](../floorwise/build) reads plan images. It segments colour regions with OpenCV (using a learned palette), finds doors and entrances, scales the plan from one real dimension, stacks the floors, and can label rooms with Claude vision. The output is a draft `building.json` that a person reviews before it is used ([ADR 003](adr/003-reconstruction-is-a-draft.md)). Measured quality: [RECONSTRUCTION_VALIDATION_RESULTS.md](RECONSTRUCTION_VALIDATION_RESULTS.md).

## Server

[`server/app.py`](../server/app.py) serves the built web app (`web/dist`) and the API. It covers buildings and thumbnails, sessions, geometry and scene, routes, closures with preview, doors and undo, and SSE chat with cancel. Routers add the Lab (`server/lab.py`, `/api/lab`), scenarios (`server/scenario.py`), the stress test (`server/stress.py`), voice (`server/voice.py`, `/api/voice`), the phone relay (`server/companion.py`, pairing plus a WebSocket), routes between buildings (`server/campus.py`) and insight tools (`server/insight.py`). `/healthz` returns `{"ok": true}`.

## Web app

| Path | What |
|---|---|
| `web/src/navigator/` | The main screen: chat, plan, 3D, Guide me, Building tools (Outside, Evacuation test, Fire test, Phone, Stress test, Evidence) |
| `web/src/components/` | Scene parts, panels and the guide player |
| `web/src/ui/` | The control kit (`kit.css`, `kit.tsx`): the only place where control sizes, radii and gaps are defined |
| `web/src/companion/` | Phone pairing, remote, AR route ribbon (`ArRoute.tsx`, WebXR `immersive-ar`) |
| `web/src/lab/` | Benchmark Lab |
| `web/src/map/`, `web/src/journey/` | Map entry screen and trips between buildings |

## Evaluation

`eval/` holds one module per suite. Each suite writes `runs/<time>_<suite>/` (`results.jsonl`, `summary.json`) with a source fingerprint. `uv run python -m eval gates` runs the offline gates and fails on any miss that is not diagnosed in `eval/known_issues.json`. See [TESTING.md](TESTING.md).
