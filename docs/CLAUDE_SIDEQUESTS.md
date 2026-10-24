# Claude Code side quests — shared-checkout handoff

Base branch: `codex/verified-building-demo`. Starting checkpoint: `e9250fc`.
Codex owns the navigator redesign, camera/player, picking/panning, labels, route rendering/depth, CIT walking failure, guidance and integration. Do not edit those files.

Paste this whole assignment into Claude Code. Recommended coordinator: Opus 5.5, xhigh effort. Sonnet 5.5, high effort is suitable for the bounded asset implementation. No production model calls are needed for these tasks.

## Shared-checkout contract

Read AGENTS.md, DESIGN.md, docs/UX_PLAN.md and docs/STATUS.md first. Confirm the current branch and inspect changes. Codex is editing concurrently. Stay on this branch. Do not switch branches, stage, commit, push, stash, reset or clean. Codex coordinates commits and integration so a shared Git index cannot capture somebody else's unfinished work. Do not undo unrelated changes. Work only in the owned paths below. Source data under docs/industrial-agents-hackathon-2026 is read-only and gitignored; do not copy it into tracked files. Never expose .env, use live LLM calls, change benchmark semantics, lower gates, or hard-code building IDs/names/questions in floorwise production code. Tests may use train/dev fixtures; do not hand-label test questions.

If parallel subagents are available, A and C can run independently; B owns different files. Otherwise do A, B, C, then D. Write a READY handoff for each completed package, listing files, exported interface, checks, screenshots/findings and limitations. Codex will read those files and integrate them. Before the final handoff, run uv run fw check; report unrelated concurrent failures accurately and never edit another owner's files to hide them.

## A — Complete, recognizable asset visuals

