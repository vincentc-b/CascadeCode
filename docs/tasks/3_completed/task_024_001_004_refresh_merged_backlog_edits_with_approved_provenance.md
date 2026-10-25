---
id: task_024_001_004
title: Refresh merged backlog edits with approved provenance
tier: task
status: completed
parent: feat_024_001
children: []
depends_on:
- task_024_001_001
owners:
- swe
skills: []
parent_rev: 90cda45b486fd8f2c1b3900a30e6707d495bd908
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  swe: gpt-5.6-luna
---
# Refresh merged backlog edits with approved provenance

## Parent Feature

[feat_024_001](../../features/2_active/feat_024_001.md)

## Depends on

- task_024_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Narrowly correct backlog refresh and activation-source precedence so a merged edit updates the existing board item and becomes the approved activation source without disturbing authoritative live state.

## Scope

- Inspect and update backlog snapshot import, integration-worktree reads, document routing, tracking, and activation provenance together.
- During scheduled sync or forced refresh, import the merged revision for the same backlog epic ID when the current item is snapshot-only or a stale local backlog copy.
- Refresh the existing board row and plan detail, including provider/model/reasoning assignments; do not create a duplicate item.
- Record/use the approved source revision displayed on the board for later human-gated activation instead of selecting a stale local HEAD.
- Preserve active, completed, or otherwise live integration state when a late edit merges.
- On fetch/parse/refresh failure retain the last valid board.
- Leave operator checkout and active worktrees untouched.
- Keep the change specific to eligible backlog briefs; do not build general branch reconciliation or a new sync service.

## Acceptance

- After a merged upstream edit, both snapshot-only and stale-local-backlog cases display the approved content and assignments on the same board item.
- Activation consumes the same approved revision shown on the board.
- A late merged edit cannot overwrite active/completed/live integration state.
- Refresh failures preserve the last valid board, and diverged operator checkouts/worktrees remain unchanged.
- Integration tests use real temporary repositories for the precedence and provenance scenarios.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
