# UX and submission release audit — 25 October 2026

The [UX inspection](UX_COGNITIVE_LOAD_AUDIT.md) was written before edits from the
running app, source and existing regressions, using the requested cognitive-load
article and the repository's UX plan. This pass reduces simultaneous toolbar choices,
discloses the assumed/manual/linked start, improves room search, groups examples and
keeps destination shortcuts visible on a 390 × 844 first-use screen.

`fw submit` now generates `SUBMISSION/BENCHMARK.md` and `SUBMISSION/answers.json`,
with no other files in that folder. The JSON contains 145 unique predictions covering
the public test questions, with zero unresolved answers or model fallbacks. The
legacy CSV is written from those same predictions. Nine packaging regressions reject
missing/duplicate IDs, contradictory routes/replies and unresolved answers, and protect
unexpected user files from deletion. The announcement gives filenames but no JSON
schema; the format is documented in BENCHMARK.md.

## Measured evidence

| Check | Result | Evidence in runs/ |
|---|---|---|
| Generated routes, all 280 train/dev/test buildings, 12 questions per building where available | 3,039/3,039 | ux-generated-all.log; 20261025-000655_generated_eafa10c9 |
| Kit graph equality plus route/closure comparisons, all 280 buildings | 8,960/8,960 (560 complete graph comparisons and 8,400 route comparisons) | ux-differential-all.log; 20261025-000653_differential_4135ea2f |
| New question wording across all 280 buildings, 13 harvested sentence frames | 3,275/3,275 | ux-roundtrip-all.log; 20261025-000713_roundtrip_e99f7ee8 |
| Live Claude demo, three five-turn conversations, real browser/SSE/tools | 3/3 after repair | ux-live-demo-fixed.log; 20261025-001146_demo_0b9ae457 |
| Targeted API/history/packaging regressions | 18 passed | ux-fix-unit.log |
| Complete final unit suite | 373 passed | ux-final-unit.log |
| Final serial desktop/phone browser suite, including visible mobile shortcuts and pointer access to Tools | 136 passed, 28 intentionally skipped | ux-final-ui.log |
| Complete configured offline gate run (`fw check`) | passed; only explicitly diagnosed gold-text ambiguities remain | ux-final-check.log |
| Exact routes / solver / rule parser train+dev / rule parser test | 2,130/2,130; 655/655; 655/655; 145/145 | ux-final-check.log |
| Perturbed wording / geometry transformations / route rules | 630/630; 860/860; 661/661 | ux-final-check.log |
| Walking-preview contract | 133 validated walks; 1 safely withheld preview; 26 unreachable pairs (160/160 contract checks) | ux-final-check.log |
| Assisted image reconstruction, 40 dev buildings / 122 floors | 22/122 meet all strict per-floor checks; 93.8% mean room recall, 94.0% matched IoU, 81.7% door recall, 30.4% exit-connected share | ux-build-eval.log; 20261025-001226_build_cdd343c2 |

Each structured run records its source/data/frontend/model fingerprints. The shared
checkout also received concurrent scenario-engine work during this audit. Evidence
marked `source_changed` is a measured snapshot, not proof of the final mixed revision.
The final serial browser run passes, and the post-fix configured offline gate run
completed successfully. Separate final unit validation includes all 373 tests present
at collection time. Import quality is reported separately and is not a passing gate.

The final `fw doctor` check passes, including a current web build. Submission was
regenerated after the final UI changes: 145/145 IDs, zero fallbacks, 45,974-byte JSON,
and exactly two package files (`ux-submission-final.log`, `ux-doctor-final.log`).

## Failures found rather than hidden

- Initial live rehearsal: 0/3. Claude returned HTTP 400 after specialized tool loading:
  an earlier thinking signature was bound to the previous tool list. The provider
  adapter now uses the documented thinking-binding beta with
  `prefix_mismatch_behavior=drop_block`, preserving tool results and assistant history.
  A deferred-tool regression and the subsequent 3/3 live run cover the fix.
  [Provider documentation](https://platform.claude.com/docs/en/build-with-claude/thinking-troubleshooting).
- Initial full browser run: an asynchronous native details toggle reopened Tools
  after Escape. A single state-controlled summary click now handles pointer/keyboard
  activation; Escape closes it and returns focus.
- The companion test's nested dependency synchronization attempted to reinstall the
  running Windows fw.exe. Its child now uses the already-synchronized project runtime
  (`uv run --no-sync`); websockets is an existing declared project dependency.
- The first mobile screenshot revealed that destination labels were below the
  composer. First use now has a smaller 3D stage and compact labelled shortcuts;
  guidance retains its existing layout. A bounding-box assertion checks discoverability.
- Concurrent Scenarios work added a mode button that overlapped Map/Tools at phone
  width. Scenarios now belongs to the secondary Tools group. The serial browser
  rerun verifies actual pointer access, not just keyboard/programmatic activation.
- Reconstruction evaluation previously returned exit code zero even when most floors
  failed its checks. It now returns nonzero for failed or empty evaluations; a regression
  verifies a finished-but-poor import cannot appear as a successful full-profile phase.

## Remaining score and submission risks

- The test predictions have no public gold answers. Coverage and graph equality do
  not establish a hidden-building score or guarantee full marks.
- Existing gold-text ambiguities remain raw failures: comprehensive e2e 653/655,
  basic e2e 2,122/2,130, and Sunday route scoring 1,329/1,338. These are diagnosed
  repeated-name questions; the gate permits only individually documented misses.
- Image reconstruction is evaluated separately and is weaker on some supplied
  sources. Its benchmark uses supplied true outline bounds for assisted calibration;
  it does not measure autonomous scale recovery or validated physical buildings.
  Its exit-connected share is a floor-only diagnostic without reconstructed vertical
  connections, so 22/122 strict floor passes must not be presented as a predicted
  multi-floor grading score. The low door recall is independently a material limitation.
- The old three-minute demo plan was replaced with a 120-second product/architecture
  script in docs/DEMO.md. docs/SUBMISSION_TECHNICAL.md contains form-ready technical
  copy. The edited video, measured 120-second export, repository push and final Hack
  and More form submission are not performed by this audit.
- Physical phone/microphone/projector checks and uncoached human navigation remain
  unverified. Automated companion tests use separate browser contexts.