Own only:
- web/src/scene-assets/**
- web/tests/asset-catalog.spec.ts
- docs/parallel/assets-handoff.md

Read the current FurnitureBatch in web/src/components/Building3D.tsx but DO NOT edit it. Inventory asset type/category fields across all supplied building JSON files. The current inventory has 96 types and four categories: furniture, equipment, fixture, machine. Do not confuse category with type.

Build a deterministic lightweight procedural visual catalogue covering every supplied type. Prioritize recognizable silhouettes for oscilloscopes, microscopes, lab benches/fume hoods, printers/3D printers, projectors/screens, safety equipment, machine tools, chairs/tables, sanitary fixtures, shelves/racks, beds/sofas and plants. Avoid representing almost everything as a single box. Reuse geometry parts and keep an overview LOD economical. Preserve source footprint, position and rotation. No textures, network assets, generated images, or new dependencies unless essential and justified in the handoff. Unknown future types must have a visibly generic fallback, never a fabricated identity.

Export getAssetVisual(asset, lod) from web/src/scene-assets/catalog.ts. Import Asset from ../lib/types. lod is 'overview' | 'interior'. Return {family: string, illustrative: true, fallback: boolean, parts: AssetPart[]}.
AssetPart: {shape: 'box' | 'cylinder' | 'sphere', position: [number,number,number], scale: [number,number,number], color: string, rotation?: [number,number,number]}.
Coordinate convention: local X/Z offsets and scale fractions are normalized to the supplied width/depth; Y offsets/heights are illustrative metres. Origin is footprint centre at the floor; forward is local -Z. Ground-contact geometry stays within the footprint; any exceptional overhang must be documented. Rotations are radians. The integrator handles source footprint rotation and world coordinates.

Test catalogue coverage against the actual supplied inventory, finite transforms, nonnegative dimensions, deterministic output, unknown fallback, tiny/missing footprints and bounded LOD part counts. Do not add broad snapshot tests that merely mirror source code. A compact contact-sheet preview is useful, but keep it inside owned paths. Mark READY when the catalogue can be consumed by an instanced renderer without editing Building3D.

## B — Diagnose benchmark failures without changing settled semantics

Own only:
- floorwise/core/resolve.py
- floorwise/agent/spec.py
- floorwise/agent/answer.py
- tests/test_resolution_regressions.py
- docs/parallel/benchmark-handoff.md

Read eval gates, recent runs and the current baseline. Reproduce reported failures, separating exact routing/geometry/parser failures from the eight previously known ambiguous-name e2e misses. Inspect whether the language actually identifies the hidden room ID when names repeat. Do not make ambiguous questions appear solved by learning gold labels, guessing building-specific conventions, or lowering tolerances. Report genuine information insufficiency.

Only implement generic, evidence-supported entity-resolution or ambiguity-handling fixes in your owned production files. Codex owns core/walk.py, core/routing.py, graph.py, scene.py and geometry rendering; do not change them. Re-run affected train/dev suites plus fw check. Report before/after counts and explain every changed result. If nothing is legitimately fixable, provide a clear diagnostic handoff instead of manufacturing a green result.

## C — Paired phone companion prototype

Own only:
- web/src/companion/**
- server/companion.py
- tests/test_companion.py
- web/tests/companion.spec.ts
- docs/parallel/phone-handoff.md

The user selected phone + laptop on the same network. Build isolated components/router exports; DO NOT mount them into Navigator, app.py or the main React router. Codex integrates those entry points. No new dependencies unless unavoidable.

Goal: laptop shows the building; phone is an intentional companion/controller with a big current instruction, next/repeat/back, recenter and optional gyro look. Motion controls camera heading only, never indoor position or automatically-confirmed progress. Sensor use needs an explicit user action and permission; HTTPS/secure-context requirements must be researched and respected. No insecure browser flags or silent permission requests. Include a first-class drag/touch fallback when sensors, permissions or iOS APIs are unavailable. Haptics can be optional capability-detected feedback; do not make them the only cue.

Propose a compact versioned event contract before coding: pairing, route/instruction state from laptop, heading delta, next/back/repeat, recenter, disconnect. Keep pairing session-scoped, explicitly confirmed, short-lived and revocable; do not let a guessed building/session ID control another user's laptop. Avoid putting secrets in server logs. Reject stale sequence numbers, malformed messages and excessive sensor rates; disconnect must leave desktop navigation usable. Do not publish a tunnel or external service. Document how the phone can reach the server and that LAN HTTP alone may not expose sensors.

Export a FastAPI router factory and an embeddable React companion screen/controller with documented props. Add meaningful protocol tests and permission-denied/reconnect/device-rotation tests. A functioning touch-only paired demo is more important than pretending universal phone VR support. Mark READY with integration instructions and exact browser limitations.

## D — Multihop scenario simulation research, not production fire guidance

Own only:
- research_notes/scenario-simulation/**
- docs/parallel/scenario-handoff.md

Research an idealized, explicitly parameterized building stress-test scenario: occupant groups, unavailable/hazardous spaces, door/exit capacities, evacuation allocation, responder entries/targets, competing flows and proposed door interventions. Distinguish max flow, min-cost flow, time-expanded flow and genuinely multi-commodity optimization. Explain why independently routing everyone to their nearest exit is insufficient and why two independent shortest paths do not optimize competing flows.

Use primary sources (NIST evacuation-model verification/validation, official standards/wayfinding guidance, original research/algorithm documentation). Cite exact supporting URLs and publication dates. Do not claim a validated fire/smoke simulator, real evacuation times, code compliance, trained-responder instructions or a publishable contribution merely because an LLM chains tools.

Capacity units are pending user clarification: 20 people/minute, per simulation step, or total throughput are different problems. Keep units explicit and mandatory in any proposed input; do not assume missing occupancy, capacities, speed or hazard progression. Separate supplied facts, user scenario assumptions, computed results and unsupported effects. No production solver/API/UI code in this package yet.

Deliver: (1) a smallest worthwhile hackathon demo, (2) deterministic API/result/evidence proposal compatible with existing Session visual results, (3) optimization objective and conflict policy, (4) infeasible/unknown-data behavior, (5) meaningful validation cases and baseline comparisons, (6) research novelty and limitations, (7) a scoped follow-on implementation. Include landmark-based multisensory guidance research: concise spoken landmarks, optional repeat/recognition cues and evidence about recall, while avoiding invented landmarks, distracting stories or relying on colour/audio alone. Mark READY when the research is actionable.
