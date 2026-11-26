---
id: task_015_001_002
title: Implement role-authorized epic-plan sign-off command
tier: task
status: completed
parent: feat_015_001
children: []
depends_on:
- task_015_001_001
owners:
- swe
skills: []
parent_rev: 827bbdb8fe96ddd3dba983f72a724630fad3a27f
created: '2026-10-23'
updated: '2026-10-23'
---
# Implement role-authorized epic-plan sign-off command

## Parent Feature

[feat_015_001](../../features/2_active/feat_015_001.md)

## Depends on

- task_015_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement the sign-off command/use case for the current canonical epic plan revision.

## Scope

- Allow only the matching Epic Manager or Epic Architect role to record its own sign-off.
- Reject sign-off whenever canonical unresolved open questions exist.
- Bind successful sign-off to the current canonical plan revision.
- Make repeated same-role/same-revision requests idempotent.
- Use existing domain error conventions for authorization, unresolved-question, and stale-revision failures.

## Acceptance criteria

- Either role can sign only for itself.
- Neither role can sign while any canonical question is unresolved.
- Successful sign-off records the caller's role against the current revision.
- A repeated valid request does not duplicate state or fail.
- A stale client cannot sign a superseded revision.

## Verification

Cover the command transition matrix with high-signal domain/API tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
