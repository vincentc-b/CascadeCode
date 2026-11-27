---
id: task_026_001_001
title: Persist stable action identity, recovery state, and attempt history
tier: task
status: completed
parent: feat_026_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d33b686e923560c006a131f82be564d48dbe2e93
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Persist stable action identity, recovery state, and attempt history

## Parent Feature

[feat_026_001](../../features/2_active/feat_026_001.md)

## Depends on

None.

## Acceptance criteria

- Introduce a durable record for one logical lifecycle action with a stable action identifier and action kind.
- Persist the action's current recovery state, failure classification, attempt count, and configured attempt bound.
- Represent the feature classifications: deterministic repair, transient retry, owner decision, human gate, and terminal blocker.
- Persist append-only attempt entries containing attempt number, start metadata, outcome, classification, and completion metadata.
- Creating or loading by the same stable identity returns the same logical action and does not create a duplicate record.
- Persistence operations needed by the next task can atomically record an attempt start and atomically finalize its outcome plus resulting recovery state.
- Reloading the persistence layer through the repository's normal restart or reopen boundary preserves the action record and complete attempt history.
- Focused persistence tests cover stable-identity deduplication, append-only history, atomic state transitions, and reload durability.

## Files likely touched

Use the repository's existing lifecycle persistence boundary and its adjacent model/schema, migration, and persistence test files. Discover exact paths from repository conventions; do not introduce a parallel store or generic orchestration subsystem.

## Implementation notes

Implement only the durable data model and persistence contract required for one logical lifecycle action. Include stable action identity, current recovery state, bounded-attempt metadata, the five failure-classification values, and append-only attempt history.

Keep execution claiming, retry scheduling, and downstream-effect idempotency behavior out of this task; Task 002 owns those behaviors. It is acceptable to add the minimal persistence fields or atomic primitives Task 002 will consume, but do not implement its resume loop.

Follow existing repository naming, serialization, migration, and transaction conventions. Preserve backward compatibility for existing persisted state where the repository requires it.

## Skills

_(none)_

## Test plan

Add or extend the smallest set of persistence-level integration tests that:

1. Create an action, append and finalize an attempt, reopen or reload through the normal persistence boundary, and assert the same identity, state, counts, classification, and history.
2. Request the same stable identity twice and assert only one logical record exists.
3. Exercise failed or rolled-back state transitions and assert no partial attempt outcome or mutable-history rewrite is committed.

Do not add redundant mock-heavy unit tests when these behaviors are covered through the real persistence boundary.

## Out of scope

- Execution-claim serialization and lease ownership.
- Retry/resume orchestration or scheduling.
- Downstream team-turn, review, merge, or completion-event idempotency.
- Recovery implementations for every lifecycle action.
- War Room or other presentation changes.
- Generic workflow orchestration.
