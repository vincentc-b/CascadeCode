---
id: task_049_005_001
title: Bound transcript milestone locks and replay under one deadline
tier: task
status: completed
parent: feat_049_005
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 1a525d7ea0a36e429ed7aacb254d389670cf9985
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Bound transcript milestone locks and replay under one deadline

## Parent Feature

[feat_049_005](../../features/2_active/feat_049_005.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Acceptance criteria

- Start one monotonic deadline at entry to `publish_committed_transition`, `record_transcript_milestone`, and `drain_recovery_progress` (250 ms fast path, caller-selected drain allowance up to one second). Pass its remaining budget through `append_committed_recovery_receipt`, the publisher process lock and SQLite open/BEGIN/commit, `_record_transcript_milestone`, `fenced_transcript_source_acknowledgement`, and the graph thread/OS fence. No nested fixed timeout may reset the total allowance; do not begin a blocking acquisition after exhaustion. Account for the preceding append/dedup path. Distinguish uninterruptible source filesystem mutation/read costs from bounded lock waits in code comments and measured evidence.
- Make the fenced source-key lookup use an existing compatible transcript index only. It must perform no schema initialization, import, repair, transcript projection or publication. Missing/incompatible index, pending intent, unavailable room/owner and budget exhaustion yield pending while retaining replay eligibility.
- Keep publisher lock and transaction before graph fence, with graph fence held through mapping commit for first insert and update. Retain immutable receipt/entry/graph/message conflict rejection and current incarnation/append sequence; delayed private/public writers, rewrite, move and restart cannot downgrade a mapping. Timeout never fabricates a mapping, loses an authoritative receipt, advances the replay cursor past pending work or duplicates a milestone.
- Extend real integration tests in `tests/recovery_progress/test_transcript_milestones.py`, `tests/recovery_progress/test_publisher.py` and `tests/war_room/test_durable_chat_store.py` as needed. Deterministically hold a publisher or graph thread lock, a second process's OS graph flock, and SQLite writer locks; measure elapsed time with justified scheduler tolerance for fast path and drain. Release each contention source and prove a subsequent drain replays exactly once. Preserve existing delayed interleavings and malformed UTF-8 positive continuation.
- Run focused publisher, milestone, store and API regressions. Record exact commands, named tests, measured timing, source baseline limits, results and revision in closeout. Do not install dependencies or edit another team's checkout.

## Files likely touched

`cascade/recovery_progress/publisher.py`, `cascade/war_room/chat_store.py`, `cascade/war_room/recovery_milestones.py`, focused integration tests.

## Implementation notes

The authoritative ledger remains replay source. A deadline or uncertain source route means pending, not successful mapping. Preserve public routes and budgets. Do not rewrite accepted architecture snapshots.

## Skills

Apply `skills/roles/frugal_engineering/SKILL.md` and `skills/design/SKILL.md`.

## Test plan

Run focused contention and prior interleaving/replay regressions; provide timings and a normal plus pending/restart trace.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
