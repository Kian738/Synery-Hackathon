# Handoff: multi-hop scenario engine (for Codex or anyone picking this up)

State at handoff: all offline gates, `pytest` (362) and `fw ui-test` (128 passed, 30 skipped) were green on the branch that added this.

## Map
| What | Where |
|---|---|
| Plan DAG, typed operators, per-step checks, abstention, templates | `floorwise/reason/` (`execute.py`, `operators.py`, `templates.json`, `elicit.py`) |
| Evacuation as flows over time, responders, door synthesis, N-1 robust doors | `floorwise/evacuation/` (`solve.py`, `ten.py`, `responders.py`, `doors.py`, `robust.py`) |
| Glue from plan steps to the solver | `floorwise/reason/evac_ops.py` (`DEFAULT_ESCAPE_S = 30`, an assumption) |
| Findings per audience, door names, capacity arithmetic | `floorwise/reason/findings.py` |
| One report dict for API and chat tool | `floorwise/reason/report.py` |
| REST: `POST /api/sessions/{id}/scenario`, `.../scenario/ask` | `server/scenario.py` |
| Chat tool for Claude: `plan_scenario(hazard_rooms, audience)` | `floorwise/agent/insight_tools.py` |
| UI: drawer inside the Navigator, hazard hatch on plan, red room in 3D | `web/src/navigator/ScenarioPanel.tsx`, `PlanView.tsx`, `Building3D.tsx` |
| Checks | `eval scenarios` (stress), `eval unseen` (test split risk), `eval.sensitivity` (physics band), `tests/test_scenario_api.py`, `web/tests/scenario.spec.ts` |

## Rules that must not break
- Every number comes from a solver step; Claude words it. A failed step abstains and is named.
- Nothing is hard-coded to a building, room or number. Hazards, occupants, capacities and escape time are inputs.
- Say "re-solved", never "verified", for fixes: it is self-consistency, not validation against Pathfinder or a drill.
- Known limits: occupants = seat count estimate, no smoke or fire model, optimistic walking times, not a compliance check.
- Anthropic API or AWS Bedrock only, never Vertex. One Bedrock call was verified (see README); `boto3` is not a repo dependency.

## Open items
- N-1 robust doors: `POST /api/sessions/{id}/scenario/robust`, opt-in button "Check if an exit fails" in the panel (about 20 s, so never automatic).
- Level 3 multi-building is not implemented: no supplied data has linked buildings; floors, stairs and lifts are done.
- Voice is browser speech only; ElevenLabs needs a key.
- Hazard hatch and slow-door markers are on the 2D plan; the 3D view colours the hazard room only.
- Scenario view is desktop-only (the phone opens in follow mode, like Stress test).
- Playwright uses 4 workers and 15 s assertions: three specs failed only under full parallelism (shared server load), never alone.
- Sunday submission format is unconfirmed (answers.json with node ids vs CSV `question_id,answer`).
- Pitch notes are in `building-agent-research/PITCH_IDEAS_INTERNAL.md` (not finalised).
