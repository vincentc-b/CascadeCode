---
id: task_008
title: Add focused integration coverage for open reviews
tier: task
status: completed
parent: feat_003
children: []
depends_on:
- task_007
owners:
- swe
skills: []
parent_rev: 754b7b672af254cf0aa8f762edbe271814d0f65e
created: '2026-10-21'
updated: '2026-10-21'
---
# Add focused integration coverage for open reviews

## Parent Feature

[feat_003](../../features/2_active/feat_003.md)

## Depends on

- task_007

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Verify the open-reviews API contract against the durable registry with high-signal integration tests.

## Scope
- Seed representative open, merged, and closed review records using existing test support.
- Assert that open reviews are returned and merged/closed reviews are excluded.
- Assert stable identifiers, direct URLs, state, and feature/epic context in the response.
- Verify the read operation does not mutate registry state.

## Acceptance criteria
- Focused integration tests exercise the API end to end through the registry read path.
- Tests cover inclusion, exclusion, response fields, and side-effect freedom.
- No redundant mock-heavy unit coverage is added.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
