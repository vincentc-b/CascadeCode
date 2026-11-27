---
id: task_049_002_005
title: Repair transcript replay durability and crash-safe room movement
tier: task
status: completed
parent: feat_049_002
children: []
depends_on:
- task_049_002_001
owners:
- swe
skills: []
parent_rev: 7cb0fd62977df31b2ff5e4bc5dd11f97f85614c9
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Repair transcript replay durability and crash-safe room movement

## Parent Feature

[feat_049_002](../../features/2_active/feat_049_002.md)

## Depends on

- task_049_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Acceptance criteria

Repair two Task 1 crash boundaries in the owning transcript store without changing the Epic storage contract:

1. When a pending append intent has a fully matching visible JSONL line, replay must fsync that file and any required parent directory before committing its event/index row or clearing the intent. Preserve exact-tail-only repair and a typed pending result for unexpected bytes.
2. Room movement must remain routable and retryable after process death between durable copy, source removal, owner switch and index/incarnation reset, including terminal retirement where switch_owner removes the checkout. Persist enough move state under the graph fence to distinguish a matching copied destination from conflicting bytes, recover/finish the owner and index transition, and leave unrelated destination/source bytes untouched.
3. Keep the source lifecycle lock outside the graph fence; preserve JSONL authority, unique source/message keys, fsync-before-index commit and acknowledgement after fence release. No GET repair, scheduler or new authority.
4. Add focused fault-injection/restart scenarios for full-line replay before fsync and each room-move boundary, including split roots and terminal retirement. Verify one authoritative history, no duplicate lines, stable routing and incarnation changes. Run focused War Room/Workspace tests.
5. Reconcile cascade/war_room/DESIGN.md and cascade/workspace/DESIGN.md with the actual durable move/replay protocol; update native cascade-dashboard-code/cascade-workspace-code and pinned model/views/source contract if symbols or relationships change. Check context/container/component remain accurate, Code Explore/Level up/deep links and source-kind/path validity; trace normal and crash recovery.

## Files likely touched

cascade/war_room/chat_store.py; cascade/workspace/integration_worktree.py as needed; cascade/war_room/DESIGN.md; cascade/workspace/DESIGN.md; pinned architecture model/views/contract as needed; tests/war_room/test_durable_chat_store.py; tests/workspace/test_integration_worktrees.py.

## Test plan

pytest -q tests/war_room/test_durable_chat_store.py tests/workspace/test_integration_worktrees.py; source-contract validation and pinned local Structurizr validation for any architecture edits.

## Out of scope

Receipt milestone consumer, authored reply identity, bounded transcript HTTP pages, unrelated lifecycle or repair policy changes.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
