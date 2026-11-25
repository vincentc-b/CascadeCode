---
id: task_039_001_004
title: Enforce dependency readiness at planning entry points
tier: task
status: completed
parent: feat_039_001
children: []
depends_on:
- task_039_001_002
- task_039_001_003
owners:
- swe
skills: []
parent_rev: 7387bc3d57a6ac8b8ae777dc4577c169353922f0
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce dependency readiness at planning entry points

## Parent Feature

[feat_039_001](../../features/2_active/feat_039_001.md)

## Depends on

- task_039_001_002
- task_039_001_003

## Acceptance criteria

- Recompute current dependency readiness at ordinary mint_feature, both planning role sign-offs, and epic plan approval at their backend entry points, including direct MCP/API calls. Missing/invalid manifests, absent/stale evidence, unknown or mismatched actual environment, and declared unresolved feasibility fail closed.
- Before wiring the guards, reconcile the merged manifest and evidence schemas with the feature contract: per-entry target environments must identify runner, repository/worktree, sandbox, runtime, and applicable container digest; unknown required identity fields must not match. Entries must retain requested range, resolved version or explicit unknown, expected verification result, feasibility proof requirements, install destination, and the source/integrity/lock references needed for current evidence and approval. Exercise distinct per-entry environments and unresolved feasibility through the public readiness API.
- An explicit validated none_required manifest passes without a setup check or authorization prompt. Existing epics without a manifest are blocked only at their next guarded planning action; prior accepted work, run/checkpoint, and history remain intact.
- Reconciled approval recording and the operation-boundary guard reject legacy v1 entries as current authority until a new fully specified manifest revision is written and independently approved; preserve earlier manifest and approval records as history. The guard compares the attempted dependency, exact version, source, digest, target environment, scope/destination, operation, and cleanup plan with the current entry and matching human approval, and fails before mutation on any mismatch. Approval recording derives human identity from an authenticated boundary rather than a caller-supplied identity string.
- Sign-offs retain the existing epic plan-revision rule and reference immutable current dependency-evidence snapshots. Approval checks both current role sign-offs and snapshot validity. An epic document edit still requires both new-revision sign-offs; selective dependency changes invalidate affected evidence and cannot grant installation authority.
- Structured blocker codes identify dependency, environment, last attempt, and next action where available. Plan approval alone creates no installation approval.
- Integration/API tests cover all guarded entry points, valid and blocked flows, explicit empty manifest, legacy epic, stale/mismatched environment, selective invalidation, and no installation authority after approval.

## Files likely touched

cascade/epic/mint.py; cascade/epic/planning_signoffs.py; cascade/epic/plan_readiness.py; cascade/approvals.py; relevant MCP/War Room wrappers and tests/epic integration tests.

## Implementation notes

Compute current dependency readiness from the manifest, actual-environment evidence, and unresolved feasibility state under existing lifecycle/tracking-repository primitives. Guard ordinary mint_feature, both planning role sign-offs, and plan approval at their authoritative backend entry points, including direct MCP/API paths; preserve existing whole-plan revision sign-off behavior. Missing manifest, stale/absent evidence, unknown or mismatched environment, and unresolved feasibility block; a validated explicit empty manifest passes. Apply to existing epics on their next guarded action without restarting runs or cancelling accepted work. Bind sign-offs to immutable dependency-evidence snapshots; plan approval creates no installation authority. Add high-signal integration/API tests for all three guards, valid/blocked flows, selective invalidation, legacy epics, and no-dependency flow.

## Skills

_(none)_

## Test plan

Use a compact lifecycle/API matrix with temporary tracking repository fixtures and deterministic evidence records. Check the authoritative backend guard directly plus one wrapper path per entry point; retain existing plan-signoff regression tests.

## Out of scope

No installation runner, bootstrap state machine, ping/resume, War Room installation controls, or epic_034 Structurizr smoke scenario.
