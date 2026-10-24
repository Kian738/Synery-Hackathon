# 03 Validation, baselines, novelty, limits and the follow-on plan

## 5. Meaningful validation cases and baseline comparisons

None of this validates the model against *people*. It validates that the code solves the stated mathematical problem correctly and that its answers behave sensibly. Real-world validity would need experimental data (see "What may be claimed" below).

### Correctness (the solver does what the model says)

| # | Case | Expected, and how it is checked |
|---|---|---|
| V1 | One door, N people, capacity c per minute, walk time w | Closed form: last-out = w + ceil(N/c_step) steps; exact equality, over a grid of N, c, w and step length, including N not divisible by c |
| V2 | The two toy cases in `01-flow-formulations.md` | 196 s for the two-exit case (63/57 split, found by exhaustive enumeration and by the solver), 79 s and responders at 40 to 49 s in the shared-door case; the hand-checkable seed tests |
| V3 | Max-flow = min-cut | On random small graphs the reported flow value equals the capacity of the reported cut; the cut doors are exactly those named in `min_cut` |
| V4 | Conservation and capacity invariants | For every step: flow in = flow out + change in occupancy per space; no arc exceeds capacity; people out never exceeds people in; no one is in a blocked space after `from_s` |
| V5 | Metamorphic properties | Adding capacity never increases last-out; adding a blocked door never decreases it; translating or rotating the building changes nothing; permuting group order or ids changes nothing; splitting one group into two with the same rooms changes nothing; doubling step length changes last-out by at most one step per leg |
| V6 | Units | The same scenario expressed as per-minute and as per-step (converted) gives equal results; a missing `capacity_basis` is refused; `total` returns no times |
| V7 | Independent cross-check | Re-solve the same time-expanded graph with a separate implementation (the kit's independent graph code is already used for `fw eval differential`; a second max-flow routine over the same arcs is enough) and compare flow values, per the existing differential pattern. An off-the-shelf solver (for example OR-Tools or NetworkX, whose documentation describes their min-cost-flow and max-flow routines) is acceptable as a *test-only* oracle if a dependency is allowed |
| V8 | Determinism | Same canonical input gives byte-equal output across processes and platforms (the tie-break order is part of the contract) |
| V9 | Real building shapes | Run all 280 supplied buildings with a fixed, stated scenario (every room one person, 20 per minute per door, 1.2 m/s) and check invariants V4 and V5 on each; this tests the graph plumbing at scale, not realism. Size estimate to confirm: median building 54 spaces and about 60 openings; the largest supplied building has 1,623 spaces and 1,799 openings. With a 3 s step and 600 s horizon that is roughly 11 thousand nodes for the median building and a few hundred thousand nodes (about a million arcs) for the largest, which is fine for a median floor and needs pruning (reachable region only, one floor or wing at a time) for the largest |

### Behaviour on infeasible and unknown data

V10: every row of the table in `02-demo-api-evidence.md` section 4 has one test: missing headcount asks, ambiguous room name lists candidates, a closure that strands a step-free group reports `infeasible` with the closure named, a binding door is reported in `min_cut`, a spreading-hazard request is refused as unsupported, and the answer text contains no number that is absent from `measurements`.

### Baselines (what the flow model must be compared with, and reported against)

| Baseline | What it is | Why it is included |
|---|---|---|
| B1 Nearest exit, independent | Each group takes its shortest path to its nearest exit; time = walking only | The naive approach; shows the structural error (47% longer in the toy case) |
| B2 Nearest exit with queues | Same routes, but doors process FIFO at their capacity | The **fair** baseline: removes the cheapest criticism. The flow model's gain over B2 is the honest number to report |
| B3 Shortest path avoiding closures | The existing `plan_route` with closed elements | Shows closures are handled by both |
| B4 Greedy sequential | Route group 1 optimally, then group 2 in the residual capacity | Shows the order-dependence that joint optimisation removes (relevant from phase 2) |
| B5 Random feasible assignment | Uniformly random exit per group | Sanity floor: the model must beat it |

Reporting rule: always show B2 next to the model, with the delta, and show results as "under these stated numbers". If B2 equals the model (distance-limited rather than capacity-limited scenarios), say so; that is a valid finding.

### Published validation material to reuse, not to claim

NIST Technical Note 1822 (Ronchi, Kuligowski, Reneke, Peacock, Nilsson, November 2013) states that no international standard defines how to verify and validate building fire evacuation models, reviews existing procedures (including maritime tests borrowed from IMO guidance), groups tests under five model components (pre-evacuation time, movement and navigation, exit usage, route availability, flow conditions and constraints) and proposes simple qualitative validation tests and example datasets. The abstract was read; the individual tests were **not** read. The follow-on should read the "flow constraints" and "route availability" tests in full and adopt those that apply to a graph-and-capacity model, citing each by number, and should state plainly that the "pre-evacuation time" and "behaviour" components are outside this model. IMO MSC.1/Circ.1533 (6 June 2016, revised guidelines on evacuation analysis for passenger ships) is the maritime counterpart; per its preamble (as reported by Lloyd's Register's notice, circular text not read) an analysis assesses performance against benchmark scenarios rather than simulating an actual emergency, which is the same stance this stress test must take.

## What may and may not be claimed

May claim: a deterministic, unit-explicit, cross-checked flow model of a stated graph and stated assumptions; exact answers to that model; transparent baselines; honest refusal when inputs are missing; interventions evaluated *within the model*.

May **not** claim: a validated fire or smoke simulator; real or predicted evacuation times; compliance with any building code or standard; instructions for trained responders or emergency procedures; that a proposed door change would make a building safer; that chaining language-model tool calls is itself a research contribution. NIST TN 1680 (Kuligowski, Peacock, Hoskins, 2010) reviews 25 existing evacuation models, so the algorithms are not new either.

## 6. Research novelty and limitations

**Novelty, stated modestly.** The flow-over-time algorithms (Ford and Fulkerson 1958, Hoppe and Tardos 2000) and evacuation formulations (Hamacher and Tjandra 2001, Lu et al 2003, and the models reviewed in NIST TN 1680) are established. What this project could add is an *integration contribution*: a pipeline from a natural-language scenario to a validated deterministic flow model over a graph reconstructed from floor plans, with mandatory units, refusal on missing data, an evidence trail that separates supplied facts, assumptions, computed numbers and unsupported effects, a fair baseline reported next to the model, and an intervention evaluator in the same visual language as the rest of the app. That is useful engineering and a defensible demo; it is not a new algorithm and not a publishable result on its own. A publishable claim would need at least one real evacuation dataset, a pre-registered comparison, and review by fire-safety engineers.

**Limitations to state in the product.**

- Flow models treat people as an interchangeable fluid with per-step arc capacity; no individual behaviour, no density-dependent speed (NISTIR 7425's drill data show speed falling with occupant density on stairs; this model ignores that unless a per-connector speed is supplied), no pre-movement time, no exit choice, no group cohesion, no mobility mixes beyond step-free routing, no elevators, no stair geometry (connector interiors are not surveyed in the data).
- Door capacity is a user number or a user-stated width rule; the building data has widths, not throughput.
- Hazard is a step change at most. No smoke, heat, visibility or toxicity.
- Opposing flow (responders) depends on an assumption about whether doors are shared pools; NISTIR 7425 itself models responders as occupants making room, calibrated on a single drill in a six-storey office building, and reports a high-rise case under assumptions it lists (no delays, no mobility impairment, nearest exit), so its numbers are not transferable and are not used here.
- Time discretisation adds up to one step of error per leg.
- Multi-commodity integral optimisation is NP-complete; phase 2 uses a stated priority policy, not the global optimum.
- Capacity units are **pending user clarification** (per minute, per step, or total). Until the user chooses, the design carries all three as an explicit `basis` and the demo ships with `per_minute` only if the user confirms it.

## 7. Scoped follow-on implementation (after the user fixes the capacity units)

Milestones, each with an acceptance test from the validation list:

1. **M1 (about one day):** `floorwise/core/scenario.py`, pure Python, no new dependency: input validation and the refusal table; time-expanded graph from `RouteGraph` edges plus door widths and explicit capacities; max-flow plus search for the horizon plus min-cost tie-break; B1 and B2 baselines. Acceptance: V1, V2, V3, V4, V6, V8, V10 green; V7 with a second max-flow routine.
2. **M2:** `Session.run_scenario` and one agent tool that takes the JSON, calls it, and publishes `kind: "intervention"` with the measurement block from `02-demo-api-evidence.md`; the chat asks for missing fields from the refusal table. Acceptance: reply contains only numbers present in `measurements` (test); known-wording turns still make zero model calls.
3. **M3:** UI panel (people-out chart, door saturation on the plan, baseline delta, assumption list always visible) and door-intervention re-solve reusing the preview pattern. Acceptance: Playwright flow at 1440 and 390 px, empty/error/infeasible states present.
4. **M4:** V5 and V9 at scale across all supplied buildings in a new `scenario` eval suite (free, offline) with a gate that checks invariants, never realism.
5. **M5 (optional):** responders under `responders_first` and `shared_fifo`; B4; the numeric toy cases as tests. Only then consider an LP-based weighted multi-commodity option, which needs an LP solver dependency and an explicit decision to add one.
6. **Before any external claim:** read NIST TN 1822's flow and route-availability tests in full, adopt the applicable ones, and have a fire-safety professional review the limitations text.
