---
id: task_020_001_004
title: Treat parentless open features as not dispatchable in the readiness predicate and boss view
tier: task
status: completed
parent: feat_020_001
children: []
depends_on:
- task_020_001_003
owners:
- swe
skills: []
parent_rev: 83a46d0120e4adff22e8bd1c3f59a3b6c8f79d75
created: '2026-10-23'
updated: '2026-10-23'
---
# Treat parentless open features as not dispatchable in the readiness predicate and boss view

## Parent Feature

[feat_020_001](../../features/2_active/feat_020_001.md)

## Depends on

- task_020_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Problem

`cascade/feature/readiness.py::compute_feature_readiness` returns early with no blockers when `meta.parent` is empty. Since task 2 (`87437b2`), `compute_boss_view` relies only on that predicate, after its `_backlog_open` filter. So a parentless open backlog feature, even an unapproved one, is listed in `dispatchable_features`. `reconcile_approval_dispatch` skips only `epic_inactive`, so it calls `dispatch_feature` on that feature every cycle and gets `bad_state`. The board also shows `blockers: []`. This breaks the spec's no-loosening rule.

## Change

1. In `compute_feature_readiness`, the no-parent branch returns `blockers=["epic_inactive"]` instead of `[]`, with approval still reported independently. Leave the early return for non-open status as it is; every caller already filters on open status first.
2. In `cascade/boss/view.py::compute_boss_view`, also require `meta.parent` for a feature to be dispatchable, because `feature_boss_dispatchable` deliberately ignores `epic_inactive`. Reconcile then skips the feature as well, through both the boss view and its existing `epic_inactive` check.
3. `_dispatch_feature` stays unchanged. It already returns `bad_state` for a parentless feature before it calls the predicate.

## Tests

Add one parentless-feature case to the existing `tests/war_room/test_board_feature_readiness.py`. Assert that the row's `readiness.blockers` contains `epic_inactive`, and that the feature is not in `compute_boss_view().dispatchable_features`. Do not add per-gate unit tests.

## Done when

The existing dispatch, boss-view, automation and war_room tests pass, and the new case passes.

## Do not touch

`cascade/feature/briefing.py` and `cascade/war_room/planning_transcript.py`. Their task 3 changes are an open question for reviewers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
