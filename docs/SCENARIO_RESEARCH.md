# Scenario module research: egress, stress tests, door recommendations

Date: 2026-10-25. Scope: what to implement so the Scenarios module is a defensible building stress-test engine. Research only; no code was changed.

Evidence labels: **[opened]** = the source page or PDF was read in this session. **[search]** = only seen in a search snippet. **[memory]** = background knowledge, no source opened (listed again in the last section). Anything marked [memory] or [search] must be re-checked before it appears in a UI string or a claim to judges.

Framing, as in `research_notes/scenario-simulation/README.md`: the module is an idealised, parameterised stress test, not a validated fire simulator and not a code-compliance check. It can still use the code numbers below as defaults and as "flags".

## 0. What the repo already has (so we do not rebuild it)

| Existing | What it does | Gap |
|---|---|---|
| `floorwise/evacuation/` (`solve.py`, `ten.py`, `adapter.py`, `doors.py`, `responders.py`, `robust.py`) | Exact quickest evacuation on a time-expanded capacity graph (binary search on horizon, min-cut bottleneck), `best_doors` = greedy add/widen of doors pruned by the min cut, re-verified on an edited copy. Params: 1.316 p/s/m, 0.15 m boundary, 1.34 m/s, stairs x0.7, dt 5 s. | Macroscopic only: no density, no queue geometry, no LOS, no per-person times (p50/p95 need a schedule-to-person mapping). `adapter.py` states it deliberately does **not** use `core/graph.py` route costs, so it can disagree with navigation (see section 7). |
| `floorwise/core/resilience.py` (`chaos_test`) | Single-element closure analysis rooted at exits: rooms lost per element. | Unweighted by occupants; no time dimension. |
| `floorwise/reason/occupants.py`, `evacuation/types.py::Occupants` | Occupants from seat-type assets (0.5 m seat pitch for rows), user overrides, uniform. | No occupant-load-factor default for rooms without seats (section 6). |
| `research_notes/scenario-simulation/` | Flow formulations, validation cases V1-V10, baselines. | Not yet tied to the standards below. |

