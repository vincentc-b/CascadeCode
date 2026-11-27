---
id: task_056_001_001
title: Define safe Feature approval eligibility and revision fence
tier: task
status: completed
parent: feat_056_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: b4983365f25e54138221180474a7db9465f5e4eb
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define safe Feature approval eligibility and revision fence

## Parent Feature

[feat_056_001](../../features/2_active/feat_056_001_separate_durable_feature_approval_from_execution_dependency_gates.md)

## Depends on

None.

## Acceptance criteria

1. Trace the current `approve_feature` authorization sequence and preserve corrective-plan, selected-provider, lifecycle architecture/comment, reviewed-context, applicable software, owner and existing request gates. Under the existing process lock, refresh the canonical owner and dependency board before any approval write.
2. Permit individual Feature approval when each unsatisfied dependency has the exact `dependency_incomplete` reason and legal noncancelled status/column. Refuse missing dependency/source, cancellation, illegal status/column, changed declaration or owner, and unknown evidence with a stable typed reason and affected work IDs. Keep `require_action_dependencies` strict for minting, Epic sign-off, Epic approval and dispatch.
3. Bind sorted `depends_on` IDs into both ordinary scope and corrective exact receipt revisions. Changing the declaration makes approval stale; predecessor status changing to completed does not. Preserve timestamp-then-receipt persistence and fail-closed unknown evidence after an interrupted write; explicit retry rechecks every approval gate and repairs evidence.
4. Keep existing approval and dispatch separation: this task does not relax Watchdog/Boss admission or create another scheduler or ledger.
5. Reconcile `cascade/DESIGN.md` approval requirements, sequence, failure/restart text and `cascade/feature/DESIGN.md` receipt lifecycle against implementation. Update affected `cascade-approval-code` and `cascade-feature-code` native Code nodes and source-contract semantic IDs when significant symbols change; link real files and declaration kinds. Record why context, container, component and Watchdog views remain unchanged or update them if the diff requires it.

## Files likely touched

`cascade/approvals.py`, `cascade/planning_action_dependencies.py`, `cascade/dependency_evaluation.py` only if needed, `cascade/feature/readiness_evidence.py`, `cascade/DESIGN.md`, `cascade/feature/DESIGN.md`, `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`, `tests/test_planning_action_dependencies.py`, `tests/test_approvals.py`.

## Implementation notes

Use the existing `DependencyEvaluation` rows and refresh path. An allowlist on the individual approval action is safer than changing `evaluate_dependencies` outcomes globally. Preserve duplicate/concurrent idempotence and do not use mutable predecessor state in the receipt digest. The parent Feature's API contract and diagram-impact inventory govern this change.

## Skills

None beyond SWE role defaults.

## Test plan

Run focused dependency and approval tests in isolated real-Git fixtures. Cover incomplete, missing, cancelled, status/column mismatch and completed predecessors; stale declaration and changed scope; an interrupted document/receipt write and explicit retry. Validate changed source symbols and architecture source contract; render affected C4 views locally when available, then trace context through Code and pinned source opening.

## Out of scope

HTTP/UI projection, Epic bulk behavior changes, dispatch gate relaxation, new dependency installation, deployment, unrelated refactors.
