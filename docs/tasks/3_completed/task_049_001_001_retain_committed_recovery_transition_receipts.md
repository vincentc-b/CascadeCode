---
id: task_049_001_001
title: Retain committed recovery transition receipts
tier: task
status: completed
parent: feat_049_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 9359a45c9d5506fd956f295bf4c7a97bb4dcc45a
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Retain committed recovery transition receipts

## Parent Feature

[feat_049_001](../../features/2_active/feat_049_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope and acceptance
- In Task action writes (`create_or_load_action`/routing, `acknowledge_team_recovery`, `_claim_resume_attempt`, `record_action_checkpoint`, `finalize_attempt`) and Watchdog persisted stage/result/postcheck writes, retain minimal immutable v1 transition receipts in the same authoritative action/incident commit under its lifecycle lock. Reuse existing immutable receipts when sufficient; add monotonic per-source sequence where mutable fields overwrite transitions.
- Each receipt binds source kind/key, action, original incident if known, generation, owning graph/affected work, attempt/claim, transition sequence, nullable occurrence time, allowlisted safe payload and deterministic source reference. Observation refresh, identical text and equal timestamps do not define event identity. Distinct repeated stage entries remain distinct. Retain until durable transcript acknowledgement; no automatic pruning.
- Notify the deterministic publisher only after the outer lifecycle lock releases, carrying the committed receipt/snapshot. Dispatch committed start evidence in `resume_action` after claim/preflight and before the long executor call; preflight refusal records refusal and never proves execution. A missed notification leaves replayable receipt. Notification failure never changes repair outcome or grants capability.
- Focused tests cover source-commit-before-notification crash, duplicate/repeated transitions, generation/attempt identity, concurrent writes and one held executor where start evidence appears before completion. Measure baseline monolithic ledger load/atomic replacement cost; report it as a limit.
- Reconcile `cascade/task/DESIGN.md` and `cascade/watchdog/DESIGN.md` with actual source-linked normal/failure flows. Update `cascade-task-code`, `cascade-watchdog-code`, component ancestors, model.dsl/views.dsl/workspace.contract.json together for real symbols and declaration kinds. Trace restart without invented repair effects. See feature plan's shared API and diagram inventory.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
