---
id: task_047_003_001
title: Route completed-parent Task delivery through Feature repair
tier: task
status: completed
parent: feat_047_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 96fc6dbfc8b711e2937452f6ef6d2078c500bc80
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route completed-parent Task delivery through Feature repair

## Parent Feature

[feat_047_003](../../features/2_active/feat_047_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the completed-parent delivery mismatch route. Preserve the original queued Task merge action, validation pair, prior refusal and all historical attempts. In task_rollup classify a completed Feature parent with not_active as parent_lifecycle_mismatch; keep busy/live-turn as expected wait. Before another merge attempt, compute a canonical evidence generation over exact owner/status, action/repair, tested heads, review obligation, approvals/comments/dependencies and lease; repeated unchanged sweeps observe only. Connect Feature direct-child recover_task/supervise_child to the existing feature_repair inspect/admit/resume operation with typed selected owner, operation, request/acknowledgement/execution/refusal fields. Enforce exact owner, parentage and gates; do not fabricate authority or launch duplicate turns. Add focused production-path tests and update Task/Feature/package design and code model for significant new symbols.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
