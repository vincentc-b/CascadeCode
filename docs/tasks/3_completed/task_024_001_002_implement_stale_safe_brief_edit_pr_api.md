---
id: task_024_001_002
title: Implement stale-safe brief edit PR API
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
# Implement stale-safe brief edit PR API

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

Add the server-side read and submit flow that turns a valid edit of an eligible backlog epic into one isolated review PR/MR.

## Scope

- Add HTTP routes following existing conventions to fetch an editable brief and submit its edited representation with explicit source provenance.
- On submit, fetch and compare the target brief revision before writing. Reject stale content, deletion, or a target that is no longer backlog with an actionable reload response; unrelated trunk commits must not invalidate an unchanged target.
- Validate through the shared provider/model inventory and brief-edit model, including explicit reasoning clears and no-op detection.
- Reuse current Git, remote-selection, branch, and forge infrastructure to create a fresh isolated branch and PR/MR against configured product trunk.
- Modify only the selected brief at its original path even when the title changes; never overwrite the approved local copy as part of submission.
- Prevent duplicate in-flight submissions. Return a real review URL only after forge creation succeeds.
- Use structured error responses that let the UI preserve input and support understandable retry/recovery.

## Acceptance

- A valid changed submission produces a one-file diff and a new PR/MR with the existing brief ID/path intact.
- Stale, deleted, no-longer-backlog, invalid, duplicate, and no-op requests do not create a PR/MR or mutate approved state.
- Failures before or during branch/forge work leave operator checkout and active worktrees untouched and can be retried safely.
- Preserve create-brief behavior with focused regression coverage using real temporary Git repositories and a fake forge boundary.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
