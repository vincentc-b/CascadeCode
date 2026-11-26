---
id: task_034_010_001
title: Reconcile completed recovery review identity for legacy missing IDs
tier: task
status: completed
parent: feat_034_010
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 865c9268c91b33d94a21b9a98c78bb744b2ff874
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reconcile completed recovery review identity for legacy missing IDs

## Parent Feature

[feat_034_010](../../features/2_active/feat_034_010.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the narrow completed-recovery identity join correction in the existing audit collector/observation path. Reproduce the retained F shape with a persisted-store fixture: exact resolution action and owner, completed review_health_restored reconciliation, matching recognized registry-qualified GitHub repository/pull URL, admission review_id='218', recovery review_id=null. Resolve absent optional numeric ID only when the authoritative reviews registry and exact forge/repository/URL identity establish equivalence; never overwrite or accept a supplied conflicting ID, URL, owner, action, forge, or repository. Preserve live/failed/unrelated actions, malformed/ambiguous and unavailable evidence behavior, historical stores, and Feature I terminal-parent eligibility. Cover the real collector path with positive legacy and negative conflict/unavailable controls; repeated projection must be read-only and idempotent. Run focused checks and report evidence for independent review/canonical publication. Do not reset lifecycle or retry completed children; distinguish accepted integration from deployment and request fresh authoritative F audit reassessment after delivery.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
