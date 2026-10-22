---
id: task_014
title: Implement atomic remote backlog snapshot refresh
tier: task
status: completed
parent: feat_006
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 23499b7b2413592bbe7c0ff8135926df551ea2f4
created: '2026-10-21'
updated: '2026-10-21'
---
# Implement atomic remote backlog snapshot refresh

## Parent Feature

[feat_006](../../features/2_active/feat_006.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Replace trunk fast-forwarding with a Cascade-managed, read-only snapshot of backlog epic briefs from the configured remote product-trunk ref.

## Scope
- Fetch through normal Git operations without changing the operator checkout, active branches, edits, or registered integration worktrees.
- Atomically publish snapshot documents plus the immutable fetched revision used to produce them.
- Validate remote/ref availability, document shape, and duplicate IDs before publication.
- Preserve the last valid snapshot on any refresh failure and expose actionable diagnostics.
- Preserve existing manual behavior when automation is disabled.

## Verification
Add focused repository-level tests for successful refresh, restart/provenance persistence, missing remote/ref, fetch failure, malformed briefs, duplicate IDs, atomic replacement, and last-known-good retention.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
