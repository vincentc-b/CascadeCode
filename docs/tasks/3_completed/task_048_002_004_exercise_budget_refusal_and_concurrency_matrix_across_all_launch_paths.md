---
id: task_048_002_004
title: Exercise budget, refusal and concurrency matrix across all launch paths
tier: task
status: completed
parent: feat_048_002
children: []
depends_on:
- task_048_002_003
owners:
- swe
skills: []
parent_rev: baf350f0bb4768359a16418ca9fd8ee2dcfed981
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Exercise budget, refusal and concurrency matrix across all launch paths

## Parent Feature

[feat_048_002](../../features/2_active/feat_048_002_execute_and_independently_verify_the_bounded_owner_agent_repair_journey.md)

## Depends on

- task_048_002_003

## Acceptance criteria

- Expand the established real harness to direct/manual/periodic/audit/briefing/provider-switch/parent/replacement-action entry points. Independently count physical model and validator invocations, charged/settled receipts and remote effects. Verify unchanged deterministic failure takes one costly attempt; transient cap, concurrent reservation, restart/new generation/cosmetic revision/policy cycle/provider switch never renew allowance; in-flight overrun/cancellation and unavailable usage charge conservatively; denied extension stays closed, authorized finite extension retains prior use; exhausted incident gets one escalation while unrelated work proceeds. Exercise red checks, malformed policy, head/policy drift, stale admission, remote races, dirty work, live owner, wrong scope, missing tools and denied gates. Verify stage and budget projection truthfulness without dashboard redesign.
- Architecture: close out affected Agent/Watchdog/Task/parent/tier/War Room designs, reconcile cascade-agent-code, cascade-watchdog-code, cascade-teams-code and affected tier/dashboard code views and component relationships; justify context/container no-change from final diff. Validate source contract, pinned local render, navigation/deep links/pinned source, normal and failure/restart traces; record gaps and do not rewrite accepted snapshots.

## Diagram-impact acceptance

| Level / view | Required final-diff reconciliation |
|---|---|
| `cascade-landscape`, `cascade-context`, `cascade-containers` | Confirm operator, provider, forge, worker/process and tracking-root persistence boundaries against all changed paths; update if changed or record a concrete no-change reason. |
| `cascade-supervisor-components`, `cascade-team-components`, affected CLI/War Room components | Check Task authority, Agent invocation, scoped owner, publication, Watchdog independent postcheck and projection consumers agree across both sides of each interface. |
| `cascade-agent-code`, `cascade-task-code`, `cascade-watchdog-code`, `cascade-teams-code`, affected Epic/Feature and dashboard/War Room Code views | Verify real changed symbols, native declaration kinds, `cascade.parent` ownership, source paths/symbols, model.dsl/views.dsl/workspace.contract.json consistency and no stale links. Only change dashboard views if producer/consumer interface changed. |
| Owning-design behavior and browser navigation | Trace normal journey plus refusal, timeout/cancellation, unknown usage, competing caller, exhausted audit deduplication, extension and restart from source. Verify source contract, pinned local render, Context→Containers→Components→Code, Level up, deep links and pinned source. Measure warm reuse and record actual evidence/gaps; do not rewrite accepted snapshots. |

## Files likely touched

Recovery journey and budget matrix tests; production routes where matrix exposes gaps; affected DESIGN.md files and architecture model.dsl/views.dsl/workspace.contract.json.

## Implementation notes

Expand the established real harness to direct/manual/periodic/audit/briefing/provider-switch/parent/replacement-action entry points. Independently count physical model and validator invocations, charged/settled receipts and remote effects. Verify unchanged deterministic failure takes one costly attempt; transient cap, concurrent reservation, restart/new generation/cosmetic revision/policy cycle/provider switch never renew allowance; in-flight overrun/cancellation and unavailable usage charge conservatively; denied extension stays closed, authorized finite extension retains prior use; exhausted incident gets one escalation while unrelated work proceeds. Exercise red checks, malformed policy, head/policy drift, stale admission, remote races, dirty work, live owner, wrong scope, missing tools and denied gates. Verify stage and budget projection truthfulness without dashboard redesign. Architecture: close out affected Agent/Watchdog/Task/parent/tier/War Room designs, reconcile cascade-agent-code, cascade-watchdog-code, cascade-teams-code and affected tier/dashboard code views and component relationships; justify context/container no-change from final diff. Validate source contract, pinned local render, navigation/deep links/pinned source, normal and failure/restart traces; record gaps and do not rewrite accepted snapshots.

## Skills

_(none)_

## Test plan

Run bounded negative and concurrency matrix against the positive journey; count physical processes, model calls and retained charges independently. Verify source contract, pinned render and browser navigation.

## Out of scope

Dependency installation, live deployment, and F3/F4 operational or CI work.
