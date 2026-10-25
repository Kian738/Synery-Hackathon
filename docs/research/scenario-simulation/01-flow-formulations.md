# 01 Flow formulations, and why independent shortest paths are not enough

Scope: an **idealised, explicitly parameterised stress test** of a building graph. It is not a fire, smoke or egress simulator and does not predict real evacuation times. See `03-validation-baselines-limits.md` for what may and may not be claimed.

## Vocabulary: four different problems that get called "flow"

| Problem | Question it answers | Time? | Commodities | Polynomial? | Fit here |
|---|---|---|---|---|---|
| **Max flow** (static) | What is the most people that can pass from sources to exits if each door has a total capacity? | no | 1 | yes | Only valid when the capacity is explicitly a *total* (`capacity_basis: "total"`). Says nothing about how long it takes. |
| **Min-cost flow** (static) | Among the ways to move everyone, which uses the least total cost (for example metres walked)? | no | 1 | yes | Cheap first pass: who goes to which exit when capacity is a total. Cost is distance, not time. |
| **Time-expanded flow** | With capacities per time step and walking delays, how many people are out by time T, and when is the last one out? | yes | 1 (or k) | yes for 1 commodity (a flow in a network with one copy of the graph per step: pseudo-polynomial in the horizon) | The core model for occupant evacuation. Also called a dynamic flow or flow over time. |
| **Multi-commodity flow** | Several groups with *different* origins and destinations share the same capacities. | usually yes | k >= 2 | LP: yes (fractional). Integral: **NP-complete already for two commodities** | Needed when responders (entrance to a specific target) compete with occupants (anywhere to any exit). |

Facts and where they come from (all links in `05-sources.md`):

- Flows over time were introduced by Ford and Fulkerson (Operations Research 6(3), 1958): the single-commodity maximal dynamic flow can be built from a static min-cost flow. The same literature notes this does not extend to several commodities (Bellmore and Vemuganti, Operations Research 21(1), 1973, as quoted in the search results; the paper itself was not read).
- With several sources and sinks and given supplies and demands, the **quickest transshipment** (minimise the time until everything has arrived) is solvable in polynomial time (Hoppe and Tardos, Mathematics of Operations Research 25(1), 2000). Skutella's survey (arXiv 2312.04991, 8 Dec 2023) calls transshipments over time "arguably the most difficult flow over time problem that can still be solved in polynomial time".
- Integral multi-commodity flow is NP-complete even with two commodities, directed or undirected (Even, Itai and Shamir, SIAM Journal on Computing 5(4), 691-703, 1976, per the abstract). Fractional multi-commodity flow is a linear programme.
- Evacuation-as-flow models in the literature: Hamacher and Tjandra (Fraunhofer ITWM report 24, 2001) review dynamic network flow approaches (minimum cost dynamic flow, maximum dynamic flow, quickest flow); Lu, George and Shekhar's capacity-constrained route planner (2003) is a heuristic reported close to optimal on a real building dataset (abstract: within 10% of optimal, about half the computation).

## Which problem is which in an evacuation question

1. **Occupants, any exit will do.** Everyone in a room is interchangeable and every exit is equally acceptable. That is a *single-commodity* problem with several sources and sinks: a transshipment over time. Polynomial, deterministic, and the right core for the demo.
2. **Occupants with a specific meeting point** (assembly point, refuge area): still one commodity per distinct destination. If there is one destination it is a single commodity.
3. **Responders going in to specific targets**, against the occupant flow, over the same doors: a second commodity with a different origin and destination that shares capacity. Genuine multi-commodity flow. Two modelling choices must be explicit, and neither is settled science:
   - whether a door's capacity is shared between directions (one pool) or per direction (two pools);
   - how much opposing flow reduces capacity (NISTIR 7425, April 2007, models firefighters ascending a stair against descending occupants with *occupants making room* rather than competing, and says that differs from the traditional definition of counterflow; it reports that responder use of the stairs "can significantly increase total building evacuation time". It is a simplified analysis calibrated on one drill).

   So `door_directionality` (shared pool or per-direction capacity) is a mandatory input with **no default**.
4. **Proposed door interventions** (widen, add, reopen, close) change capacities or edges; evaluating one is a re-solve, not a new model.

