---
id: task_051_003_001
title: Normalize authoritative review, CI and feedback evidence
tier: task
status: completed
parent: feat_051_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d88eb696965a89d17b73e596e14538e1c2d14fda
created: '2026-11-26'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Normalize authoritative review, CI and feedback evidence

## Parent Feature

[feat_051_003](../../features/2_active/feat_051_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Goal: normalize current GitHub/GitLab review facts in cascade/tracking.py using scripted Runner transport. Extend merge_request_snapshot with original review identity, exact source and target heads, mergeability, authoritative required-check policy, per-check results with check-run/pipeline generation, and review feedback/approval state. Keep unavailable/unknown explicit. A forge listing with zero checks does not establish an empty required policy; only authoritative target policy does. Distinguish failed, pending, missing, stale, green, approval-only wait, actionable human feedback, conflict/moving target, transient outage and terminal disposition. No forge text becomes an executable command.

Acceptance: production normalization tests in tests/test_tracking_find.py or a focused adjacent test drive both forge adapters through scripted transport, including policy unavailable, missing result, stale source/target, newer failed generation after old green, and confirmed empty policy. Preserve existing snapshot consumers and review identity. Update cascade/DESIGN.md shared forge/check contract with stable IDs and source-linked normal/failure evidence flow; reconcile the merge_request_snapshot node and its component relationship in model.dsl, views.dsl and workspace.contract.json. Record landscape/context/container unchanged reasons if the diff does not alter actors or deployment. Validate source contract, pinned local render and context→container→component→Code navigation/deep link/pinned source; report actual checks and limits in task closeout.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
