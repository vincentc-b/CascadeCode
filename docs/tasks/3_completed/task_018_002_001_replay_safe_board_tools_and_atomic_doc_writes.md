---
id: task_018_002_001
title: Replay-safe board tools and atomic doc writes
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2fb5e0ef1e58b297b378c4be6ac2054bff58ae7b
created: '2026-10-23'
updated: '2026-10-23'
---
# Replay-safe board tools and atomic doc writes

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Make board effects safe to replay when a resumed role node re-runs from the start (epic dec_005, dec_007). Does not depend on feat_018_001.

Acceptance:
- `record_decision`: if an identical entry (same section and choice) is already in the log, return the existing id and append nothing.
- `mint_feature`: if a child with the same title exists under the same parent, return the existing id; `append_event` fires only when a child is actually created.
- `reply_comment`: if the same author already posted an identical body on the same comment, return the existing reply id.
- `resolve_amendment`: resolving an already-resolved amendment is a no-op.
- `write_doc` keeps its `sha` compare-and-swap.
- `board/store.py` doc writes are atomic: write a temp file in the same directory, then `os.replace`.
- A resumed model that uses different wording is not deduplicated (accepted).

Testing: no per-tool unit-test matrix and no atomic-write unit test. Integration test (b) in the integration-tests task covers these paths.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
