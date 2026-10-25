# Research

These are the sourced notes behind Floorwise's design decisions. Each note marks which sources were actually opened and which were only seen in search results. Check a claim against its source before you repeat it in the UI or to judges.

## Summary report

- [Indoor wayfinding agent UX](../../reports/Indoor%20wayfinding%20agent%20UX.md) (in `reports/`; the path is referenced from `floorwise/core/instructions.py`). Covers the deterministic-graph and grounded-talk architecture, the resolver and ask-back gate, route instructions, the evaluation protocol, and AR and positioning options. The notes below are its detailed sources.

## Wayfinding agent UX (detailed notes)

| Note | Topic |
|---|---|
| [wayfinding-ux/wayfinding_ux.md](wayfinding-ux/wayfinding_ux.md) | Map-first versus step-first, signage, voice and accessibility in indoor wayfinding products and studies |
| [wayfinding-ux/route_instructions.md](wayfinding-ux/route_instructions.md) | Landmark salience, chunking, floor changes in route instructions |
| [wayfinding-ux/conversational_ux.md](wayfinding-ux/conversational_ux.md) | When to ask back and when to act, showing what was understood |
| [wayfinding-ux/evals_and_dashboards.md](wayfinding-ux/evals_and_dashboards.md) | LLM-as-judge reliability, eval harness and dashboard design |
| [wayfinding-ux/floorplan_vectorization.md](wayfinding-ux/floorplan_vectorization.md) | Learned and classical floor-plan vectorisation (RoomFormer, Raster2Seq and others) |
| [wayfinding-ux/ar_localization.md](wayfinding-ux/ar_localization.md) | WebXR AR support by platform, phone localisation options |

## Phone, AR, VR and positioning

- [phone-xr-positioning.md](phone-xr-positioning.md): what can ship in a browser now versus what needs hardware, anchors or a native app.

## Evacuation and scenarios

| Note | Topic |
|---|---|
| [egress-and-stress-tests.md](egress-and-stress-tests.md) | Standards and numbers (German and US codes), crowd models, door-placement algorithms, visualisation and the build plan that led to `floorwise/stress` |
| [scenario-simulation/README.md](scenario-simulation/README.md) | Flow formulations, a demo and API proposal, validation baselines and limits, landmark and multisensory guidance, sources. This research came before `floorwise/evacuation` and `floorwise/reason` |

What none of this research claims: that the evacuation modules predict real evacuation times, model fire or smoke, or check code compliance.
