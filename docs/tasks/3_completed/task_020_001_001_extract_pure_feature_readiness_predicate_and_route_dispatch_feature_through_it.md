---
id: task_020_001_001
title: Extract pure feature readiness predicate and route _dispatch_feature through it
tier: task
status: completed
parent: feat_020_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 10207c9b3e77020f0fcb2ffb93b501d817f96994
created: '2026-10-23'
updated: '2026-10-23'
---
# Extract pure feature readiness predicate and route _dispatch_feature through it

## Parent Feature

[feat_020_001](../../features/2_active/feat_020_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
Create one pure readiness predicate module that returns `{approved: bool, blockers: [codes]}` for a feature, and make `cascade/watchdog/dispatch.py::_dispatch_feature` consume it.

## Scope
- Merge into the predicate: `_dispatch_feature` gates (open status/parent, `unmet_deps` with dep ids, `not_approved`, dependency/epic `feature_awaiting_merge`, sibling block), the `compute_boss_view` feature-filter checks (`feature_dependency_ready`, `feature_merge_gated`, `meta.approved_at`, `1_backlog` path check), and the active-parent-epic check from `automation.reconcile_approval_dispatch` (`epic_inactive`).
- Cover post-gate refusals read-only: `read_feature_dispatch_selection`, or `plan_feature_dispatch` (pure) when no selection is persisted -> `dispatch_base_unavailable` with underlying reason (`unsupported_topology`, `missing_predecessor_pr_identity`); then `comments.gate.refusal_if_blocked` -> `review_threads_blocking`.
- Approval is reported independently of other blockers.
- Stable codes: `not_approved`, `unmet_deps`, `feature_awaiting_merge`, `sibling_blocked`, `dispatch_base_unavailable`, `review_threads_blocking`, `epic_inactive`.

## Constraints
- Predicate never calls `ensure_*`, writes files, appends events, or takes the dispatch process lock.
- No loosening: at least as strict as the conjunction of boss-view and dispatch checks today. Record any semantic difference found via `record_decision` on feat_020_001.
- `_dispatch_feature` returns the first blocker in today's order, mapped to existing `DispatchResult.reason`: `sibling_blocked` -> `feature_awaiting_merge`; `dispatch_base_unavailable` -> underlying reason; `review_threads_blocking` -> existing refusal text. Manual `dispatch_feature` ignores `epic_inactive` as today. The persisting `ensure_feature_dispatch_selection` call stays in `_dispatch_feature` after the predicate passes.

## Done when
Existing dispatch tests pass unchanged. No per-gate unit tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
