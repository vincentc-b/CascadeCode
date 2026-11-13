---
id: task_046_001_006
title: Repair GitHub review snapshot source revision query
tier: task
status: completed
parent: feat_046_001
children: []
depends_on:
- task_046_001_005
owners:
- swe
skills: []
parent_rev: 69a27b208fcbb3cb69bc620843d48a17c5036796
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Repair GitHub review snapshot source revision query

## Parent Feature

[feat_046_001](../../features/2_active/feat_046_001.md)

## Depends on

- task_046_001_005

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Defect

`cascade/tracking.py::merge_request_snapshot` passes `headRefOid` to `gh pr view --json`. The installed GitHub CLI rejects that field before returning a snapshot. This caused `feat_046_001:review-health:review_snapshot_failed:f9fef92474d2c2cf`, although PR 226 is open and mergeable. Existing tests mock the unsupported response field, so they missed the CLI contract failure.

## Required repair

Use a supported GitHub CLI field or supported API call to obtain the PR source commit while preserving `source_revision`, merge commit, mergeability, description, and comment behavior. Update the snapshot test to assert the exact supported `gh` query and source SHA extraction; include a focused regression for a real CLI-compatible response. Keep GitLab behavior unchanged.

## Validation and handoff

Run `pytest -q tests/test_tracking_find.py` and the relevant review-health/reconciliation tests. Show `gh pr view 226 --json ...` succeeds with the chosen fields. Deliver through the normal Task review path so Feature review health can recheck PR 226. Do not edit trunk or install dependencies.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
