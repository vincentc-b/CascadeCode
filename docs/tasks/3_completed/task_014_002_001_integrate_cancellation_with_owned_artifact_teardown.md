---
id: task_014_002_001
title: Integrate cancellation with owned-artifact teardown
tier: task
status: completed
parent: feat_014_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2ec9d63a2458eb2b1e78aa3b3661b1fe04dd7d95
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Integrate cancellation with owned-artifact teardown

## Parent Feature

[feat_014_002](../../features/2_active/feat_014_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

On cancellation of in-flight work, invoke the existing worktree/branch teardown path using the cancelled work item as the ownership boundary. Preserve canonical/base branches and unrelated or uncommitted user work. Make cleanup safe to retry, and persist/return actionable partial-failure state instead of reporting a clean cancellation when teardown is incomplete.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
