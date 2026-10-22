---
id: task_007_001_002
title: Implement durable PR identity and stacked dispatch selection
tier: task
status: completed
parent: feat_007_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 1e3c960663ff045315cdec0a9f97f5a001bbece5
created: '2026-10-22'
updated: '2026-10-22'
---
# Implement durable PR identity and stacked dispatch selection

## Parent Feature

[feat_007_001](../../features/2_active/feat_007_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Enforce durable feature-to-PR identity at completion and implement deterministic, opt-in base selection for linear feature stacks.

## Scope
- Reject feature completion until a durable feature-to-pull-request link is populated.
- When the room setting is disabled, retain the current predecessor-merge gate.
- When enabled, evaluate direct predecessors only:
  - zero predecessors or a merged predecessor uses the epic's normal integration/base branch;
  - exactly one complete, unmerged predecessor with resolvable durable PR/head-branch identity is eligible and supplies that head branch;
  - incomplete/non-complete predecessors remain blocking;
  - more than one direct predecessor fails closed as unsupported topology;
  - missing PR or branch identity fails closed with a visible diagnostic.
- Persist the selected predecessor and base in durable feature/dispatch state before side effects so retries and restarts are deterministic.
- Preserve idempotent dispatch/PR creation and existing first-feature behavior.

## Acceptance
Focused lifecycle/dispatcher/PR-adapter integration tests cover disabled and enabled paths, first feature, merged fallback, A→B→C direct-predecessor selection, fan-in, missing identity, blocked predecessor states, completion invariant, and retry idempotency.

## Constraints
Do not implement explicit provider-side retargeting or arbitrary stack reordering. Prefer extending existing durable state and dispatcher seams.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
