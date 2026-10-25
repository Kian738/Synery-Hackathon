# 02 Smallest worthwhile demo, input/result/evidence proposal, objective and conflict policy

No solver, API or UI code is part of this package. Everything below is a proposal for a follow-on (see section 7 of `03-validation-baselines-limits.md`).

## 1. Smallest worthwhile hackathon demo

**"Two-door stress test", occupants only, one floor.** Chosen because it is single-commodity (polynomial, exact, checkable by hand), visual, and honest.

1. The user names a floor and one or more groups: "40 people in Lab 2.17, 25 in Office 2.04", **with a headcount for each** (the data has none).
2. The user states the unavailable space or door: "Lift 2 is out, the east corridor is blocked" (existing closure tools and `Constraints` already express closed connectors and closed elements).
3. The user states door capacity with units: "doors pass 20 people per minute, walking speed 1.2 m/s, time step 3 s".
4. The tool returns, in one visual result: people out by time (a small step chart), the last-out time **under the stated assumptions**, which doors saturate and when, and the comparison with the **nearest-exit baseline** (independent shortest routes, and the fairer baseline of nearest exit with FIFO queues at doors).
5. One intervention button reuses the existing preview pattern: "what if door X were 1.2 m wide / reopened": a re-solve, with the same visual and a delta.

Not in the demo: responders, counterflow, hazard growth, mobility mixes, stairs speed reduction. Phase 2 adds responders under an explicit priority policy (section 5). The demo is a stress test of a *graph under stated numbers*; the screen says so.

## 2. Mandatory input (units are required, nothing is defaulted)

A scenario is a JSON document. Missing required fields make the tool **ask** (one closed question per missing item, listing what is needed) or refuse; it never fills them in.

```json
{
  "scenario_version": 1,
  "building_id": "…",
  "time": { "step_s": 3, "horizon_s": 600 },
  "capacity": { "basis": "per_minute",  "door_people": { "default_ref": null, "overrides": { "<opening_id>": 20 } },
                "width_rule": null },
  "speed": { "walk_mps": 1.2, "stairs_mps": null, "step_free_only_groups": [] },
  "door_directionality": null,
  "groups": [ { "id": "g1", "name": "Lab 2.17", "space_ids": ["…"], "people": 40, "needs_step_free": false } ],
  "unavailable": { "space_ids": [], "opening_ids": [], "connector_ids": [], "from_s": 0 },
  "exits": { "space_ids": ["…"] },
  "responders": null,
  "policy": { "conflict": "responders_first", "objective": "last_out_then_total_time" },
  "assumptions_acknowledged": ["hazard_static", "no_pre_movement_delay", "no_density_slowdown"]
}
```

Rules:

- **`capacity.basis` is required** and is one of `per_minute`, `per_step`, `total`. A per-door number without it is rejected. `per_minute` and `per_step` run the time-expanded model; `total` runs a static max flow and reports **no times** (it has none).
- Capacity is **not derivable from the data**. The building data supplies door width (`width_m`), but converting width into people per minute needs a flow-per-metre coefficient, which is a modelling assumption. Allowed only as an explicit `width_rule` (for example `{ "people_per_min_per_m": … }`), never as a hidden default. If neither a per-door value nor a `width_rule` is given, the tool asks.
- `people` per group is required (no occupancy data is supplied). `walk_mps` is required for any time output; without it the tool can still return the static (no-time) flow and says times are unavailable.
- `speed.stairs_mps` is required only if stairs appear, and `door_directionality` only if responders appear. Connector interiors have no surveyed geometry in the data (STATUS.md: landing transitions, not continuous flights), so a stair's traversal time is an explicit assumption or a stated per-connector input.
- `unavailable.from_s` is when the space becomes unusable. The model supports only a **step change** (usable until `from_s`, then not). A hazard that *spreads* is not supported (sections 4 and 5). Omitting it means "blocked from t = 0", and the result states that.
- `assumptions_acknowledged` makes the limits visible and testable. The tool lists the list it used in every result.

## 3. Objective and conflict policy

Lexicographic, so ties never depend on solver internals:

1. **Maximise people out by the horizon** (max flow in the time-expanded network). If not everyone can leave, stop here and report the shortfall and the cut (section 4).
2. **Minimise the last-out time** (smallest feasible horizon, found by search over the horizon).
3. **Minimise total person-time** among solutions with that last-out time (min-cost flow with unit cost per waiting or walking step).
4. **Deterministic tie-break**: fixed ordering of groups, doors and steps by identifier, so equal inputs always give byte-equal results.

Occupants are fractional by default (people may be split across routes, as in all flow models); the result also gives an integer rounding (largest-remainder per group) and says which it shows.

Conflict policy for phase 2 (responders):

