---
id: task_026_002_002
title: Repair interrupted Task runs and missing integration checkouts
tier: task
status: completed
parent: feat_026_002
children: []
depends_on:
- task_026_002_001
owners:
- swe
skills: []
parent_rev: b2d72c4bb274540f1fa2d709cbdf84ccfcc8407d
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Repair interrupted Task runs and missing integration checkouts

## Parent Feature

[feat_026_002](../../features/2_active/feat_026_002.md)

## Depends on

- task_026_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement deterministic supervisor repairs for interrupted Task execution and missing integration checkouts.

## Scope

- Detect an interrupted Task run from persisted lifecycle state.
- Resume it without minting a replacement action or widening worker permissions.
- Detect a missing integration checkout and recreate it from authoritative persisted metadata.
- Make repair idempotent under repeated supervisor evaluation.

## Acceptance

- An interrupted Task resumes the same action and can proceed to completion.
- A missing integration checkout is restored with the expected repository/ref identity.
- Re-running repair after success is a no-op.
- Irrecoverable or semantic failures are surfaced for ownership routing rather than guessed at.

## Verification

Exercise both repair paths through the supervisor boundary, including a repeated invocation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
