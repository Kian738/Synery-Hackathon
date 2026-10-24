# BRIEFING — 2026-10-24T14:03:30Z

## Mission
Investigate requirements, feasibility, and technical architecture for R3: Interactive Visualizer & Real-Time Operational Dispatcher (2D/3D stacked floor plans, assets, animated routes, live dispatch/updates, voice-assisted navigation).

## 🔒 My Identity
- Archetype: explorer
- Roles: Survey Specialist 3 (Visualization, Real-Time Dispatch & Voice Navigation)
- Working directory: /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/.agents/teamwork/teamwork_preview_explorer_survey_3/
- Original parent: 99a36772-9103-445c-a001-17463bb30980
- Milestone: Investigation & Technical Architecture Plan for R3

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Write metadata and reports only in your working directory
- Output handoff to /Users/konstantin/Programmation/Hackathon/Je_regrette_rien/industrial-agents-hackathon-2026/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md

## Current Parent
- Conversation ID: 99a36772-9103-445c-a001-17463bb30980
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `starter_agent/viewer.py` (inspected: static matplotlib 2D PNG output only)
  - `starter_agent/building_map.py` (inspected: graph model, route, set_closed, add_door, search)
  - `starter_agent/tools.py` & `starter_agent/agent.py` (inspected: Claude tool wrappers)
  - `benchmark/score.py` & `benchmark/evaluate.py` (inspected: scoring rules and format)
  - `data/dev/proc-factory-dev-003/building.json` & `floor_0.svg` (inspected: geometry, floors, spaces, openings, assets)
  - Repository scan for web/frontend files: 0 existing web assets
  - Python runtime environment: standard library `http.server.ThreadingHTTPServer` available, `networkx`, `shapely`, `pydantic` installed
- **Key findings**:
  - Zero existing frontend/web files exist. Existing `viewer.py` is purely static Matplotlib PNG generation.
  - Recommended backend architecture: Python stdlib `http.server.ThreadingHTTPServer` REST API (zero extra dependencies, starts in <0.1s, 100% zero-configuration out-of-the-box).
  - Recommended rendering architecture: Three.js WebGL multi-floor stacked 3D + 2D orthogonal top-down toggle, exploded view spacing slider, extruded room polygons, asset footprints, 3D animated route tube with traveling beacon.
  - Recommended dispatcher architecture: REST endpoints `/api/closure`, `/api/add_door`, `/api/route` integrated directly with in-memory `BuildingMap`, immediate route recalculation with visual diff highlighting and audio announcement.
  - Recommended voice architecture: Browser-native Web Speech API (`SpeechRecognition` + `SpeechSynthesis`), fast local intent parser + agent fallback, seamless graceful fallback to text input.
- **Unexplored areas**: None for R3 survey scope.

## Key Decisions Made
- Architecture design complete: stdlib zero-config server + Three.js 3D/2D frontend + Web Speech API + interactive dispatch tools.
- Package as `visualizer/` module runnable via `python -m visualizer [building_dir]` or `uv run python -m visualizer`.

## Artifact Index
- DISPATCH.md — incoming dispatch instructions
- BRIEFING.md — working memory and identity
- progress.md — liveness heartbeat
- handoff.md — final 5-component handoff report