- `responders_first`: responders get strict priority on the arcs they use, then occupants are optimised in the residual capacity (this is what produced 79 s in the toy case: `01-flow-formulations.md`). It is a **policy**, deterministic and polynomial; it is not the global optimum of a weighted multi-commodity problem and is labelled as such.
- `shared_fifo`: no priority (the independent-shortest-paths behaviour with queues); useful as a baseline.
- `weighted`: only if a multi-commodity LP solver is added later; weights are explicit inputs.
- `door_directionality` is required whenever responders are present: `shared_pool` (both directions together may not exceed the door's capacity: the assumption behind the toy case) or `per_direction` (each direction has the full capacity: no interference). These are the two ends of a modelling choice, not a measured law; how much opposing flow really reduces throughput is not settled by anything in this package, so no intermediate factor is offered and neither value is a default. A numeric reduction can be added later only with a cited source or the user's own stated figure.

## 4. Infeasible and unknown-data behaviour

| Situation | Behaviour |
|---|---|
| A required field is missing (headcount, capacity basis, speed for times) | Ask for exactly that field (one closed question), or refuse. Never default. |
| A named room is ambiguous (same name, same floor) | Use the existing ask-back or list the candidates (as the chat path already does); never pick one silently. |
| Not everyone can reach any exit (disconnected by closures or step-free needs) | Result `status: "infeasible"`, with `unreachable_groups` (and for step-free groups, the name of the closure responsible) and the maximum number who can leave. No time is reported for the stranded. |
| Everyone can leave but not within the horizon | `status: "partial"`: number out at the horizon, the shortfall, and the **min cut**: the doors whose capacity limits the flow, with utilisation per step. This is the explanation, derived from the residual graph, not text. |
| Hazard that changes over time | Refused as unsupported unless it is a step change (`from_s`). The result lists "hazard progression" under unsupported effects. |
| Capacity given as a total but a time is requested | Static result only; says "a total capacity has no time". |
| The graph model cannot validate a route (the human-walking layer withheld guidance, see `core/walk.py`) | The flow model uses graph edges only and states that drawn lines are schematic; it does not claim a walkable path. |
| Result would be identical for every plausible capacity | State it ("limited by distance, not by door capacity"): a useful finding, not a failure. |

## 5. Result and evidence: compatible with existing Session visual results

`Session.publish_visual(kind, title, ids, measurements, rows, lines, warnings)` already carries a typed result to the UI (`VisualResult` in `web/src/lib/types.ts`: `id`, `kind`, `title`, `entities`, `floor_ids`, `measurements`, `lines`, `warnings`, `provenance`; rows are paged server-side). Proposal: **reuse `kind: "intervention"` first** (no TypeScript change), and add `"scenario"` to the union only if the UI needs a dedicated panel. Fields:

- `entities`: the doors that carry flow or saturate (`openings`), blocked spaces (`rooms`), groups' rooms.
- `measurements` (all numbers deterministic, all labelled with units):
  - `scenario_hash` (hash of the canonical input), `model: "time_expanded_flow_v1"`, `step_s`, `horizon_s`, `capacity_basis`;
  - `status` (`ok`/`partial`/`infeasible`), `people_total`, `people_out`, `last_out_s`, `total_person_time_s`;
  - `out_by_time`: `[[t_s, cumulative_out], …]`;
  - `doors`: per door, `flow_people`, `peak_utilisation`, `saturated_from_s` and `until_s`;
  - `baselines`: `nearest_exit_independent`, `nearest_exit_fifo` (each with `last_out_s`), and `improvement_vs_fifo_s`;
  - `min_cut`: opening ids when `status` is not `ok`.
- `rows`: one row per (group, exit) allocation: people, route as graph nodes, walk time, queue time.
- `lines`: one 3D segment per used route leg (existing `a`/`b` format), thickness encoded in `measurements`, not in the geometry.
- `warnings`: every assumption the run depended on, plus every unsupported effect, in plain words.
- `provenance`: "Idealised flow model using the stated assumptions; not a fire, smoke or egress simulation."

**Evidence separation.** The result carries four labelled blocks so a reader (and a test) can tell them apart: **supplied facts** (graph, door widths, closures from the building data and their ids), **scenario assumptions** (everything the user stated, echoed back verbatim with units), **computed results** (numbers above), **unsupported effects** (a fixed list: fire and smoke spread, pre-movement and reaction time, door-opening time, density-dependent speed, mobility mixes, elevators, stair geometry, group cohesion, behaviour and exit choice, alarm and signage effects). The agent may phrase the result but may not add a number; every number in the reply must come from `measurements` (same rule as AGENTS.md: the model only words computed results).

## 6. Anti-claims for every output

The reply and the visual always include: "This is an idealised stress test of the building graph under the numbers you gave; it is not a validated evacuation or fire simulation, gives no real evacuation times, and is not a code-compliance check or an instruction for responders." Interventions are described as "changes the modelled capacity by X", never as "makes the building safer".
