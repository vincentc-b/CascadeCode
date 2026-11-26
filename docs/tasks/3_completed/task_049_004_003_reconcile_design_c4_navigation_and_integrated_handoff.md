---
id: task_049_004_003
title: Reconcile design, C4 navigation and integrated handoff
tier: task
status: completed
parent: feat_049_004
children: []
depends_on:
- task_049_004_001
- task_049_004_002
owners:
- swe
skills: []
parent_rev: f9661680f1f17ea47ef16fb466320c8981d63f4f
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reconcile design, C4 navigation and integrated handoff

## Parent Feature

[feat_049_004](../../features/2_active/feat_049_004_prevent_stale_transcript_acknowledgements_from_regressing_recovery_routing.md)

## Depends on

- task_049_004_001
- task_049_004_002

## Acceptance criteria

- Give the significant `cascade/recovery_progress/` producer a child `DESIGN.md` with its own stable requirement and decision IDs, source-linked modules, publisher SQLite state, normal flow, pending evidence, delayed acknowledgement, room movement and restart/replay behavior. Update Watchdog and parent summaries to link to that owner without duplicating its requirements or decisions. Keep the War Room transcript contract owned in the War Room design.
- Reconcile current-design text against final code. Remove any claim that a pre-transaction or conditional refresh prevents stale routing unless the graph fence actually remains held through the publisher SQLite commit for first insertion and refresh. Cover malformed UTF-8 detail refusal and positive continuation in the War Room design.
- Record diagram impact for `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-supervisor-components`, `cascade-war-room-components`, `cascade-watchdog-code`, `cascade-dashboard-code`, and `cascade-workspace-code` if move behavior changes. For each view, name changed source symbols, owner, required edit or concrete no-change reason, and verification result. Preserve valid container boundaries, semantic IDs, declaration kinds, `resume_transcript_room_move` and its retirement relationship.
- Give the authoritative transcript source-key lookup a native `cascade-dashboard-code` node if it remains a significant separate entry point. Connect the publisher mapping helper to it and the lookup to the graph fence according to real calls and lock order. Reconcile detail reader behavior. Synchronize `model.dsl`, `views.dsl` and `workspace.contract.json` with changed Code nodes or edges; check renamed/deleted symbols for stale links.
- Validate source contract and supported local render. In browser, traverse context → containers → component → native Code, use Level up and restored deep links, and open pinned source for publisher mapping, source lookup and detail reading. Check warm artifact reuse and render-process bounds; report measured performance.
- Run focused milestone/publisher/store and transcript API regressions, architecture source-contract checks and diff checks at the exact integrated Feature revision. Trace one normal and one delayed/failure/restart scenario against source. Record fixture paths, commands/results, design paths reviewed, updates or no-change reasons and unresolved gaps in closeout.
- Reconcile final Feature 2 route/header/error/detail fixtures and provide exact revision, fixture paths and measured results to the parent and Feature 3. Do not claim Epic acceptance or alter other teams' completed board records.

## Files likely touched

`cascade/recovery_progress/DESIGN.md`; `cascade/watchdog/DESIGN.md`; `cascade/war_room/DESIGN.md`; `cascade/workspace/DESIGN.md`; root and package designs where interfaces change; `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`; focused architecture and UI verification artifacts.

## Implementation notes

After Tasks 1 and 2 integrate, reconcile the owning designs and revision-pinned Structurizr model against actual code. Keep durable design prose in present tense. Put delivery IDs, chronology, commands and measured results in Task or Feature closeout.

## Skills

Apply `skills/design/SKILL.md` and `skills/roles/frugal_engineering/SKILL.md`.

## Test plan

Run the focused regressions and architecture checks listed above at the integrated revision, then verify the specified navigation and pinned-source path in a local browser.

## Out of scope

Route redesign, new dependencies, and edits to other teams' completed board records.
