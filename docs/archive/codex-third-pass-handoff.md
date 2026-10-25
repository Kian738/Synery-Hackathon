# Codex third-pass integration notes

The user confirmed Claude owns the in-progress graph/routing work and asked Codex to leave it alone. Codex's patch concerns `core/scene.py`, phone transport/UI, scene rendering, camera presentation, chat links and their tests/docs. Do not attribute the current graph or benchmark changes to this UI patch.

`tests/test_scene_and_contracts.py` was adapted locally for the expanded differential evaluator: explicitly require two complete-graph rows, twelve route rows and all rows correct. This small test adaptation belongs with Claude's pending evaluator/core changes and is intentionally excluded from Codex's UI commit.

The current shared-core check passed 110 unit tests plus its offline gates. Its basic e2e result is 2122/2130, versus the previous committed 2124/2130; the core owner must account for this difference. The UI-only validation against the previous committed core exposed an existing mismatch with the current official implementation; therefore final integration validation uses an isolated copy of the current shared core rather than claiming the old core matches the updated reference. It passed 118 unit tests and all configured gates. No production graph/routing files are staged by Codex.

The displayed route is now a flat strip with round joins; camera heading is damped/rate-limited. The underlying validated polyline is unchanged by this patch. Remaining walking-line zigzags still need the walking-layer audit after the core work is ready: obstacle-aware simplification, exact doorway crossings, then clearance-validated rounding where feasible. Do not use unconstrained curves or hide collisions to make a screenshot smoother.

All 280 supplied buildings' slabs compile, producing 85,264 triangles in 20.475 seconds on this machine. Every triangulated slab's area matches its unioned footprint within 1e-5 square metres. This is a compilation/area check, not a rendering FPS or physical-building accuracy claim.