The 1.316 p/s/m and 0.15 m boundary are the SFPE door-flow rule as implemented by Pathfinder: a 1 m door flows at 1.316 x (1.0 - 2 x 0.15) = 0.92 p/s [opened: https://www.thunderheadeng.com/docs/2024-1/pathfinder/verification-validation/]. The repo is therefore already consistent with the IMO door-flow test (below).

## 1. Standards and numbers we can implement directly

### 1.1 German (primary for this dataset)

ASR A2.3 (workplaces). Main escape-route minimum clear widths, from the BGN transcription of the ASR text [opened: https://vorschriften.bgn-branchenwissen.de/daten/tr/asr_a2_3/5.htm]:

| Persons in catchment | Doors/passages (m) | Main escape route (m) |
|---|---|---|
| up to 5 | 0.80 (0.90 recommended for new buildings) | 0.90 |
| up to 20 | 0.90 | 1.00 |
| up to 50 | 0.90 | 1.20 |
| up to 100 | 1.00 | 1.20 |
| up to 200 | 1.05 | 1.20 |
| up to 300 | 1.65 | 1.80 |
| up to 400 | 2.25 | 2.40 |

Between 200 and 400 persons the table is interpolated linearly. Special cases: aisle to a personal workplace 0.60 m; toilet cubicle door 0.55 m. Legacy relaxations (buildings applied for before 30.9.2022): 0.875 m route for up to 5 persons, 0.85 m doors in the 20-person row.

Stairs (same page, Tab. 2): persons per floor up to 30 -> stair 1.00 m, door after stair 0.90 m; up to 40 -> 1.20 / 1.05; up to 50 -> 1.40 / 1.25; up to 60 -> 1.80 / 1.65; up to 70 -> 2.40 / 2.25. Alternative: stair at least 1.20 m for up to 65 persons per floor with sequential evacuation of at most 3 floors. Main escape routes: no compensating steps, no spiral stairs, escalators or ladders; curved stairs only if width <= 1.40 m and inner diameter > 2.00 m. Clear height of route >= 2.10 m (not below 2.00 m); doors >= 2.10 m (not below 1.95 m).

Lengths [opened: https://vorschriften.bgn-branchenwissen.de/daten/tr/asr_a2_3/5.htm]: escape route length up to 35 m (normal fire risk, or increased risk with automatic extinguishing), 25 m (increased risk without extinguishing), 10 m (explosion hazard); toxic-hazard rooms 20 m appear only in a secondary summary [search: https://www.lfv-bayern.de/media/filer_public/57/91/57915861-845b-43f8-bc7f-f32eee4f8488/fluchtweg.pdf]. The actual walking length may be at most 1.5 x the permitted escape route length. Our `RouteGraph` lengths are walking lengths, so the check is: walking length to the nearest exit or protected stairwell <= 35 m "escape length" (the ASR measures the shortest line; if we measure walking length we are conservative, and the 1.5 factor gives the hard upper bound 52.5 m).

Doors (ASR A2.3 section 6 [opened: https://vorschriften.bgn-branchenwissen.de/daten/tr/asr_a2_3/6.htm]): doors and emergency exits in wall openings "should" open in the escape direction (6.2(6)); sliding doors are permitted; an additional secondary escape route is required for production/storage/workshop rooms over 200 m2 and other work rooms over 400 m2; emergency exit wall openings at least 0.90 m x 1.20 m. Door narrowing by leaves/frames: at most 0.15 m, never below 0.80 m [search: https://forum-verlag.com/blog-bs/asr-a2-3-fluchtwege-notausgaenge]. The ASR transcription does **not** define dead ends (section 8 only requires that no backlog can form at the end of a route [opened: https://vorschriften.bgn-branchenwissen.de/daten/tr/asr_a2_3/4.htm]).

Building law: BayBO Art. 33(2) (state version of MBO section 33): from any point of a habitable room at least one exit to a protected stairwell or outdoors within 35 m [search: https://www.gesetze-bayern.de/Content/Document/BayBO-33]; two independent escape routes per storey is the MBO rule per commentary [search: https://www.baunetzwissen.de/treppen/fachwissen/brand--schallschutz/brandschutzanforderungen-fuer-flucht--und-rettungswege-167600]. Assembly venues (Bavarian VStaettV section 7, MVStaettV equivalent) [search: https://www.gesetze-bayern.de/Content/Rtf/BayVStaettV-7?all=False]: max 30 m from any visitor place to the nearest exit of the hall; clear width 1.20 m per 200 persons (1.20 m per 600 outdoors/stadiums), widths staggered in 0.60 m steps, minimum 1.20 m (0.90 m for halls up to 200 places). Hall and lecture-theatre rooms in the dataset should use the VStaettV numbers; offices use ASR A2.3. Switzerland: no source opened (VKF fire protection rules are the analogue; treat as the same order of magnitude and say so).

### 1.2 US codes (for the numbers judges may know)

| Item | Value | Source |
|---|---|---|
| IBC capacity factor stairs / other components | 0.3 in / 0.2 in per occupant (7.6 / 5.1 mm) | [search] multiple secondary sources, e.g. https://floridabuilding.org/fbc/commission/FBC_1024/Acc_Adv_Council/686/686_2_ADDITION_DOC_8101-LS1-01-Layout1.pdf. NFPA 101 uses different factors; MeyerFire says so but its page body was not retrievable [search: https://www.meyerfire.com/university/what-is-an-exit-capacity-factor]. Do not quote NFPA 101 values until checked. |
| Dead-end corridor | 20 ft (6.1 m) general; 50 ft (15 m) in fully sprinklered B, E, F, I-1, M, R-1, R-2, S, U; unlimited if shorter than 2.5 x corridor width | [opened] ICC training deck https://iccsafe.org/wp-content/uploads/2021-IBC-Means-of-Egress.pdf (extracted locally) |
| Common path of egress travel | 75 ft general in the deck's worked example; 100 ft sprinklered business | [opened] same deck; [search] https://www.sjcfl.us/wp-content/uploads/2023/08/Business-Annual-Checklist.pdf |
| Travel distance, business | 200 ft unsprinklered, 300 ft sprinklered (NFPA 101); educational 150 / 200 ft | [search] https://open-exam-prep.com/study-guides/cfps-fire/safety-in-the-built-environment/means-of-egress-components |
| Stair min width | 44 in (36 in for small occupant loads) | [opened] ICC deck |
| Occupant load factors (m2/person): business 150 gross sf = 13.9; concentrated business (call centres) 50 gross sf = 4.6 | business 150 confirmed | [search] https://www.sandiego.gov/development-services/forms-publications/technical-bulletins/10-1 |
| Other IBC 1004.5 rows (classroom 20 net sf = 1.9 m2; assembly unconcentrated 15 net = 1.4 m2; concentrated 7 net = 0.65 m2; standing 5 net = 0.46 m2) | **[memory], not confirmed** | check against IBC Table 1004.5 |

NFPA 130 (transit stations) [search: Seattle amendment https://www.seattle.gov/documents/departments/fire/business/nfpa130amendments2012sfc.pdf]: platform occupant load must clear in 4 minutes or less; stair capacity 0.0555 persons/mm width/min (1.41 per inch) with vertical travel speed 14.6 m/min (Washington rule https://lawfilesext.leg.wa.gov/law/WACArchive/2022/htm/WAC%20%2051%20%20TITLE/WAC%20%2051%20-%2050%20%20CHAPTER/WAC%20%2051%20-%2050%20-3116.htm); escalators count for at most half (WA) or 25 % (Bellevue) of capacity. The 6-minute point-of-safety rule was not confirmed. Use only for a "station/mass event" preset.

### 1.3 Concepts

- ASET/RSET (SFPE): RSET = alarm/detection + pre-movement (recognition, response) + movement time; the design passes if ASET > RSET with a margin [search: https://fire-risk-assessment-network.com/blog/aset-rset/ and https://nuoro.ordingegneri.it/wp-content/uploads/sites/45/2021/04/Giordano%2003-Modulo-S1-Esodo.pdf]. Example tenability limits seen: visibility > 10 m, CO < 950 ppm, air temperature < 80 C at 2 m. We have no fire/smoke model, so the engine reports **RSET only**, and ASET becomes an **input** (a user-set "time until route X becomes untenable"), which we model as a time-triggered closure. Never present a pass/fail without that label.
- ISO 20414:2020 "Fire safety engineering: verification and validation protocol for building fire evacuation models" (published Nov 2020, confirmed 2026), aimed at agent-based models but adoptable for macroscopic ones if they can represent the tested components; Annex A is a reporting template [search: https://www.iso.org/standard/78348.html]. ISO 16738 (egress assessment) and ISO 23932 (general FSE principles): not verified.

## 2. Crowd and evacuation models

| Model | Core equation / idea | Inputs it needs from us | Cost | Fits a room-and-door graph? |
|---|---|---|---|---|
| Fruin LOS | Static density bands; no dynamics | Area per room | trivial | Yes, as a **display scale** |
| Weidmann fundamental diagram | v(rho) = v0 (1 - exp(-gamma (1/rho - 1/rho_max))), v0 = 1.34 m/s, gamma = 1.913 m-2, rho_max = 5.4 m-2 [search: https://arxiv.org/pdf/1512.01166 and summary https://arxiv.org/pdf/0901.0170; the closed form is [memory]] | Corridor length, width | O(1) | Yes: edge travel time as a function of load |
| Predtechenskii-Milinskii (1978) | Speed and flow as polynomials of dimensionless density with person area ~0.125 m2; separate emergency factors; stair relations [search: https://arxiv.org/pdf/1303.4695] | Same | O(1) | Yes, macroscopic. Its statistical validity is disputed (Kholshevnikov et al.) |
| SFPE/Nelson-MacLennan flow | Specific flow max 1.316 p/s/m, 0.15 m door boundary layer, speed-density profile (Pathfinder tails to factor 0.15 rather than 0) | Door widths | O(1) | Already in the repo |
| Macroscopic dynamic network flow | Time-expanded graph, quickest flow / quickest transshipment / earliest-arrival flow; LP or min-cost flow; gives lower bounds on evacuation time, no individual behaviour; exact method may not finish on big instances (12 h) while heuristics run in < 1 s [search: https://kluedo.ub.rptu.de/files/1477/bericht24.pdf, https://arxiv.org/pdf/1312.0489] | Capacities, lengths, supplies | LP size = nodes x T | Already implemented (`evacuation/ten.py`) |
| Cellular automata | Grid cells, floor field, conflict resolution | Grid of the plan | O(agents x steps) | Needs a grid; loses exact lengths |
| Social force (Helbing-Molnar 1995) | Newtonian: driving + repulsion + wall forces, Langevin noise [opened summary: https://arxiv.org/pdf/cond-mat/9805244] | Continuous geometry, many parameters, small dt | Heaviest, stiff, overlaps at high density | Poor fit |
| Collision-free speed model, CFSM (Tordeux et al. 2016) | Speed = optimal-velocity function of headway; direction = weighted exponential repulsion; collision-free by construction, lower cost than force models [opened summary: https://arxiv.org/pdf/1512.05597] | Continuous geometry | Medium | Only inside a room polygon |
| Optimal steps (Vadere, LGPL) | Agent picks the best next step on a circle around itself on a potential field | Continuous geometry | Medium | Poor fit |
| RVO2 / ORCA velocity obstacles | Reciprocal half-plane constraints, linear program per agent | Continuous geometry | Cheap per agent | Not verified (license, Python bindings are third-party forks [search: https://github.com/wangck123/Python-RVO2]) |

### Recommendation: implement two, both on the graph

1. **Macroscopic queueing network on the existing graph (primary).** Per-edge travel time = exact walking length / speed(rho) using Weidmann for density-dependent speed, door service limited at width-based specific flow (1.316 x (w - 0.3)), stair edges with the stair speed factor and stair LOS capacity. Run as a discrete-event "agent packet" simulation: each person is an object walking the route graph; a door is a server with rate J(w); queue length at a door is observable. This gives per-person egress times (p50/p95), queue lengths per door, density per room (people / room area), and heat maps, in milliseconds. It uses the same edge lengths as navigation.
2. **The existing time-expanded min-cost flow as the optimal baseline.** It gives the lower bound T* ("best case if everyone were routed perfectly"). The ratio T_sim / T* is a headline KPI ("routing efficiency") and is also a consistency check: T_sim must never be below T* (invariant, section 7).

Why not microscopic: a continuous model (CFSM, JuPedSim) would need a walkable polygon per floor with correct holes (our `walk.py` has walkable rooms and furniture, but it is not built for a solver loop), and we cannot calibrate or validate it in two days. If a micro-model is wanted for the demo, JuPedSim's CFSM is the right one (below), run only on a **single selected room or corridor** as a "zoom-in" validation, not on the whole building.

### Validation tests we can reproduce

IMO MSC.1/Circ.1533 tests as run by Pathfinder (IMO_01 to IMO_11) [opened: https://www.thunderheadeng.com/docs/2024-1/pathfinder/verification-validation/ ]. Reproducible cheaply on a graph model: 

| Test | Setup | Expected | Graph model? |
|---|---|---|---|
| IMO_01 movement speed | 2 m x 40 m corridor, 1.0 m/s | 40.0 s (SFPE) | Yes, exact |
| IMO_02/03 stairs | 10 m incline, 7"x11" stairs, 1.0 m/s base | 12.99 s | Yes, if stair speed table is implemented |
| IMO_04 door flow | 8 x 5 m room, 1 m door, 100 persons | mean flow <= 1.33 p/s; SFPE 0.92 p/s, so ~109 s | Yes |
| IMO_05 initial delay | 10 persons, delays 10-100 s | each person starts at own delay | Yes |
| IMO_07 multiple speeds | 50 persons, speeds 0.97-1.62 m/s, 40.5 x 51 m room | first/last arrival 24.7 / 41.2 s | Yes (straight-line walk) |
| IMO_08 counterflow | 100 persons + 0/10/50/100 counterflow in a 10 x 2 m corridor | time increases with counterflow; pure SFPE does not slow | No (needs bidirectional interaction); skip |
| IMO_09 available doors | 1000 persons, 1 m doors, 4 vs 2 | SFPE 271 s vs 541 s (roughly doubles) | Yes, doubling is a strong invariant |
| IMO_11 congestion | 150 persons, stairs, density >= 3.5 p/m2 at stair base | queue forms at stair base | Partly (queue yes, density needs a footprint) |
| IMO_06 rounding corners, IMO_10 exit assignment | geometry / assignment | no wall crossing; assigned exit used | Trivially satisfied by a graph model |

RiMEA guideline tests: Test 1 = keep the prescribed walking speed in a 40 m corridor (1.3 m/s, 500 runs, accepted duration 26-34 s), Test 2 = stairs 10 m at 0.65 m/s [search: https://www.traffgo-ht.com/downloads/pedestrians/downloads/RiMEA%20Testbericht%20PedGo.pdf]; Test 4 = fundamental diagram (specific flow vs density) [search: https://www.sne-journal.org/sne-volumes/volume-25/sne-251-articles/a-comparison-of-microscopic-pedestrian-simulation-models-based-on-rimea-test-cases]; Test 11 = 1000 agents, two doors of unequal distance, exit width 1 m (same source). Tests 5, 6, 10, 12, 13 are named (response time, rounding corners, exit allocation, bottleneck effect, staircase) [opened: https://traffgo-ht.com/en/pedestrians/validation/rimea/index.html]. The full RiMEA 3.0/4.0 list was **not** retrievable; get it from rimea.de before claiming "RiMEA compliance". Claim only "reproduces IMO_01, 02, 03, 04, 05, 07, 09 analytic expectations" at most.

## 3. Open-source and commercial tools

| Tool | Licence / status | Python API | Take-away |
|---|---|---|---|
| JuPedSim | LGPL-3.0; PyPI `jupedsim` 1.4.2, Python >=3.10,<3.15; C++ core [opened: https://pypi.org/pypi/jupedsim/json, https://github.com/PedestrianDynamics/jupedsim]; models: CollisionFreeSpeedModel (variants incl. V3 rotational steering) and GeneralizedCentrifugalForceModel; WarpDriver listed [opened: https://www.jupedsim.org/stable/] | `jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=shapely_polygon, trajectory_writer=jps.SqliteTrajectoryWriter(...))`, `add_exit_stage(polygon)`, `add_journey(jps.JourneyDescription([exit_id]))`, `add_agent(jps.CollisionFreeSpeedModelAgentParameters(journey_id=..., stage_id=..., position=..., radius=0.12))`, `iterate()` [opened: https://www.jupedsim.org/stable/notebooks/getting_started.html] | Best candidate for an optional zoom-in micro-check; geometry in shapely. Stages: exits, waypoints, waiting sets/queues. LGPL is fine to import dynamically. |
| Vadere | LGPL; optimal steps, gradient navigation, social force [search: https://www.vadere.org/?p=614, https://arxiv.org/pdf/1907.09520] | Java GUI/CLI, not Python-first | Reference for the OSM model only |
| SUMO | EPL-2.0 (from memory); has a JuPedSim interface [search: https://sumo.dlr.de/docs/Tutorials/Jupedsim/JuPedSim_Intro.html] | TraCI | Not relevant to indoor evacuation |
| Pathfinder (Thunderhead) | Commercial. Steering, SFPE and Steering+SFPE modes; default acceleration reaches max speed in 1.1 s; V&V against IMO 1533 and RiMEA | GUI/ API | The comparison target. Its V&V page is our test spec. |
| buildingEXODUS, MassMotion, CrowdSim | Commercial / not opened | - | Not verified in this session |

## 4. Door placement and bottleneck algorithms

Building blocks:

- **Flow-weighted edge betweenness** (Brandes): for every origin with occupants o_s and every exit, route the occupants along shortest/min-cost paths and accumulate load per door; load / capacity = utilisation. Cheap, explains "where the crowd goes".
- **Max-flow / min-cut**: the minimum cut of the time-expanded network at the last infeasible horizon is the bottleneck set; a new door helps only if it touches that cut. Already used in `evacuation/doors.py` (pruning). Use it to explain "this wall of 3 doors is the limit".
- **Shortcut value (SV)** of a candidate door c between rooms a, b with length l_c: SV(c) = sum over (s,t) of w_st x max(0, d(s,t) - d_c(s,t)), where d_c(s,t) = min(d(s,t), d(s,a) + l_c + d(b,t), d(s,b) + l_c + d(a,t)). Exact for one added edge. Choosing k edges to minimise average shortest-path length is NP-hard and has no simple approximation guarantee [search: https://www.cs.uoi.gr/~tsap/publications/sdm2015-paper.pdf]; related shortcut objectives (hitting time) are supermodular with bicriteria greedy results [search: https://arxiv.org/pdf/2306.03571]; effective graph resistance is non-submodular [search: https://arxiv.org/html/2501.03363v1]. So: **greedy with lazy re-evaluation, no (1 - 1/e) claim**, and say "greedy, not optimal" in the UI (the repo already does).
- **Space syntax / visibility graph analysis**: integration = closeness-like (to-movement), choice = betweenness-like (through-movement) [search: https://link.springer.com/chapter/10.1007/978-3-030-59140-3_2]. For us: choice = flow-weighted betweenness above; integration = mean weighted distance to all rooms. Report as "central rooms" in the 2D view; do not run full VGA on a grid.
- **Braess-type effects**: in a centrally optimal flow model, adding a door cannot increase the optimum (max flow is monotone). With selfish or nearest-exit assignment, or with limited route knowledge, an added opening can worsen times. Evidence is mixed: a 2025 experiment/model study finds the paradox unlikely under full knowledge and high demand but possible with limited knowledge [search: https://arxiv.org/html/2509.11736v1]; two contiguous exits can fail to help [search: https://arxiv.org/abs/1607.07379]. Consequence: our simulator (assignment rule = shortest path, like real people) can show a regression. Report it as a finding ("this door redirects people into the stair queue"), do not suppress it.
- **Equity**: for each candidate also report the step-free reach delta (rooms newly reachable step-free, mean step-free-to-standard route ratio). Rank with a lexicographic or weighted score; show both.

### Ranking pseudocode (about 90 lines of Python when written; well under 200)

```
INPUT
  G           RouteGraph over rooms (nodes) + door nodes, exact walking lengths, widths, step_free flags
  occ[r]      occupants per room (section 6 defaults)       exits = set of exit nodes
  budget_k    number of doors to recommend                  w_new = 0.9 m   # single leaf, as in evacuation/doors.py
  sim(G, occ, scenario) -> Result(T_p50, T_p95, queue[door], load[door], unreachable)

1  # --- candidates
   cand = []
   for floor in floors:
     for (a, b) in room_pairs_sharing_wall(floor, min_len=1.0 m):      # core/geometry.shared_walls
       if door_between(a, b) exists: continue
       pos = clear_wall_position(a, b, w_new)                          # existing door-placement logic
       if pos is None: continue                                        # no free wall segment
       l_c = leg(anchor(a) -> pos) + leg(pos -> anchor(b))             # same spacewalk legs as navigation
       cand.append(Candidate(a, b, pos, l_c, w_new))

2  # --- distances once
   D = all_pairs_dijkstra(G, weights="length")                         # rooms only, |V| <= ~300
   Dsf = same with step_free-only edges
   OD = {(s, t): occ[s]  for s in rooms, t = nearest exit by D[s]}     # evacuation demand
        + {(s, t): w_nav for navigation pairs, optional}               # daily demand, optional

3  # --- cheap exact score for every candidate  O(|cand| x |OD|)
   for c in cand:
     SV = 0
     for (s, t), w in OD:
        d_new = min(D[s][t], D[s][c.a] + c.l + D[c.b][t], D[s][c.b] + c.l + D[c.a][t])
        SV += w * (D[s][t] - d_new)
     c.SV = SV                                   # person-metres saved
     c.SVf = same with Dsf and unreachable -> big M           # step-free equity
     c.max_save = max(D[s][t] - d_new over OD)
     c.over35 = # occupants whose nearest exit moves from > 35 m to <= 35 m        # rule-based gain

4  # --- bottleneck relevance
   base = sim(G, occ, scenario); cut = min_cut_of_last_infeasible_horizon(G)
   for c in cand: c.touches_cut = c.a in cut_side_A and c.b in cut_side_B or path through cut
   keep top M=15 by (SV + big * touches_cut)                           # prune before simulating

5  # --- simulate survivors (each sim is milliseconds on the packet model)
   for c in keep:
     r = sim(G + c, occ, scenario)
     c.dT95 = base.T_p95 - r.T_p95
     c.dQ   = base.max_queue - r.max_queue
     c.regress = r.T_p95 > base.T_p95 + eps          # Braess flag
     c.dUnreach = len(base.unreachable) - len(r.unreachable)
     c.dBridges = count of cut vertices/bridges before - after       # resilience (chaos_test)

6  # --- greedy selection of k doors with lazy re-evaluation
   chosen = []
   for i in 1..budget_k:
     best = argmax over keep of  score(c) = a1*dT95 + a2*SV/total_occ + a3*dUnreach + a4*dBridges + a5*SVf/total_occ  - a6*regress*BIG
     if best.score <= 0: break
     chosen.append(best); G = G + best; recompute D, base, cut (only for the remaining top M)
   return chosen with per-door before/after KPIs and the reason string

7  # --- verify (same pattern as evacuation/doors.py)
   fresh = sim(edit_copy_of_building(chosen), occ, scenario)
   assert fresh.T_p95 == chain result      # independent re-run
```

Why this ordering: step 3 is exact and cheap, so the full candidate set is ranked without simulation; step 5 spends the simulator only where a queue exists; the output always carries person-metres saved (explainable to a human) next to simulated minutes (the stress-test claim).

## 5. Visualisation spec

Professional practice [search/opened as noted]: PTV Viswalk colours areas by LOS using a density attribute in ped/m2 with schemes from Fruin, Weidmann, HCM and others, offers Red-Amber-Green and Green-Amber-Red ramps, and forces areas that reached or exceeded a capacity limit to red in every scheme [opened: https://cgi.ptvgroup.com/vision-help/VISSIM_2025_ENG/Content/3_Darstellung/Farben_Fugae_LOS_verw.htm]. Fruin walkway bands (space per person) [opened: https://www.fhwa.dot.gov/publications/research/safety/pedbike/98107/section3.cfm]:

| LOS | m2/person | persons/m2 (derived) | flow ped/min/m |
|---|---|---|---|
| A | > 3.2 | < 0.31 | <= 23 |
| B | 2.3-3.2 | 0.31-0.43 | 23-33 |
| C | 1.4-2.3 | 0.43-0.71 | 33-49 |
| D | 0.9-1.4 | 0.71-1.1 | 49-66 |
| E | 0.5-0.9 | 1.1-2.0 | 66-82 |
| F | < 0.5 | > 2.0 | variable |

Stairs (HCM-recommended, reflecting Fruin's breakpoints, same page): A 1.9 m2/p, B 1.6-1.9, C 1.1-1.6, D 0.7-1.1, E 0.5-0.7, F < 0.5. Queuing areas: A >= 1.21 m2/p, B 0.93-1.21, C 0.65-0.93, D 0.27-0.65, E 0.19-0.27, F < 0.19. HCM walkway bands are far more generous (A >= 12 m2/p) and not appropriate for emergency stress tests; say which scale the legend uses. For an emergency the meaningful alert threshold is about 2 p/m2 (E/F) and the Weidmann flow peak near 1.7 p/m2 (computed from the formula above: speed 0.81 m/s at 1.5 and 0.61 at 2.0, specific flow ~1.21 p/s/m, falling to 0.63 at 4.0 and 0 at 5.4).

### Colour ramps (colour-blind-safe by construction: monotone lightness, no red-green pairing)

- **Density / LOS (sequential, 6 steps, light to dark):** A `#F7FBFF`, B `#C6DBEF`, C `#FEE391`, D `#FD8D3C`, E `#D7301F`, F `#67000D`. Lightness drops steadily so the ordering survives deuteranopia and greyscale; the hue goes blue -> yellow -> orange -> dark red. This ramp is my design (ColorBrewer-style endpoints), not tested here with a CVD simulator; run one before the demo.
- **Time / isochrones (sequential):** viridis stops `#440154`, `#3B528B`, `#21908D`, `#5DC863`, `#FDE725` (viridis is the standard perceptually uniform, CVD-safe ramp; [memory]).
- **Before/after diff (diverging, blue-orange, never red-green):** improved `#2166AC` -> neutral `#F7F7F7` -> worse `#B35806`.
- **Categorical (routes, exits, scenarios):** Okabe-Ito `#E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7 #000000` [memory; the source page https://jfly.uni-koeln.de/color/ was opened but the values are an image there].
- **Hazard / blocked:** hatch pattern + `#000000` outline, never colour alone (WCAG: two cues).

### 3D floor view (three.js)

- Floors as extruded translucent slabs with floor-explode slider (z gap), room footprints as a single `InstancedMesh`/`ShapeGeometry` per room with a **vertex-colour or DataTexture lookup** (value -> LOS ramp), so recolouring is one buffer update per frame, not material churn.
- Layers (toggle, one active at a time for the heat layer): density now, peak density, time-to-clear (isochrones), utilisation of doors (door = bar sized by flow/capacity), diff.
- Doors: tube or quad at the door position, colour = utilisation (load / capacity), thickness = width; **bottleneck marker** = a pin with a queue-length number and a ring whose radius ~ queue length in metres (people x 0.5 m).
- Flow arrows: instanced cones along route edges, spacing and animation speed proportional to flow (people/s), width proportional to cumulative load; hide below 5 % of max.
- Agents: instanced capsules or points (cap at ~2,000 drawn), positions from the event log with linear interpolation; stairs in sync with climbing.
- Timeline: scrubber with 0-T range, play/pause, speed 1x/4x/16x, markers for events (alarm, closure, first out, p50, p95, last); KPI strip above updates with the scrubber ("inside now", "out", "max density").
- Interaction: hover a room -> tooltip (name, area, occupants now, peak density, LOS letter); click a door -> side panel with load curve and queue; click a recommendation -> camera flies to the candidate wall and shows a ghost door; "Apply" runs the edit and shows the diff layer; keyboard: space = play, arrows = scrub, 1-5 = layers. `prefers-reduced-motion`: arrows static, no particle motion.
- Performance: one render loop, dirty flag, no per-frame allocation; picking by id colour or raycast on room meshes only.

### 2D plan

- Same ramp on room polygons (fill opacity 0.75 over the plan), walls stay black 1 px; label only rooms above 40 % of peak density plus the top 5 bottlenecks to avoid clutter.
- Isochrone contours at 30 s, 60 s, 120 s, 180 s (labels on the line, direct labelling), flow arrows with width = load, bottleneck = triangle with queue count and the door name; before/after slider (swipe) and a diff layer.
- Legend always visible: scale name (Fruin LOS), thresholds in p/m2, "assumed occupants: ...", scenario parameters. Each marker has a text alternative in the side list (sorted by severity) for screen readers and keyboard.
- Time-series strip under the plan: people inside vs time for p50/p95 and the min-cost-flow lower bound as a dashed line.

## 6. Scenario catalogue

Occupant defaults when the dataset has none (propose as `Occupants.from_load_factors`, labelled estimate): people = floor(area / factor) with area from `geometry`. Factors in m2/person: office 13.9 (IBC business, confirmed) or 10 (ASR A6-style office, [memory]); open-plan/call centre 4.6; classroom 1.9; lecture hall: seats from assets else 1.4; lab 4.6 [memory]; corridor, stair, lift, outdoor: 0; assembly standing 0.46 [memory]. If seat assets exist, keep the existing seat count (it is better data). Show the source in the UI ("estimated from 13.9 m2/person").

| # | Scenario | Parameters | Mechanics | KPIs | Extra assumptions |
|---|---|---|---|---|---|
| 1 | Fire evacuation, one stair blocked | alarm delay 30-120 s, pre-movement 30-90 s (distribution), blocked element(s), time-to-untenable (ASET input) | closure at t0 or at t_block; lifts off | T first/p50/p95/last, max density + LOS, bottleneck list with queue, unreachable rooms, RSET vs ASET input | occupant defaults; speed 1.34 m/s (Weidmann); stair factor 0.7 (repo assumption, unverified) |
| 2 | Lift out of service | lift id, step-free occupants share (default 2 %) | removes lift edges; step-free reach | step-free rooms lost, extra metres per route, who has no step-free route | share of mobility-impaired is an assumption |
| 3 | Morning arrival peak | arrivals ramp over 30 min at entrances, destination = room by type | inbound flow, doors as servers | door queue per entrance, time to desk p95, stair load | arrival distribution |
| 4 | Lecture-hall change-over | 2 halls empty and refill in 10 min, adjacent corridors | counterflow on shared corridor (graph model cannot capture counterflow slow-down: flag it) | corridor LOS, time to clear, queue at doors | break length |
| 5 | Step-free evacuation | step-free-only edges, refuge-area rule (wait at stair-adjacent refuge) | uses step-free graph, exits only on level | step-free rooms with no exit, time p95 vs normal | % users, refuge areas not in data |
| 6 | Shelter in place (bomb threat) | which zone to avoid, safe rooms by wall count / door | direction away from threat; no outside | rooms with no route away, time to reach nearest interior room | threat location |
| 7 | Power cut | lifts off, electric doors fail (state?), 20 % slower speed in unlit stairs | speed multipliers | time p95 delta, stair LOS | speed reduction is a guess; no source |
| 8 | Event crowd (e.g. 80 % hall capacity) | hall occupancy from standing factor, pre-movement 10-30 s | high density at the hall doors | max density, door queue, ASR/VStaettV width check (1.20 m per 200) | uses VStaettV rule |
| 9 | Door closed for maintenance (stress test) | any door set | single-element closure over all doors | ranking of doors by delta p95 (extends `chaos_test`) | none |
| 10 | Recommendation run | budget k, candidate set | section 4 | before/after KPIs per door | none |

Always report: egress time p50/p95/last, per-exit counts, max density by room with LOS letter, bottleneck list (door, width, flow, queue length, time queue exists), unreachable rooms (under closures), "code flags" (any room with route > 35 m, any door below ASR minimum for its catchment, dead-end > 20 ft/6.1 m is US-only, so mark it as such), routing efficiency T_sim/T*.

## 7. Recommended architecture

### Data model (typed, units in names, as in `evacuation/types.py`)

```
ScenarioSpec   id, kind, params{}, closures[], hazards[], timeline[events], occupants: OccupantSpec, speed_model, seed
Population     per room: n, speed distribution (mean 1.34, sd 0.26 [memory]), pre_movement distribution, mobility class
Result         kpis, per_person[(id, room0, t_out, exit, path)], per_door[(load, peak_queue, busy_time)],
               per_room[(peak_density, los, t_peak)], timeline frames (every 1 s: room counts), events, assumptions[]
Recommendation candidate, score parts, before/after Result, regress flag, reason
```

### Endpoints

`POST /api/scenarios/run` (spec -> Result summary + frames id), `GET /api/scenarios/{id}/frames?t0&t1` (binary/JSON frames for replay), `POST /api/scenarios/compare` (two ids -> diff layer), `POST /api/scenarios/recommend-doors` (spec + k), `GET /api/scenarios/catalogue` (defaults, assumptions). Stream long runs over the existing SSE channel; cache by hash of (building, edits, closures, spec).

### Reuse the RouteGraph so navigation and stress tests never disagree

The current `evacuation/adapter.py` builds its own capacity graph by design. Keep it as the min-cost-flow baseline, but have the new packet simulator take **edge lengths, step-free flags and closures from `RouteGraph`/`Constraints`** (same door-to-door spacewalk lengths, same stair/lift cost rules, same `closed`/`avoid` sets) and widths from `Building` openings. Add one test that for every room, the simulator's free-flow route length equals `plan_route(room, exit)` length from `core/routing.py` (zero tolerance), and that the min-cost-flow adapter's edge lengths equal the same graph's; this is the consistency invariant. Edits (session doors, closures) enter through one function that produces the edited `RouteGraph`; both engines consume it.

### Invariants to test (property tests)

1. Flow conservation: persons in = persons out + persons inside + stranded at every frame.
2. No person is faster than free flow: t_out >= path_length / v_person + pre_movement.
3. T_sim >= T* (min-cost flow lower bound) and, with unit capacities large, T_sim -> free-flow time.
4. Monotone in closures: closing an element never decreases p95 or reduces the unreachable set.
5. Adding a door never raises p95 **under optimal routing** (flow model); under shortest-path assignment a rise is allowed only with a regress flag; on a tree-like layout (no alternatives) the packet model must return an unchanged or lower p95 because the new door only gives an alternative the nearest-exit rule can ignore. The Braess evidence above is why test 5 is split in two.
6. Door doubling (IMO_09 analogue): 2 equal exits -> time about half of 1 exit when door-limited (tolerance 10 %).
7. IMO_04: 100 persons, 1 m door, mean flow 0.92 p/s (+/- 5 %), time ~109 s.
8. Determinism: same seed, same result; scaling occupant counts x2 never decreases p95.
9. Layout symmetry: mirrored building gives equal KPIs.

### Ranked build plan (2 days)

| Rank | Task | Why / size |
|---|---|---|
| 1 | Packet/queue simulator on `RouteGraph` with door servers (SFPE J), Weidmann edge speed, stair factor, pre-movement distribution; IMO_01/04/09 tests | Core engine; ~4 h |
| 2 | KPIs and the shared `Result` schema (p50/p95, per-door queue, per-room density + Fruin LOS, unreachable) + invariants 1-4 | ~3 h |
| 3 | Occupant defaults from load factors, scenarios 1, 2, 5, 9 as presets | Demo story; ~2 h |
| 4 | Door recommendation (pseudocode in section 4) reusing `evacuation/doors.py` verification; before/after | The "wow" feature; ~4 h |
| 5 | 2D plan heat map + legend + bottleneck markers + diff slider | ~3 h |
| 6 | 3D floor view layers (rooms recolour, door bars, bottleneck pins, timeline replay) | ~5 h |
| 7 | Code-flag checks (35 m, door widths vs catchment table, VStaettV 1.20 m/200) | ~2 h |
| 8 | Optional: JuPedSim zoom-in on one room for validation screenshots | only if time remains |

## 8. What I could not verify

- Primary NFPA 101 / NFPA 130 text: capacity factors, travel distance and the 6-minute point-of-safety rule only from secondary sources; NFPA 101 factors may differ from IBC's 0.3/0.2 in.
- IBC Table 1004.5 beyond business 150 gross sf (classroom, assembly, standing factors are from memory); the ICC PDF I opened was a training deck, not the code text.
- ASR A2.3 current (Nov 2024) wording: used a transcription (BGN) of an earlier version; 20 m toxic-hazard length and 0.15 m door narrowing from secondary sources. ASR does not define dead ends in the text I read.
- Swiss rules (VKF / SIA) and the exact MBO/MVStaettV model-law wording: only Bavarian state versions seen.
- ISO 16738 and ISO 23932 content; ISO 20414 test list (only catalogue summary).
- RiMEA full test list (3.0/4.0) and acceptance criteria; Circ.1533 acceptance tolerances beyond Pathfinder's table.
- Weidmann closed-form formula (parameters seen, formula from memory), Predtechenskii-Milinskii exit-flow formula, Fruin stair/queue tables as original (I used FHWA's HCM-based reproduction).
- RVO2 licence and Python status, buildingEXODUS, MassMotion, CrowdSim, SUMO licence.
- JuPedSim release date and commit recency (version 1.4.2 read; dates not retrieved).
- All colour hex values: the LOS ramp is my own design and has not been run through a CVD simulator; viridis and Okabe-Ito hex values are from memory.
- Default walking-speed standard deviation, power-cut slowdown and stair factor 0.7: no source.
