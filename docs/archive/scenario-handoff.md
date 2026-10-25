# Package D: multihop scenario simulation research — READY (research only)

Status: **READY.** The research is actionable; the follow-on is blocked on one user decision (capacity units). No production solver, API or UI code was written, and no file outside `docs/research/scenario-simulation/**` and this handoff was touched.

Read in this order: `docs/research/scenario-simulation/README.md`, then files 01 to 05 there.

## The seven deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Smallest worthwhile demo: **two-door stress test**, occupants only, one floor, headcounts and capacities supplied by the user, result compared with a fair nearest-exit-with-queues baseline, one door-intervention re-solve | `02-demo-api-evidence.md` section 1 |
| 2 | Deterministic input / result / evidence proposal, reusing `Session.publish_visual` with `kind: "intervention"` (no TypeScript change needed first); four labelled evidence blocks (supplied facts, scenario assumptions, computed results, unsupported effects) | `02` sections 2, 5, 6 |
| 3 | Objective (lexicographic: people out, then last-out time, then total person-time, then deterministic tie-break) and conflict policy (`responders_first`, `shared_fifo`; door directionality explicit) | `02` section 3 |
| 4 | Infeasible and unknown-data behaviour table: ask for missing fields, never default; `partial`/`infeasible` with the min cut and the stranded groups; spreading hazards refused | `02` section 4 |
| 5 | Validation cases V1-V10, baselines B1-B5, reuse of NIST TN 1822's component structure | `03` section 5 |
| 6 | Novelty (an integration contribution, not a new algorithm), claims allowed and forbidden, limitations | `03` section 6 and "What may and may not be claimed" |
| 7 | Scoped follow-on in milestones M1-M6 with acceptance tests | `03` section 7 |

Plus the guidance research (landmark-based, multisensory, with an evidence table that says which sources were actually opened): `04-landmark-multisensory-guidance.md`.

## Key findings

1. **Four problems are being called "flow".** Max flow (static, totals), min-cost flow (static, cost), time-expanded flow (time and capacity per step, polynomial for one commodity) and multi-commodity flow (integral version NP-complete already for two commodities: Even, Itai and Shamir 1976). Occupants who may use any exit are one commodity with several sources and sinks: a transshipment over time, solvable exactly. Responders going to specific targets add a second commodity and need either an LP or an explicit priority policy.
2. **Nearest-exit routing is structurally insufficient.** Toy case (assumed numbers, hand-checkable): two groups of 60, two doors at 20 people per minute: everyone to the nearest door finishes at 367 s; the optimal split finishes at 196 s (47% shorter), found by enumerating all splits. Shortest paths are computed against an empty building, so shared capacity never enters.
3. **Independent shortest paths do not optimise competing flows.** Second toy case (one door shared by both directions, an assumption): independent first-come routing leaves the responders crossing at 100 to 109 s and the occupants finished at 97 s; the joint decision gets responders through at 40 to 49 s *and* occupants out at 79 s, better for both. "Responders first" is a policy, so it is an explicit input.
4. **Units change the answer, not just the scale.** "Capacity 20" read as 20 per minute, 20 per step (3 s steps) or 20 in total gives respectively a 196 s optimum, a door that is no longer the bottleneck (about 25 s), and an infeasible problem (at most 40 of 120 can leave). The proposed input requires `capacity_basis` and refuses without it.
5. **The data does not supply what the model needs.** There is no occupancy and no door throughput; door width is supplied, but converting width to people per minute is an assumption that must be explicit. Connector interiors are not surveyed (stairs are illustrative per STATUS.md), so stair traversal is an assumption too.
6. **Evidence for landmark guidance is about route recall and direction quality, not evacuation outcomes.** Verified: decision points and turns are remembered better than straight segments (Meilinger et al., 2014); more landmark mentions go with higher-rated directions (Lovelace et al., 1999); landmark-related instruction detail improved later retracing, recognition and sketch maps in a driving simulator (Gramann et al., 2017); about four route segments was best for indoor recall (Nourin et al., arXiv 2024). No source read shows that landmark cues speed up or improve evacuation, so none is claimed.

## What I could not verify (so the notes do not claim it)

- NIST TN 1822's individual verification and validation tests were not read (only the abstract); NIST TN 1680 and IMO MSC.1/Circ.1533 were identified from catalogue or search summaries and their full texts were not read.
- The ISO 21542 "two-sense" idea I had in mind was **not found** in the material available; no multi-sensory requirement is attributed to it. WCAG 1.4.1 and 1.3.3 (read) are cited by analogy and are not wayfinding or fire standards.
- The Bellmore and Vemuganti 1973 statement, the Hoppe and Tardos details, and Even, Itai and Shamir's abstract come from search results, not from opening the papers. Lu et al.'s paper showed no nearest-exit comparison in what I could read, so none is attributed to it.
- The in-repo UX report's cited 4-versus-6-8-segment percentages were not re-checked against the paper body.

## Pending user decision

**Capacity units.** Per minute, per simulation step, or total throughput are three different problems (finding 4). The demo should ship with `per_minute` only once the user confirms it; until then the design carries `capacity.basis` as a required field. No hazard progression, occupancy, capacity or speed is assumed anywhere in the proposal.

## Do not claim (repeat for any slide or UI copy)

A validated fire or smoke simulator; real or predicted evacuation times; code compliance; instructions for trained responders; that a proposed door change makes a building safer; that chaining language-model tool calls is a research contribution. The suggested standing sentence is in `02-demo-api-evidence.md` section 6.

## Verification performed

Documents only; no code or tests. The two toy cases were enumerated by a throwaway script and the building-size figures counted from the supplied files (both described in `05-sources.md`).
