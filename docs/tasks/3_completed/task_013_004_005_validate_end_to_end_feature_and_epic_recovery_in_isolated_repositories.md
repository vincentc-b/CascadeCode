---
id: task_013_004_005
title: Validate end-to-end Feature and Epic recovery in isolated repositories
tier: task
status: completed
parent: feat_013_004
children: []
depends_on:
- task_013_004_002
- task_013_004_003
- task_013_004_004
owners:
- swe
skills: []
parent_rev: 2b8e5f1452993d96fc263be155cc99b87c2d0035
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate end-to-end Feature and Epic recovery in isolated repositories

## Parent Feature

[feat_013_004](../../features/2_active/feat_013_004.md)

## Depends on

- task_013_004_002
- task_013_004_003
- task_013_004_004

## Acceptance criteria

1. In real isolated repositories, run the audit through registered Feature and Epic adapters into concrete owning teams. Each path publishes owned-branch review evidence, reconciles cleanup/rollup and reaches terminal state exactly once.
2. Prove absent/completed owners and no-progress dispatch, while live slow planning, pending input/review, approval/comment/dependency gates, cancellation/return and dirty work remain protected.
3. Cover split tracking/product roots, restart after acknowledgement, stale generation, concurrent manual recovery, sibling blockers and unknown/failed publication. Retain failed or pending work with exact owner/resume action.
4. Record test commands, outcomes and any genuine limitation in a lightweight repository artifact; no mocked callback may stand in for required mutation or publication proof.

## Files likely touched

`tests/watchdog/`, `tests/feature/`, `tests/epic/`, `tests/test_review_health.py`, Epic 042 review/completion fixtures, `docs/task_artifacts/`.

## Implementation notes

Test the same registered capability and reservation path used by the supervisor. Inspect durable request, acknowledgement, result, original action identity and final board/review state. Reuse existing isolated Git/forge fixtures and avoid broad mock-heavy coverage.

## Skills

_(none)_

## Test plan

Run focused watchdog, Feature, Epic, review and completion suites plus the new isolated-repository acceptance flows. Document exact pass/fail evidence and stop after concrete risks are covered.

## Out of scope

UI, default-on enablement and redundant unit coverage.
