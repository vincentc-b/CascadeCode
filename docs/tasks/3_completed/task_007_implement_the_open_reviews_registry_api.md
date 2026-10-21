---
id: task_007
title: Implement the open-reviews registry API
tier: task
status: completed
parent: feat_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 754b7b672af254cf0aa8f762edbe271814d0f65e
created: '2026-10-21'
updated: '2026-10-21'
---
# Implement the open-reviews registry API

## Parent Feature

[feat_003](../../features/2_active/feat_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Expose a read-only list API backed directly by the existing durable review registry.

## Scope
- Define the minimal response DTO using existing review records.
- Query and return only open reviews.
- Include stable review identifier, direct URL, review state, and feature/epic context.
- Preserve the registry as the sole source of truth; introduce no writes or new persistence.

## Acceptance criteria
- Open records are returned through the API.
- Merged and closed records are excluded.
- Every response record contains the required identifier, URL, state, and context.
- The read path is side-effect free.

## Out of scope
War Room UI/presentation and review mutation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
