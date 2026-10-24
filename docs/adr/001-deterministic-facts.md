# ADR 001: deterministic facts, language-only model

Accepted 2026-10-24. Claude resolves intent and invokes typed tools. Geometry, aggregation, routes and interventions are computed by floorwise/core. Existing operators are exposed to chat instead of asking Claude to calculate from coordinates or truncated search results. Compound descriptions intersect deterministic room, floor and asset filters.

Verification: fw check; tests/test_scene_and_contracts.py; fw eval rehearse. A good benchmark score does not prove live interaction quality; live transcripts require review.
