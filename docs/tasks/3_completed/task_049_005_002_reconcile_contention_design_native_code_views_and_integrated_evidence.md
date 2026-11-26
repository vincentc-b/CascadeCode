---
id: task_049_005_002
title: Reconcile contention design, native Code views and integrated evidence
tier: task
status: completed
parent: feat_049_005
children: []
depends_on:
- task_049_005_001
owners:
- swe
skills: []
parent_rev: a90648ca8033e8e4ce63acf099a994a702763852
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reconcile contention design, native Code views and integrated evidence

## Parent Feature

[feat_049_005](../../features/2_active/feat_049_005_bound_transcript_acknowledgement_work_under_contention.md)

## Depends on

- task_049_005_001

## Acceptance criteria

- Reconcile the integrated implementation and tests against `cascade/recovery_progress/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/DESIGN.md`, root `DESIGN.md`, and affected `cascade/workspace/DESIGN.md` links. Give `REQ-RECOVERY-PROGRESS-004` an accurate verification claim that distinguishes measured bounded lock contention from uninterruptible filesystem/source baseline limits. Preserve one owner per requirement/decision and matter-of-fact current-design prose; keep delivery history and measured test runs in work records.
- Complete the all-level diagram impact inventory at the integrated diff: `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-supervisor-components`, `cascade-war-room-components`, `cascade-watchdog-code`, `cascade-dashboard-code`, and `cascade-workspace-code` when affected. For each, record owning design, changed source symbols, update or concrete no-change reason and verification. Native Code nodes and relationships must represent publisher fast path/public writer/drain/mapping, recovery append, graph fence, existing-index lookup and any changed Workspace owner resolution. Keep `model.dsl`, `views.dsl` and `workspace.contract.json` synchronized with real declarations, semantic IDs, kinds and source paths; do not alter accepted publication snapshots.
- Resolve `architecture/design-mappings.json` so `cascade/recovery_progress` maps to its own `DESIGN.md` and artifact owner. Verify architecture resource discovery and pinned links still resolve after the mapping correction; retain one authoritative owner for each Recovery Progress requirement and decision.
- In owning designs, source-link collaborating modules and explain inputs/outputs, SQLite and transcript state, normal publisher-before-graph commit, deadline exhaustion/pending, restart/replay and failure gates. Check the normal and contention/restart traces against source; reconcile affected parent/child interfaces without copying requirement ownership.
- Validate architecture source contract, supported local render and design/source links at exact integrated revision. In a local browser, traverse context → containers → component → native Watchdog and Dashboard Code; exercise Level up, restored deep links and pinned source for representative publisher/fence/index nodes. Check stale renamed/deleted symbols, changed ownership, warm artifact reuse and render-process bounds, recording measured results and limitations.
- Re-run the focused publisher, milestone, store and API tests against the integrated revision, including the Task 1 contention cases. Record exact revision, commands, named fixtures, timing tolerances/results, reviewed design paths, resolved gaps and remaining limits in closeout. Hand exact evidence to Epic and Feature 3 through the supported lifecycle; their final acceptance gate remains.

## Files likely touched

`cascade/recovery_progress/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/watchdog/DESIGN.md`, affected package/root/Workspace designs, `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`, focused verification artifacts.

## Implementation notes

Use existing model abstraction and add only code nodes/edges needed to explain the changed path. Do not claim hard real-time bounds for uninterruptible filesystem/source work.

## Skills

Apply `skills/design/SKILL.md` and `skills/roles/frugal_engineering/SKILL.md`.

## Test plan

Run the integrated focused regressions and architecture checks, then verify pinned browser navigation and source inspection.

## Out of scope

New public routes, dependency installation, accepted architecture snapshot rewrites, and changes to completed board records.
