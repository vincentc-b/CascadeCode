---
id: task_048_001_003
title: Gate review publication and prove bounded recovery
tier: task
status: completed
parent: feat_048_001
children: []
depends_on:
- task_048_001_002
owners:
- swe
skills: []
parent_rev: 5b170561e4fe97bf8457932c5b4e8da8c96ab75f
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Gate review publication and prove bounded recovery

## Parent Feature

[feat_048_001](../../features/2_active/feat_048_001.md)

## Depends on

- task_048_001_002

## Acceptance criteria

- Change admit_review_publication_generation so material change is necessary but never sufficient; remove automatic attempt_bound growth and require incident-wide cumulative admission. Unknown classification fails conservatively. Deterministic unchanged failure can spawn one expensive check only. Transient default is at most three total attempts for one operation with persisted bounded backoff/jitter. Budget policy/version is part of admission; clock/report changes cannot mint a generation.
- Carry canonical incident, top-level claim and unique validator operation identities through team_review_recovery.py, review_rebase.py and review_validation.py. Atomically reserve worst-case approved profile runtime before spawn and settle on success, failure, timeout and interruption. Stop the entire local process group on timeout; retain bounded diagnostics. Do not reduce validation coverage to fit an exhausted budget. Recheck tested source SHA, target/policy/environment and remote lease before push; reconcile remote completion after interruption.
- Keep old attempts and generation-scoped resolved decisions. Exhaustion leaves delivery unresolved with one durable escalation; authenticated independent bounded correction/extension permits only remaining finite work. Preserve full Task validation and separate Epic product acceptance.
- Extend tests/test_review_recovery_journey.py or the closest production regression with a real temporary product/tracking repository, bare remote, real validator process and production tool adapters. Prove timeout once, restart and repeated request suppression, approved policy correction or extension, exactly one useful later publication, old resolved decision retained and independent remote SHA verification. Count actual process spawns and pushes, not only status. Use scripted external forge/provider transport only; no fake successful repair/check/push/postcheck or private lifecycle rewrites.
- Exercise the actual provider → MCP → validator entry path in the F1/F2 seam with scripted external provider transport permitted: the MCP request must carry the canonical incident, claim and operation receipt to the real budget gate and spawn the real validator only on an admitted permit. Assert refusal causes zero validator spawns and no publication, while the authorized later call yields one charged operation and one verified remote update. Record that F2 still owns provider paid-turn charging and broad launch coverage.
- Architecture impact: check cascade-landscape/context and cascade-containers for stable boundaries; reconcile cascade-supervisor-components and cascade-team-components admission→validator→publication→postcheck edges, cascade-task-code budget/generation link, cascade-watchdog-code consumer, and cascade-teams-code real publish/check/validator source declarations. Update cascade/DESIGN.md, cascade/task/DESIGN.md and cascade/watchdog/DESIGN.md as current facts; include normal, timeout, crash/restart, escalation and extension flows, persistent state, authority and process-isolation limits. Update model.dsl/views.dsl/workspace.contract.json together, preserve accepted snapshots; verify source contract, supported local render and representative context→container→component→Code, Level up, deep link and pinned-source browser path. Record exact checks and gaps in Task closeout.
- Reconcile the final diff with every view row in the feature diagram-impact inventory. F2 owns paid provider-turn enforcement; this Task must expose a usable budget API but cannot claim provider spending is bounded here. No live deployment or unrelated refactor.

## Files likely touched

`cascade/task/action_recovery.py`, `cascade/team_review_recovery.py`, `cascade/review_rebase.py`, `cascade/review_validation.py`, `tests/test_review_recovery_journey.py`, owning designs and the pinned architecture model/views/contract.

## Implementation notes

Use the Task-owned budget API from the preceding tasks. Keep existing exact-SHA publication and local process-group cleanup, reconciling implementation with the feature plan.

## Skills

_(none)_

## Test plan

Run the real-process/bare-remote journey in the acceptance criteria and focused review-recovery and architecture contract/navigation checks. Assert independent spawn/push/remote evidence and retained history.

## Out of scope

F2 provider paid-turn enforcement, Epic product acceptance, live deployment and unrelated action refactors.
