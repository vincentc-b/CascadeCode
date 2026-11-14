---
id: task_013_001_004
title: Register scoped health auditor authority and executable capability checks
tier: task
status: completed
parent: feat_013_001
children: []
depends_on:
- task_013_001_001
- task_013_001_003
owners:
- swe
skills: []
parent_rev: e42512edf87a275dc4c15513cf66b40350b9ad28
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Register scoped health auditor authority and executable capability checks

## Parent Feature

[feat_013_001](../../features/2_active/feat_013_001.md)

## Depends on

- task_013_001_001
- task_013_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Define the named health_auditor role and an incident-scoped operation allowlist. Register only existing lifecycle recovery operations with explicit failure classes, owner routing, evidence requirements, reachability, finite retry policy, and durable result paths.

## Acceptance
- Startup and per-incident probes prove the selected operation is registered, authorized for the concrete work ID/owner, can reach its required worktree/action, and can persist request, acknowledgement, and result.
- Missing or inaccessible capability becomes a durable actionable incident with an exact resume path and later re-evaluation when capability changes.
- The role cannot cross human plan/feature approval, comment, dependency, credential, installation, destructive Git, or ambiguous conflict gates.
- Registration reuses executable Task/Feature/Epic recovery seams; event-only routing does not count as executable repair.

## Validation
Exercise concrete-owner authorization, denied gates, missing capability, and capability arrival without invoking model or forge.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
