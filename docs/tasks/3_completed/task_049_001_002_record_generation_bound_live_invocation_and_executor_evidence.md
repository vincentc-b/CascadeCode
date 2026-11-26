---
id: task_049_001_002
title: Record generation-bound live invocation and executor evidence
tier: task
status: completed
parent: feat_049_001
children: []
depends_on:
- task_049_001_001
owners:
- swe
skills: []
parent_rev: 9c97b16f8c3d6853c7a1903cbaddd71c1fcd83e0
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Record generation-bound live invocation and executor evidence

## Parent Feature

[feat_049_001](../../features/2_active/feat_049_001_project_evidence_based_recovery_progress.md)

## Depends on

- task_049_001_001

## Acceptance criteria

- In Workspace kickoff, record explicit begin/end of the admitted graph invocation, and in Task `resume_action`, record executor entry/exit around the actual call. Bind observations to worker runtime generation, PID/boot/process-start identity, invocation token, graph, action generation and exact attempt/claim. The supervisor refreshes only matching registered live tokens.
- Expire a live observation after at most 30 seconds or earlier claim expiry; observed stop/death invalidates immediately. Inaccessible/dead/expired/legacy/unmatched ownership is unknown or stale, never live execution. A process existing or `graph_turn_owner_is_live` returning true for queued work is insufficient. Live evidence is observational and cannot reclaim claims or change repair policy.
- Exercise queued but idle, admitted live investigation without repair, matching live executor, claim expiry, mismatched generation/attempt/claim, unknown process, worker restart and a held executor. Assert no executing claim survives stop/death or ambiguous identity.
- Reconcile `cascade/workspace/DESIGN.md`, `cascade/task/DESIGN.md` and affected `cascade/DESIGN.md` with source-linked invocation/executor state and restart behavior. Update actual `cascade-workspace-code` and `cascade-task-code` nodes plus component ancestors, and synchronize model.dsl/views.dsl/workspace.contract.json. Check declaration kinds and source links; do not model modules as deployed containers. See feature plan's shared API and diagram inventory.

## Files likely touched

- `cascade/workspace/kickoff.py` and the existing worker identity/registry module used by kickoff.
- `cascade/task/action_recovery.py` and its execution evidence owner.
- `cascade/workspace/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/DESIGN.md`, and the three synchronized architecture source/contract files named in the feature plan.

## Implementation notes

Keep invocation and executor tokens observational. Use the existing supervised worker lifecycle and claim identity; do not grant repair authority through a liveness record. Name the concrete source symbols and declaration kinds in the Code views after implementation.

## Skills

_(none)_

## Test plan

Run focused workspace kickoff and Task recovery tests with a held executor. Assert queue-only activity does not prove invocation, exact tokens distinguish investigating from executing, and stop, death, expiry, mismatch and restart remove live claims. Validate the updated architecture source contract and local render.

## Out of scope

Current-progress materialization, public GET and board projection; those belong to Tasks 3 and 4. Do not change repair admission or claim policy.
