# Independent validation and reconstruction protocol

The earlier 22/122 import result is historical, not a submission requirement or a reliable complete-building score. Its floor-only entrance check penalized upper floors without outdoor entrances. The original evidence remains in `runs/20261025-001226_build_cdd343c2`.

## What is evaluated

`uv run fw eval build --mode both --split dev --limit 40` produces three separate ledgers: `build_assisted` (true-bound diagnostic), `build_pipeline_floor` (actual import, floor geometry/topology), and `build` (complete reconstructed building, including vertical connections, exit reachability and review requirements). All 122 source floors remain in the denominator. Production import receives image pixels and one simulated caller measurement of the first image outline width. Source geometry is used afterward for scoring and origin translation only. Assisted calibration is explicitly labelled and never passed to production import.

Measurements include room and door precision/recall; missing and invented rooms/openings; merged and split regions; wrong adjacency; connection precision/recall; all-pairs reachability agreement; invented connected pairs; and complete-building ordinary/step-free exit agreement. An upper floor with no source outdoor entrance is not intrinsically a failure. Empty cohorts, missing required files, oracle crashes and changing fingerprints fail the run. Failures retain per-case JSON and source/reconstruction SVG overlays. Thresholds remain explicit; no abstention is an automatic reconstruction success.

The builder uses component-local morphology, resolution-scaled marker detection, opposing-region opening association, duplicate-region suppression and one-to-one core registration. It requires a real dimension and preserves uncertain labels/alignment as review requirements. Default opening widths, accessibility flags and floor elevations are disclosed as unverified inferred fields. They must be verified before use as an accurate accessible building model. The import UI requests the dimension and presents review requirements before opening a draft.

## Reproducible private campaigns

```powershell
uv run fw private generate --profile initial --root runs/private-corpora/my-initial
uv run fw private run --profile smoke --root runs/private-corpora/my-initial
uv run fw private run --profile full --root runs/private-corpora/my-initial
uv run fw private run --profile holdout --root runs/private-corpora/my-initial
uv run fw private live --split holdout --limit 20 --root runs/private-corpora/my-initial
uv run fw private retire --root runs/private-corpora/my-initial
uv run fw private generate --profile expanded --root runs/private-corpora/my-expanded
```

Initial: 200 new buildings, 10,000 distinct requests, 600 image cases. Expanded: 2,000 new buildings, 100,000 distinct requests, 6,000 image cases. Each image case exercises every floor of a whole building; raw raster counts are larger. The optional `industrial` profile adds 200 buildings with forklift clearance and terminal-bay constraints. `smoke` generation creates a small exploratory corpus; smoke evaluation selects eight development buildings. Full evaluation covers development/validation; holdout is a separate invocation. Retired holdouts join regression coverage on subsequent full runs.

Generators construct new polygons/topology; no kit building is copied. Concave wings, multiple cores, disconnected sections, basements, narrow openings, duplicate names, closures, ordered tours and accessibility constraints are represented. Styles vary resolution, padding, text, walls, compression and colour. Missing scale is an explicit clarification contract. Geometry alone cannot establish real accessibility or labels; those cases remain reviewable, and the automatic reconstruction numerator remains zero when review is required.

Family partition is development: spine/courtyard links/offset wings/dual core/split block/concave branch; validation: staggered branches/alternating necks; holdout: comb links/detached annex. Rendering and wording families are also disjoint. Solver/text requests, entity ambiguity contracts and typed multi-turn correction contracts are labelled separately. Typed session contracts are not live conversational tests. Live evaluation is capped at 20 requests and 400,000 tokens per process, with actual model-token use reported. A successful deterministic dispatch does not prove LLM coverage.

Expected answers come from elementary polygon moments/counts or an independent kit graph, never Floorwise's solver. Forty analytic check executions include 20 basic rectangle instances and 20 more diverse walking, vertical, outside-hop, clearance, terminal-bay and concave-moment checks; these are not 40 unrelated families or a human-user study. Unit tests ensure oracle infrastructure crashes cannot become fabricated no-route gold.

Private data stays under ignored `runs/` or outside the repository. Code is versioned; local manifests contain seed, generation, exact counts, per-file SHA256 values and generator/oracle digest. Public manifest receipts omit seeds and expected answers. Layouts and wording are accessible to their author: this is a locally frozen holdout, not an independently secret examination.

Opening holdout freezes the implementation fingerprint. Changed implementations cannot reuse it for a new holdout claim: retire and generate a fresh corpus. Old raw evidence and checksums remain. Reissuing is permitted only before any holdout use and does not create novel geometry. Do not add copied v1/v2 populations together as independent buildings.

## Reading results

Every campaign writes raw records, summary, content fingerprints and `coverage.json`. Separate solver correctness, text correctness, rendering style, layout family, ordinary failures, infrastructure errors, review requirements and clarification contracts. Raw automatic image failures remain failures even when the review UI behaves correctly. Internal pass rates do not predict full marks.

The long exploratory runs were invalidated by concurrent checkout changes. Their raw measurements are retained and labelled historical. The release snapshot under `runs/reconstruction-release-snapshot` isolates source for repeatable checks; `SNAPSHOT.json` records file hashes. Read-only kit data and installed dependency junctions are shared, not copied training data. Final measured evidence is recorded in `docs/RECONSTRUCTION_VALIDATION_RESULTS.md`.
