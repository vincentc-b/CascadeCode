---
id: task_002
title: Gate central feature dispatch on approval, dependencies, and merge eligibility
tier: task
status: completed
parent: feat_001
children: []
depends_on:
- task_001
owners:
- swe
skills: []
parent_rev: 27e2c98dfbed1a2c01d4a4bedd9d1077b5cf81f0
created: '2026-10-21'
updated: '2026-10-21'
---
# Gate central feature dispatch on approval, dependencies, and merge eligibility

## Parent Feature

[feat_001](../../features/2_active/feat_001.md)

## Depends on

- task_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Extend the single existing implementation-dispatch decision so a feature becomes eligible only when all required gates pass.

## Scope
- Require the feature's durable approval state.
- Require every feature listed in `depends_on` to be completed.
- Retain the existing single-feature-awaiting-merge gate without creating a parallel dispatch path.
- Trigger/re-evaluate eligibility after relevant approval, dependency-completion, and merge-gate changes.
- Define missing or non-completed dependencies as blocking, consistent with existing board validation/error conventions.

## Acceptance
- Unapproved features never dispatch.
- Approved features with any incomplete dependency never dispatch.
- Eligible approved features dispatch when dependencies are complete and the merge gate permits.
- Existing merge serialization behavior remains intact.
- Dispatch remains idempotent under repeated eligibility evaluation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
