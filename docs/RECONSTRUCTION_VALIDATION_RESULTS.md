# Reconstruction and independent validation — 25 October 2026

This release is not ready for a claim of perfect reconstruction or full marks. `122/122` is our internal floor cohort, not an organizer requirement. Reconstruction and unfamiliar offline wording still fail strict gates. No threshold was reduced, required case omitted, or abstention counted as automatic reconstruction.

## Valid fixed-source reconstruction measurements

All runs below have `source_changed: false`, no infrastructure-error rows, all 40 required buildings and all 122 required floors. Raw records and failed-case overlays are under `runs/reconstruction-release-snapshot/runs/`.

| Assessment | Pass / assessed | Evidence directory |
|---|---:|---|
| Assisted floor diagnostic | 70 / 122 | `20261025-014111_build_assisted_1e0d8cad` |
| Actual import floor geometry/topology | 64 / 122 | `20261025-014113_build_pipeline_floor_18f250b6` |
| Complete automatically accepted buildings | 0 / 40 | `20261025-014112_build_4e7052db` |

Both floor assessments pass all 45 supplied procedural floors. Real-plan failures remain: assisted OSM 7/19, ResPlan 5/10, Swiss 13/48; production-pipeline OSM 6/19, ResPlan 5/10, Swiss 8/48. The 22/122 historical diagnostic had different, flawed connectivity semantics and is not directly comparable. It remains unchanged in `runs/20261025-001226_build_cdd343c2`.

Assisted floor macro means: room recall 93.87%, precision 93.60%; door recall 85.08%, precision 90.82%; topology recall 84.56%, precision 91.88%; pairwise reachability agreement 84.12%. These include 167 missing and 188 invented regions; 529 missed and 221 invented doors; 195 wrong-adjacency detections; 65 merged regions; and 71 falsely connected source-floor room pairs. Complete-building connectivity has a different denominator and can mask a false floor connection through genuine vertical alternatives, which is why floor topology remains a separate gate.

Actual import also exposes registration/scale limitations hidden by assisted bounds: 1,083 missing and 1,104 invented room regions across the floor cohort, 1,525 missed and 1,217 invented openings. All remain recorded. An image-only draft cannot establish true doorway clearance, accessibility, labels or missing alignment information. Review requirements are explicit; strict complete-building automation therefore passes zero buildings. This is a release blocker, not a successful abstention score.

The duplicate-region bug was repaired, marker detection now scales with drawn features, and opening association uses opposing regions. Tests cover duplicate detections, doubled resolution, upper-floor topology, false bridges, one-to-one cores and missing scale. These repairs do not resolve every real-plan failure.

## Independent initial campaign, fresh geometry

Local corpus `fresh-initial-v3`: 200 new buildings, 10,000 distinct requests, 600 whole-building image cases / 1,197 floor rasters. Development, validation and holdout are disjoint by layout, rendering and wording family. Manifest receipts are in `docs/PRIVATE_CORPUS_RECEIPTS.json`.

| Run | Measured result | Evidence directory |
|---|---|---|
| Development + validation | 8,000/8,000 requests; 40/40 analytic check executions; 320/320 automatic image cases fail; 160/160 missing-scale clarification contracts pass | `20261025-013903_private_full_34be6dec` |
| Frozen offline holdout | 1,241/2,000 requests; solver 1,600/1,600; text 841/1,600; 80/80 automatic image cases fail; 40/40 missing-scale contracts pass; 40/40 analytic executions | `20261025-013907_private_holdout_965c111f` |
| Bounded live holdout language | 20/20 route requests; 42,805 actual model tokens | `20261025-013907_private_live_e1e180a7` |

The offline holdout language failures are genuine coverage gaps: deterministic fallback cannot parse much of the disjoint wording family. The bounded live parser resolves its 20 tested requests; it does not imply all 2,000 holdout requests pass live. Resolver and typed session-correction contracts are separate from language testing.

On the 320 development/validation image cases with a supplied scale, room and door precision and recall are all 100%. Complete geometry still fails because core types/links and accessibility are unavailable or unverified. Mean topology recall is 90.22%, pairwise reachability agreement 60.25%, and ordinary exit agreement 61.64%. There are no invented ordinary connected pairs in these cases, but unverified step-free defaults produce false accessibility, correctly failing the strict gate. None is counted as successful automatic reconstruction.

The holdout was opened only after the implementation was fixed. It remains tied to that snapshot; no repair was based on its failing wording. Later UI integration changes are tested separately. The source-wide lifecycle guard rejects reuse after any implementation change; old cohorts opened during mutable checkout runs were retired before the fixed-source regression campaign.

## Expanded and industrial campaigns

The expanded local corpus has 2,000 new buildings, 100,000 distinct requests, 6,000 image cases and 11,997 rasters. The additional industrial corpus has 200 new buildings, 10,000 requests, 600 image cases and 1,197 rasters, including forklift and terminal-bay constraints. These are new layouts, not copies of supplied kit buildings. Earlier duplicate-question v1 reseals are not additional independent populations.

The retired industrial cohort's complete fixed-source regression is 9,457/10,640 total checks: all 8,000 development/validation requests pass; 783 offline language requests fail in former holdout families; 400 automatic image cases fail; all 200 missing-scale contracts and all 40 analytic executions pass. Evidence: `20261025-014205_private_full_4ad8e692`. This is regression evidence, not a fresh holdout claim.

Expanded fixed-source results are appended after the complete run finishes. Incomplete or source-changing exploratory runs are retained as invalid release evidence, including the interrupted duplicate expanded run. A locally frozen holdout is accessible to its author and does not eliminate overfitting risk.

## Release evidence and remaining work

The snapshot source and component hashes are recorded locally. Code and protocol are versioned; generated datasets, seeds and expected answers remain gitignored. Raw failure rows and denominators are retained. A source snapshot is required because other work in the shared checkout changed files during earlier tests; the integrity gate correctly rejected those earlier runs.

The two-file submission package regenerated 145/145 unique public-test IDs with zero fallback answers. No submission question was hand-labelled. The organizer announcement supplies filenames but not a complete JSON schema; package validation follows the repository interface. Submission correctness on unseen jury inputs remains unknown.

Physical-phone testing, unfamiliar-user testing, an exported exactly 120-second video, repository publication and the Hack and More form remain outside this validation result. Internal scores do not establish full marks.
