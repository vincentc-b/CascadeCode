---
id: task_020_002_002
title: 'End-to-end integration test: late-minted feature approval and single dispatch'
tier: task
status: completed
parent: feat_020_002
children: []
depends_on:
- task_020_002_001
owners:
- swe
skills: []
parent_rev: b08df021b3402105acba63c4d9a32cdb193dd8aa
created: '2026-10-23'
updated: '2026-10-23'
---
# End-to-end integration test: late-minted feature approval and single dispatch

## Parent Feature

[feat_020_002](../../features/2_active/feat_020_002.md)

## Depends on

- task_020_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Write one integration test, either browser-level or HTTP plus rendered-board level. Reuse the fixtures in `tests/war_room/test_board_feature_readiness.py` rather than building a parallel fixture set.

The test must cover:
1. An epic with initial children gets its plan approved, and those children are approved.
2. A feature minted afterward is unapproved. Its board row shows `readiness.approved == false` and the awaiting-approval state with the approve action.
3. One POST to `/api/approve_feature` returns 200 without running a model turn inline. Stub the kickoff runner and assert the kickoff is queued in the background, not invoked on the request thread.
4. Exactly one `dispatch_feature` succeeds. A second approve POST and a board refresh produce no extra dispatch, worktree, queue event, or kickoff.
5. Variant: when the late feature depends on an unmerged sibling, approval persists, the feature stays in backlog, and the blocker is shown. Assert on the `unmet_deps:<sibling_id>` prefix form, plus `feature_awaiting_merge` or `sibling_blocked` if the fixture puts the sibling in review.

Add only this test, with no redundant unit tests. Touch `approvals.py` or the approve handler only if the test exposes a real defect, and if you do, record why in the task notes.

Done when: the test passes on the feature branch and the existing war_room tests still pass.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