## Why routing everyone to the nearest exit is insufficient

Nearest-exit routing optimises each person's *distance* and ignores that exits have finite throughput. Worked toy case (all numbers are **assumed scenario inputs**, chosen to be checkable by hand):

- Two groups of 60 people (A and B). Two exits, X and Y. Each door passes **1 person per 3 s (20 people per minute)**.
- Walk times in seconds: A to X 10, B to X 12, A to Y 30, B to Y 28. Everyone in a group reaches the door together (idealised).
- **Nearest exit for everyone** (both groups choose X): 120 people through one door. The k-th person passes at 10 + 3(k-1) s, so the last passes at **367 s**.
- A to X and B to Y (one group per door): X is done at 187 s, Y at 205 s, makespan **205 s**.
- Optimal split (63 through X, 57 through Y; three of B's people use X): both doors finish at **196 s**, which is 47% shorter than nearest-exit. (Checked by enumerating every split.)

The error is structural: shortest paths are computed one traveller at a time against an *empty* building, so shared capacity never enters the objective.

**Units matter, and they change the answer.** The same sentence "each door has capacity 20" means three different problems:

| Reading | Meaning | Result for the case above |
|---|---|---|
| 20 people per minute | 1 person per 3 s, time-expanded | 196 s optimal makespan |
| 20 people per simulation step (step = 3 s) | 400 people per minute | six steps of 20 people, so the last of 120 passes X at about 10 + 5 x 3 = 25 s (the door stops being the bottleneck) |
| 20 people in total through that door | static max flow | at most 40 of the 120 people can ever leave: infeasible, report the shortfall |

Therefore the proposed input requires `capacity_basis` (`per_minute`, `per_step` or `total`) next to every capacity and refuses to run without it. Nothing infers a basis.

## Why two independent shortest paths do not optimise competing flows

Second toy case, one door shared by both directions, with the shared-pool assumption stated above:

- Door D passes 1 person per 3 s in total, either direction. A second exit D2 is 40 s further for occupants and also passes 1 per 3 s.
- 30 occupants arrive at D at t = 10 s (at D2 at t = 50 s). 4 responders arrive at D at t = 40 s, heading in.
- **Independent shortest paths** (each party takes its own shortest route, first come first served at D): occupants use D and finish at 97 s; the responders queue behind them and cross at **100, 103, 106, 109 s**.
- **Responders get strict priority, occupants still all use D**: responders cross at 40 to 49 s but the last occupant leaves at **109 s**.
- **Joint decision** (responders have priority at D, occupants are split between D and D2): 20 occupants use D, 10 use D2; responders cross at **40 to 49 s**, the last occupant leaves at **79 s**. (Checked by enumerating all splits.)

The joint solution is better for both parties than either per-party shortest-path policy. The responders' path and the occupants' paths cannot be chosen independently, because the decision for one changes the capacity the other sees. That is exactly the distinction between independent shortest paths (a route per traveller) and a flow decision (a quantity per arc and time step). The case also shows why the *conflict policy* in `02-demo-api-evidence.md` must be an explicit input: "responders first" is a policy, not a mathematical fact.

A third distinction worth stating once: **merging all commodities into one super-source and one super-sink answers a different question.** In a network with only the edges s1-t2 and s2-t1, the merged max flow is 2, yet commodity s1-to-t1 has no path at all. It is safe to merge occupants only because they are interchangeable; responders are not.

## Time-expanded construction (for the follow-on)

For step length dt (explicit) and horizon T = n steps: one node per (place, step); a "wait" arc from (v, t) to (v, t+1) with capacity equal to the space's holding capacity (an input, because the building data has areas but no occupant density limit); a "move" arc from (u, t) to (v, t + ceil(walk_time/dt)) with capacity `door_capacity_per_step`; supplies at (room, 0); exits connect to a sink with no capacity. Maximising people out by T is a max flow; minimising the last arrival is the smallest T that is feasible (binary search on T); minimising total person-time among those is min-cost flow with unit time costs on wait arcs. Rounding walk times up to the step is a stated approximation whose error is bounded by dt per leg. The size is pseudo-polynomial in T/dt, which is acceptable for a floor or a building of this data's size (see `03-validation-baselines-limits.md` for a size estimate to confirm before building).
