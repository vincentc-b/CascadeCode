---
id: task_049_003_004
title: Reconcile recovery UI architecture and integrated feature closeout
tier: task
status: completed
parent: feat_049_003
children: []
depends_on:
- task_049_003_003
owners:
- swe
skills: []
parent_rev: 3dd4f1d84e48a7855d03090c706e78cb02ee607e
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reconcile recovery UI architecture and integrated feature closeout

## Parent Feature

[feat_049_003](../../features/2_active/feat_049_003_show_coherent_recovery_progress_on_board_and_historical_transcript.md)

## Depends on

- task_049_003_003

## Acceptance criteria

- Pin producer ancestry to Feature 4 handoff `a3d4a42b3df92a553206c300c42142600183eaef`; atomic mapping original `469f0fa5f0bd99cf38351e26d6d7feb952bb26d3` is integrated via patch-equivalent `2e9fe23e`, while UTF-8 detail is integrated from `ecd390f4d1819d72bc65e2ea4960000a48e50a67`.
- Inventory `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-war-room-components`, `cascade-supervisor-components`, `cascade-team-components`, `cascade-dashboard-code`, `cascade-war-room-http-code`, `cascade-task-code`, `cascade-watchdog-code`, `cascade-workspace-code` and `cascade-teams-code`; name source symbols, owning designs, actual changes and concrete no-change reasons at every level.
- Verify producer ownership `REQ-RECOVERY-PROGRESS-001` through `004` and `DEC-RECOVERY-PROGRESS-001` through `002` in `cascade/recovery_progress/DESIGN.md`; War Room owns transcript/consumer behavior. Review parent and sibling interfaces, normal held-reply flow and pending/restart failure with links and actual state/persistence.
- Keep Feature 5's blocking graph-lock and 30-second schema-initializing index connection gap explicit. Its verified repair on the delivered baseline is required for final integrated Feature/Epic acceptance; a consumer workaround or Feature 4 lifecycle state is insufficient. Report Feature 4 scoped browser navigation separately from its broader documentation-refresh failure.

- Review root, Cascade, War Room, Task, Watchdog, Workspace and Recovery Progress designs against integrated diff; current facts only, one owner per requirement/decision.
- Reconcile context, container, component and affected Dashboard, War Room HTTP, Task, Watchdog, Workspace and Teams native Code views, model.dsl, views.dsl and workspace.contract.json to real declarations/kinds/owners; remove stale planning-only nodes.
- Trace source-linked normal held-reply publication and pending/replay, stale owner/incarnation failure, persistent state and restart behavior.
- Validate source contract and pinned local render; exercise context-to-Code, Level up, deep-link restore, pinned source open, stale/renamed symbol and ownership refusal, warm artifact reuse and bounded renderer operations.
- Record exact design paths/view keys/commands/results, no-change reasons and gaps in closeout; preserve accepted snapshots.

## Files likely touched

DESIGN.md; cascade/{DESIGN.md,war_room/DESIGN.md,task/DESIGN.md,watchdog/DESIGN.md,workspace/DESIGN.md,recovery_progress/DESIGN.md}; architecture target model.dsl/views.dsl/workspace.contract.json as needed.

## Implementation notes

Implement Task 4 in the feature spec: reconcile root/War Room/Task/Watchdog/Workspace/Recovery Progress designs and model/views/source contract to actual symbols, verify all diagram impact rows, normal and failure/replay flows, pinned render and context-to-Code navigation, deep links, stale symbols, source opening and warm artifact reuse; record exact gaps.

## Skills

_(none)_

## Test plan

Focused architecture source/contract/render/browser checks and final integrated acceptance evidence.

## Out of scope

No invented architecture node, deployment claim or full suite gate.
