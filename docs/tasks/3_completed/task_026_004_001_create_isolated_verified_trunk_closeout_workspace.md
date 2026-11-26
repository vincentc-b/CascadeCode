---
id: task_026_004_001
title: Create isolated verified-trunk closeout workspace
tier: task
status: completed
parent: feat_026_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 8afe236aac71e1d61a745c95ea791e4f5cef4658
created: '2026-10-27'
updated: '2026-10-27'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Create isolated verified-trunk closeout workspace

## Parent Feature

[feat_026_004](../../features/2_active/feat_026_004.md)

## Depends on

None.

## Acceptance criteria

- Resolve and verify the remote product-trunk revision used by closeout.
- Create a disposable isolated checkout pinned to that exact revision.
- Do not change the operator checkout's worktree, index, current branch, or HEAD.
- Cleanup removes only resources created for the isolated checkout and is safe after partial failure.

## Files likely touched

Closeout workspace/orchestration code and its nearest existing tests; exact paths should follow repository conventions discovered during implementation.

## Implementation notes

Implement the minimal workspace setup for trunk-dependent epic closeout: fetch/verify the remote product trunk and create an isolated checkout from that exact revision. Do not stash, clean, reset, commit, merge, or otherwise mutate the operator checkout. Ensure cleanup is scoped only to the isolated workspace.

## Skills

_(none)_

## Test plan

Exercise workspace creation and cleanup through the nearest existing integration boundary, including a cleanup/failure path if that boundary does not already cover it. Avoid duplicative mock-heavy unit coverage.

## Out of scope

Running review closeout, resuming the persisted close action, and the full dirty-trunk end-to-end regression.
