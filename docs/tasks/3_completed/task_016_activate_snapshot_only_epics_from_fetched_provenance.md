---
id: task_016
title: Activate snapshot-only epics from fetched provenance
tier: task
status: completed
parent: feat_006
children: []
depends_on:
- task_014
- task_015
owners:
- swe
skills: []
parent_rev: 943c6f1f0eedd36540fc30c592e51e8131607be9
created: '2026-10-21'
updated: '2026-10-21'
---
# Activate snapshot-only epics from fetched provenance

## Parent Feature

[feat_006](../../features/2_active/feat_006.md)

## Depends on

- task_014
- task_015

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Allow an authorized remote-visible backlog epic to activate from the exact fetched revision containing its approved brief.

## Scope
- Resolve and validate the persisted snapshot revision for a snapshot-only epic.
- Create the epic integration branch/worktree from that immutable fetched revision.
- Materialize the approved brief while preserving applicable trunk-pointer, authorization, registry, and dispatch contracts.
- Do not check out, merge, reset, stash, or fast-forward the operator checkout.
- Fail actionably if provenance is unavailable or stale without damaging existing dispatch state.

## Verification
Cover activation provenance and authorization, branch/worktree base correctness, unchanged operator HEAD/branch/tracked edits, unchanged active integration worktrees, restart behavior, and safe failure paths.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
