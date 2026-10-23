---
id: task_015_001_003
title: Gate plan approval and expose authoritative readiness
tier: task
status: completed
parent: feat_015_001
children: []
depends_on:
- task_015_001_002
owners:
- swe
skills: []
parent_rev: 827bbdb8fe96ddd3dba983f72a724630fad3a27f
created: '2026-10-23'
updated: '2026-10-23'
---
# Gate plan approval and expose authoritative readiness

## Parent Feature

[feat_015_001](../../features/2_active/feat_015_001.md)

## Depends on

- task_015_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Use one authoritative readiness predicate for epic planning status, approval enforcement, and the existing read model.

## Scope

- Compute `planning` versus `ready_for_review` from the current canonical revision, both valid role sign-offs, and zero canonical unresolved questions.
- Enforce that same predicate inside the plan-approval command so direct and stale-client attempts cannot bypass it.
- Extend the existing read model with readiness/status, valid role sign-offs, whether approval is currently allowed, and a stable disabled reason.
- Treat sign-offs on older revisions as insufficient without destructive cleanup.
- Preserve already-approved epics.

## Acceptance criteria

- Activation and a single sign-off cannot be approved.
- Both current-revision role sign-offs with no unresolved questions enable approval.
- A material plan revision returns an unapproved epic to non-ready until both roles sign the new revision.
- Direct approval attempts fail through existing domain error conventions when the predicate is false.
- Read-model fields agree with command behavior for every state.

## Verification

Exercise a compact domain/API transition table; avoid redundant selector-only tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
