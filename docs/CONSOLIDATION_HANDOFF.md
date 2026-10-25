# Shared-checkout consolidation handoff

Claude is authorized to keep editing the shared source checkout. The other Codex chat works only in runs/reconstruction-finalization and must not copy changes into the source checkout or change Git refs during this integration. Final one-branch cleanup waits until the ongoing work is handed off.

## Preserve and merge

- Existing active branch: codex/verified-building-demo. Do not create another branch or reset the working tree.
- The reviewed default-branch merge was committed and pushed as 81e2876. Its reviewed source was exported to runs/reviewed-consolidation-snapshot and passed the full frozen validation. The merge state is complete. Do not stage another agent's unfinished work indiscriminately; the remaining working-tree changes are separate from that tested checkpoint.
- The original full working tree is saved in stash 1e8d118b6ec59dadd80e08d0d0d5edae64340781. Pre-consolidation history has a local bundle in runs/consolidation and remote archive/2026-10-25/* tags. Keep these until the final handoff is complete.
- Preserve current unstaged Claude edits: agent/session.py, agent/tools.py, agent/chat.py, core/spacewalk.py, server/app.py, tests/test_edit_capabilities.py and eval/edits.py. Their changing version has not passed the frozen release gate. Root runs_gates.log is a diagnostic log, not source to commit.
- Merge source changes, not generated caches, dependency directories or unrelated snapshot files. Integrate the newer default-branch scenario diagnostics before moving the default branch to main. Never force-push or discard branch-only work; keep archived tips recoverable.

## Important reconciliation

Both Claude and the isolated Codex candidate address door-edit routing caches. Retain one consistent invalidation strategy, then test cold and warmed caches, unchanged original disk cache, a second session, add/remove/undo, and routing through the actual added opening. Do not combine two partial cache implementations blindly. Check duplicate item names, multiple doors joining the same rooms and generated asset-ID collisions before exposing removal/undo as verified.

The source UI uses components/ScenarioPanel.tsx with explicit occupancy and passage-rate assumptions. The older navigator/ScenarioPanel.tsx and its quick-fire browser tests were intentionally excluded; they silently infer occupancy and do not match the current UI. Multi-hop scenario API/tool contracts remain present. Keep bounded session locking and validate both explicit and template request schemas.

Retain fixed per-conversation advertised Claude schemas, the preserved-thinking wire header, one bounded invalid-signature recovery, real assistant start/delta/end streaming, complete comparison tables, and Claude-first normal chat. Do not restore dynamic schema mutation or regex product answers during conflict resolution.

## Verification

Run fw check on the final frozen source, build the frontend, and run the paid chat_regressions profile explicitly. A five-turn regression does not replace the thirty-conversation gate. Browser inspection is blocked by the saved localhost permission rule despite renewed user approval; do not use another browser path to bypass it. Physical phone acceptance, unfamiliar teammate trials and full live/demo rehearsals remain separate requirements.

The earlier changing-source check passed 440 unit tests and numerical routes/solver/parser gates, but correctly failed source compatibility during rules. It must not be relabelled a passing release check. See STATUS.md and UX_AUDIT_50_AND_EXPLORATION.md for current evidence and scope.

Further concurrent work also touches Building3D, Connectors3D, SceneAssets, playback, Navigator, styles, focus helpers and lighting. These changing files are not part of the reviewed checkpoint. Re-review them rather than applying the whole tree: camera offsets must not move off collision-validated paths, missing walls must not be hidden to make a bad route look clear, and stairs/lifts must not acquire fabricated intermediate coordinates. Preserve the rejected prototype backups under runs/gemini-review for comparison.

For an isolated candidate, compute its diff against the snapshot it started from. Apply only that candidate diff to the latest integrated source; copying its older entire UI or provider files would erase the streaming and result-flow repairs. Validate conflicts with the final combined source, not each candidate in isolation.
