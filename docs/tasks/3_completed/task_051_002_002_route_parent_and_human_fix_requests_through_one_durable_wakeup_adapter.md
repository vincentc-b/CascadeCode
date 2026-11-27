---
id: task_051_002_002
title: Route parent and human fix requests through one durable wakeup adapter
tier: task
status: completed
parent: feat_051_002
children: []
depends_on:
- task_051_002_001
owners:
- swe
skills: []
parent_rev: f834c5c379eaa970b2d29e938d582ab00d8b5858
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route parent and human fix requests through one durable wakeup adapter

## Parent Feature

[feat_051_002](../../features/2_active/feat_051_002_admit_durable_scoped_repairs_for_open_feature_reviews.md)

## Depends on

- task_051_002_001

## Acceptance criteria

- A direct Epic parent request against an implementation-complete Feature with its original open red review calls the admitted review-repair adapter even when no Task lifecycle mismatch exists. An authenticated human mutation request uses the same adapter and exact action/generation contract; an unauthenticated or unrelated requester is refused.
- `supervise_child` and `recover_feature` return separate requested, admitted, acknowledged, executing/executed, waiting/refused and verification pending/verified fields, plus accountable owner, selected operation, action/generation and a typed next prerequisite. Queue acknowledgement cannot claim execution or verification.
- Admission is durable before enqueue. Faults after admission/before enqueue and enqueue/before checkpoint replay the same request and event. A live Feature graph joins or defers and does not start a competing writer or spend another provider turn. A legacy completed-open Feature reconciles through the supported repair route while retaining branch, review, checkpoint and worktree.
- Existing completed-parent Task mismatch and accepted/merged-review follow-up routes still select their current compatible paths. Scoped request authority and current owner/head/generation gates are rechecked before wakeup.
- Reconcile `cascade/epic/DESIGN.md`, `cascade/feature/DESIGN.md`, affected `cascade/workspace/DESIGN.md` and `cascade/DESIGN.md` with actual code. Update the `cascade-epic-code`, `cascade-feature-code` and affected `cascade-workspace-code` native nodes/relationships in model.dsl, views.dsl and workspace.contract.json together. Verify real source symbols/kinds, normal and restart flows, context → container → component → Code, Level up, deep link and pinned source.

## Files likely touched

`cascade/team_supervision.py`, `cascade/epic/recovery.py`, `cascade/feature/repair.py`, existing authenticated mutation adapter and `cascade/workspace/kickoff.py` if its queue contract changes; owning designs and architecture source closure.

## Implementation notes

Use the action identity and authority established by task_051_002_001. Expose a narrow callable for the later War Room UI without implementing that UI here. Keep queue cursor and checkpoint as existing wakeup stores.

## Skills

_(none)_

## Test plan

Extend `tests/epic/test_parent_lifecycle_recovery.py`, `tests/workspace/test_completed_recovery_kickoff.py` and focused Feature repair tests with real temporary Git and event/queue state. Inject both durable-boundary crashes and a concurrent owner; assert one action/event/turn and typed result. Run source-contract validation and a pinned local render/navigation check; record actual evidence and gaps.

## Out of scope

War Room UI, cross-forge CI normalization, a new scheduler or recovery ledger, and merged-review follow-up changes.
