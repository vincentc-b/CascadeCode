---
id: task_048_002_003
title: Prove one real owner-agent repair and legacy timeout recovery journey
tier: task
status: completed
parent: feat_048_002
children: []
depends_on:
- task_048_002_002
owners:
- swe
skills: []
parent_rev: e3ac22202348e60ce02334243c4b3b38a63689a3
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove one real owner-agent repair and legacy timeout recovery journey

## Parent Feature

[feat_048_002](../../features/2_active/feat_048_002_execute_and_independently_verify_the_bounded_owner_agent_repair_journey.md)

## Depends on

- task_048_002_002

## Acceptance criteria

- Build deterministic integration harness through production worker/watchdog queue, durable checkpoints, actual role-scoped tool dispatch, Task test/commit/delivery, owner validation/publication and independent remote/postcondition inspection. Script only external paid-provider and forge transport. Use temporary repositories, bare remote, real validator processes, true red checks and process-group timeout cleanup. First prove one admitted incident repaired via owner tools and resolved only by fresh authoritative postcheck; assert no duplicate Task/review/worker/publication on repeat sweeps or competing caller. Replay unchanged timeout + legacy exhausted next-decision through restart, approved policy correction and authorized extension when necessary; preserve old attempts/decisions. Unavailable policy owner must wait with named next action.
- Architecture: reconcile Agent, Watchdog, Task, tier and cascade parent designs with sequence, persistence and restart; update cascade-agent-code, cascade-watchdog-code, cascade-teams-code, affected tier code views and component views for actual symbols. Verify context/containers remain accurate, source contract/local render and browser navigation/deep links/pinned source.

## Diagram-impact acceptance

| Level / view | Required source-linked reconciliation |
|---|---|
| `cascade-landscape`, `cascade-context`, `cascade-containers` | Check actual provider/forge/operator boundary and worker/Task-sidecar process/storage against the positive journey; record source-backed no-change reasons or update changed relationships. |
| `cascade-supervisor-components`, `cascade-team-components` | Show owner dispatch, Task check/delivery, review publication and Watchdog postcheck with actual owning components. |
| `cascade-agent-code`, `cascade-watchdog-code`, `cascade-teams-code` and affected tier Code views | Trace `run_role`, `run_planning_role_turn`, `run_swe_turn_sync`, `dispatch_planning_tool`, `dispatch_audit_recovery`, `reconcile_parent_lifecycle_incident` and changed provider/Task declarations to real source and declaration kinds. Reconcile model.dsl, views.dsl and workspace.contract.json; reject stale or disconnected code nodes. |
| Owning-design behavior | Explain provider reservation over serialized nested production MCP and real validator work, immutable tested-SHA publication, fresh independent original-obligation postcheck, timeout/legacy exhaustion, approved correction/extension, lost response and restart. Verify source contract, pinned local render, browser Context→Containers→Components→Code, Level up, deep links and pinned source; record measured reuse and gaps, without a universal latency claim. |

## Files likely touched

Real-process recovery journey tests; production queue/role/tool/validation adapters where the journey exposes gaps; affected DESIGN.md files and architecture model.dsl/views.dsl/workspace.contract.json.

## Implementation notes

Build deterministic integration harness through production worker/watchdog queue, durable checkpoints, actual role-scoped tool dispatch, Task test/commit/delivery, owner validation/publication and independent remote/postcondition inspection. Script only external paid-provider and forge transport. Use temporary repositories, bare remote, real validator processes, true red checks and process-group timeout cleanup. First prove one admitted incident repaired via owner tools and resolved only by fresh authoritative postcheck; assert no duplicate Task/review/worker/publication on repeat sweeps or competing caller. Replay unchanged timeout + legacy exhausted next-decision through restart, approved policy correction and authorized extension when necessary; preserve old attempts/decisions. Unavailable policy owner must wait with named next action. Architecture: reconcile Agent, Watchdog, Task, tier and cascade parent designs with sequence, persistence and restart; update cascade-agent-code, cascade-watchdog-code, cascade-teams-code, affected tier code views and component views for actual symbols. Verify context/containers remain accurate, source contract/local render and browser navigation/deep links/pinned source.

## Skills

_(none)_

## Test plan

Run the positive real-process journey, timeout/restart replay, legacy decision and unavailable-owner variant. Count effects independently and verify architecture source/render/navigation.

## Out of scope

Dependency installation, live deployment, and F3/F4 operational or CI work.
