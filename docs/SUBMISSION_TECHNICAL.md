# Technical explanation for the submission form

Repository (configured Git origin): https://github.com/Kian738/Synery-Hackathon

Floorwise turns a building model into an indoor navigation assistant. A provider-neutral
language layer resolves a user's request into typed operations; deterministic Python
tools compute every distance, count, geometric relationship, route and closure impact.
Language models parse unfamiliar wording and explain results without supplying geometry.

The route graph follows kit 1.1.0: door-to-door walking with wall clearance, explicit
stair and lift costs, and no outside shortcut. Constraints include step-free access,
opening width, closures, avoided areas and supported industrial transport rules. React
shows resolved endpoints, constraints, one instruction per decision and linked floor
plans/3D views. User-declared position is distinct from simulated route playback.
An optional paired phone controls the camera and instructions. Plan-image import
produces a draft building for review using a real scale dimension.

The repository includes reproducible offline evaluation, route validity checks and
desktop/mobile browser regressions. `uv run fw submit` generates the two required
files in `SUBMISSION` and validates complete question-ID coverage. Current measured
results and remaining limitations are recorded in `docs/STATUS.md`; no public gold
labels exist for the test predictions. Live positioning and physical phone validation
are not claimed.

Form checklist: repository URL; edited video whose inspected duration is exactly
120 seconds; technical explanation above. Upload and final form submission remain
separate from generating local benchmark files.
