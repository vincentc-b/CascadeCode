---
id: task_048_001_002
title: Reserve and settle incident operations atomically
tier: task
status: completed
parent: feat_048_001
children: []
depends_on:
- task_048_001_001
owners:
- swe
skills: []
parent_rev: 5b170561e4fe97bf8457932c5b4e8da8c96ab75f
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Reserve and settle incident operations atomically

## Parent Feature

[feat_048_001](../../features/2_active/feat_048_001.md)

## Depends on

- task_048_001_001

## Acceptance criteria

- Implement reserve_incident_operation and settle_incident_operation in the Task-owned budget API, with typed admitted/pending/exhausted/owner-decision outcomes. Under task_lifecycle_lock, verify canonical lineage, policy version, material eligibility, persisted transient backoff, elapsed deadline and all cumulative remaining dimensions before a real expensive launch. Replay of one operation identity grants no extra permit; settlement is idempotent.
- One live top-level claim per incident; a nested provider/MCP/tool operation shares the parent claim but gets its own charged receipt and serialized execution. A concurrent independent caller waits. A live owner is never reclaimed from lease age alone; proven dead/uncertain in-flight work retains conservative consumption until authoritative reconciliation.
- Publish a versioned F2 consumer API: incident identity remains distinct from material generation, top-level claim and unique operation identity; every admitted operation returns a bounded permit and durable receipt. A nested provider → MCP → validator call reuses the live claim, reserves and settles a separate serialized charge, and cannot deadlock or launch unmetered work. Competing claims return pending. Return typed pending, exhausted or owner-decision refusals with reason, policy version and existing receipt; replay never mints allowance.
- Count process attempts and validator/process seconds separately from future F2 paid turns/model seconds/tokens. Store actual known use; mark estimated/unavailable honestly. Keep original start and counters through generations, restarts, policy cycles, provider switches and cosmetic revisions. Refuse ambiguous/corrupt accounting.
- Wire watchdog/incidents.py and reservations.py as consumers of the Task ledger without another spendable budget. Existing audit observation/capability claim remains distinct from the operation permit. Exhaustion coalesces one durable escalation; unrelated incidents stay eligible.
- Architecture impact: check cascade-landscape/context and cascade-containers for unchanged external/runtime boundaries with concrete reason; update cascade-supervisor-components, cascade-task-code, cascade-watchdog-code and cascade/task/DESIGN.md, cascade/watchdog/DESIGN.md, cascade/DESIGN.md for actual reserve/settle relationships, source-linked Function kinds, normal/crash/restart/extension flows, persistence and local process isolation. Reconcile model.dsl, views.dsl, workspace.contract.json together when structure changes; verify source contract, local render, context→container→component→Code, Level up, deep link and pinned source. Record evidence/gaps in closeout.

## Files likely touched

`cascade/task/incident_budget.py`, `cascade/watchdog/incidents.py`, `cascade/watchdog/reservations.py`, owning Task/Watchdog/package designs and the pinned architecture model/views/contract as the actual diff requires.

## Implementation notes

Use the Task-owned budget record and lifecycle lock defined in the parent feature. F2 owns paid provider enforcement.

## Skills

_(none)_

## Test plan

use temporary real tracking/product roots and at least two processes to prove no overspend, exactly-once settlement, concurrent waiting, live-owner protection, crash/unknown charge retention, elapsed-time preservation and nested claim charging. Avoid a mock-only accounting test. No provider-turn enforcement or unrelated action refactor.

## Out of scope

Provider paid-turn enforcement, live deployment and unrelated action refactors.
