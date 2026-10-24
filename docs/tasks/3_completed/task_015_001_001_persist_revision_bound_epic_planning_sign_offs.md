---
id: task_015_001_001
title: Persist revision-bound epic planning sign-offs
tier: task
status: completed
parent: feat_015_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 11782a30f0e0573759c5d947d960d2e4e9df8888
created: '2026-10-23'
updated: '2026-10-23'
---
# Persist revision-bound epic planning sign-offs

## Parent Feature

[feat_015_001](../../features/2_active/feat_015_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add the smallest persistence/domain representation for independent Epic Manager and Epic Architect sign-offs bound to the canonical plan revision.

## Scope

- Store at most one effective sign-off per required role and plan revision.
- Ensure active, unapproved epics begin with no valid sign-offs.
- Preserve the approved state of already-approved epics during migration or hydration.
- Expose repository/domain operations needed to read and idempotently record a role sign-off.

## Acceptance criteria

- Sign-offs identify both role and canonical plan revision.
- Repeating the same role/revision sign-off is a no-op.
- Sign-offs from an older revision are retained or ignored safely but are not valid for the current revision.
- Existing approved records remain approved.

## Verification

Use focused persistence/domain tests for migration compatibility, uniqueness/idempotency, and revision binding.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
