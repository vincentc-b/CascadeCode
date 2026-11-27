---
id: epic_057
title: Recover expired architecture render leases during live supervision
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Recover expired architecture render leases during live supervision

## Intent

Epic 051 repeatedly could not close despite accepted merged Features because an architecture publication remained pending with an expired render lease owned by an exited worker. The supervisor was still healthy; its publication reconciliation reread a running row indefinitely. Manual construction and reconciliation of the existing C4 scheduler recovered the pinned render and released the superseded publication hold. Restore Epic 046’s bounded interrupted-render recovery during normal live supervision, not only scheduler startup. Coordinate with the broader lifecycle convergence brief Epic 021; this brief owns only architecture render/publication recovery.

### Success criteria

1. During ordinary supervisor maintenance, deterministically detect dead or expired render worker leases and invoke the existing project-scoped scheduler reconciliation. Preserve cross-process ownership, exact pinned inputs, render identity, validated cache reuse and bounded concurrency; no duplicate render, provider turn or new scheduler. Never reclaim a demonstrably live lease.
2. Recover an interrupted render once within the existing durable automatic recovery allowance, then record explicit terminal failure and supported retry guidance if exhausted. Handle worker exit with supervisor still running, restart, timeout, corrupt/missing artifact, changed baseline or plan revision and simultaneous reconciliation. Do not renew approval or substitute current HEAD for pinned inputs.
3. Reconcile the matching architecture publication and its acceptance hold through existing ownership and revision gates. Successful validated publication can advance its exact current unit; stale/superseded or failed publication must release or transition the hold according to the existing contract and expose the actual next prerequisite. No fabricated architecture evidence or gate bypass; an accepted Feature merge alone does not authorize Epic closure.
4. Show actionable live pending/recovering/failed/superseded status and expiry/retry evidence in War Room and plan review without driving work from GET. Reproduce Epic 051 Feature 006’s accepted PR with expired renderer and demonstrate automatic verified closeout convergence without manual scheduler instantiation, restart, or agent turn. Use real pinned renderer and bounded deterministic process/lease fixtures; repeat polling and restart prove at-most-once recovery, preserved history and no premature closeout.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse cascade/workspace/c4_scheduler.py, architecture_publication.py, c4_render.py, architecture_review.py, lifecycle_review_gate.py and existing Watchdog maintenance and War Room projection. Scope to stale render/publication liveness and typed visibility; coordinate with completed Epic 046, Epic 021 convergence, Epic 049 progress and Epic 055 runtime upgrade rather than duplicating their schedulers or ledgers. Preserve exact review authority, resource bounds and human approval. Update owning DESIGN.md and C4 views against actual implementation. Filing authorizes no deployment or approval bypass.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-27 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
