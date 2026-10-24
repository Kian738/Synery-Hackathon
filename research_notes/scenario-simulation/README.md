# Scenario simulation research (package D)

Research only: no solver, API or UI code. Everything describes an **idealised, explicitly parameterised building stress test** over a graph. It does not describe, and must not be presented as, a validated fire or smoke simulator, a predictor of real evacuation times, a code-compliance check, or instructions for trained responders.

| File | Contents |
|---|---|
| `01-flow-formulations.md` | max flow, min-cost flow, time-expanded flow and multi-commodity flow told apart; worked proof-by-example that nearest-exit and independent shortest paths fail; why capacity units change the problem |
| `02-demo-api-evidence.md` | smallest demo; mandatory unit-explicit input; objective and conflict policy; infeasible and unknown-data behaviour; result and evidence format compatible with `Session.publish_visual` |
| `03-validation-baselines-limits.md` | validation cases V1-V10, baselines B1-B5, what may and may not be claimed, novelty and limitations, scoped follow-on milestones |
| `04-landmark-multisensory-guidance.md` | landmark-based, multisensory guidance: evidence table with verification status and design rules |
| `05-sources.md` | every source with exact URL, publication date and what was actually opened |
| `06-integration-review.md` | integer-flow feasibility, service discretization and expanded-network size concerns before implementation |

**Open decision (blocks implementation, not research):** capacity units. "20 people per minute", "20 per simulation step" and "20 in total" are three different problems with different answers (see `01-flow-formulations.md`). The proposed input makes the basis mandatory and never guesses it.

Handoff: `docs/parallel/scenario-handoff.md`.
