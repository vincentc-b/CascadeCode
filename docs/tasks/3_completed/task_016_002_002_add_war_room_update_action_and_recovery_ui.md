---
id: task_016_002_002
title: Add War Room update action and recovery UI
tier: task
status: completed
parent: feat_016_002
children: []
depends_on:
- task_016_002_001
owners:
- swe
skills: []
parent_rev: 3dcca657b1807bae983e8725abeb49094ccce6bb
created: '2026-10-23'
updated: '2026-10-23'
---
# Add War Room update action and recovery UI

## Parent Feature

[feat_016_002](../../features/2_active/feat_016_002.md)

## Depends on

- task_016_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Expose branch drift and safe recovery on active War Room cards through the board/API contract from task_016_002_001.

## Scope

- Show accurate ahead/behind state on active epic, feature, and task cards.
- Show Update branch only when a work branch is behind.
- Disable the action while the item is busy or otherwise ineligible, displaying the stable reason and concise operator recovery guidance.
- POST the update request and refresh the board after success so updated counts render and the action disappears once current.
- Render typed dirty_index, local_changes, branch_conflict, busy, and invariant failures without raw Git output.
- For conflicts, list validated blocking paths and state that the merge was aborted.
- Keep the original task-merge or epic-close action available for retry after update or manual recovery.
- Do not add remote fetch, automatic retries, stashing, conflict resolution, or new lifecycle workflows.

## Verification

Add one browser-level interaction test covering behind-state visibility, disabled eligibility guidance, successful update and refresh, action removal once current, conflict recovery rendering, and retention of the original retry action.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
