# Documentation

Start with the [project README](../README.md). Coding agents and contributors: [AGENTS.md](../AGENTS.md) holds the rules and commands.

## Using and checking Floorwise

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Packages, data flow, the three meanings of distance, scenarios, scene compile, server and web app |
| [TESTING.md](TESTING.md) | Test commands, every eval suite and gate, independent oracles, the manual challenge pack |
| [STATUS.md](STATUS.md) | What works now and the evidence for it |
| [JUDGING.md](JUDGING.md) | Evidence map: capability, command, result, implementation |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Each requirement from the kit and Synera's messages, traced to code and tests |
| [DEMO.md](DEMO.md) | The two-minute pitch script, the fire demo, the fallback recording |
| [PHONE_DEMO.md](PHONE_DEMO.md) | Pairing a phone, HTTPS for motion sensors |
| [DEPLOY.md](DEPLOY.md) | Hosting the app for others |
| [../BENCHMARK.md](../BENCHMARK.md) | The benchmark command and answer format (copied into `SUBMISSION/`) |

## Plans and open work

| Document | What it covers |
|---|---|
| [TASKLIST.md](TASKLIST.md) | Short list: what is done, what is next, how each item is checked |
| [BACKLOG.md](BACKLOG.md) | Long list of open and unverified items, positioning and AR options |

## Decisions and design

| Document | What it covers |
|---|---|
| [adr/001-deterministic-facts.md](adr/001-deterministic-facts.md) | Facts from code, language from the model |
| [adr/002-three-routing-semantics.md](adr/002-three-routing-semantics.md) | Benchmark cost, walking line and exit-rooted impact kept apart |
| [adr/003-reconstruction-is-a-draft.md](adr/003-reconstruction-is-a-draft.md) | Image imports are drafts that a person reviews |
| [UX_PLAN.md](UX_PLAN.md) | Visual direction, tokens, layout, interaction protocol |
| [../DESIGN.md](../DESIGN.md) | Colour and type tokens for the 3D stage |
| [UI_RESEARCH.md](UI_RESEARCH.md) | Reviewed interaction research behind the guidance and camera choices |
| [CHAT_UX.md](CHAT_UX.md) | Chat and highlight choreography decisions |

## Reconstruction validation

| Document | What it covers |
|---|---|
| [PRIVATE_VALIDATION.md](PRIVATE_VALIDATION.md) | Protocol for the independent corpus and the frozen holdout |
| [RECONSTRUCTION_VALIDATION_RESULTS.md](RECONSTRUCTION_VALIDATION_RESULTS.md) | Measured import quality, including failures |

## Interface contracts

These files are referenced from source code and stay at these paths.

| Document | Contract |
|---|---|
| [parallel/phone-handoff.md](parallel/phone-handoff.md) | Phone companion protocol (`server/companion.py`, `web/src/companion/`) |
| [parallel/assets-handoff.md](parallel/assets-handoff.md) | Procedural scene-asset catalogue (`web/src/scene-assets/`) |
| [parallel/benchmark-handoff.md](parallel/benchmark-handoff.md) | Diagnosis of the ambiguous benchmark questions (`eval/known_issues.json`) |

## Research and history

- [research/](research/README.md): sourced research behind the decisions (wayfinding UX, route instructions, evaluation, plan vectorisation, AR and positioning, evacuation).
- [archive/](archive/README.md): old audits, handoffs and the dated status log. Kept for history and not maintained.
- `Hackathon Challenge - Talk to Your Building.pdf`: the challenge brief. The kit itself (data, starter agent, README) lives in `industrial-agents-hackathon-2026/`, which is gitignored.
