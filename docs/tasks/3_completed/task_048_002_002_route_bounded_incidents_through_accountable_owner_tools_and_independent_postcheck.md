---
id: task_048_002_002
title: Route bounded incidents through accountable owner tools and independent postcheck
tier: task
status: completed
parent: feat_048_002
children: []
depends_on:
- task_048_002_001
owners:
- swe
skills: []
parent_rev: ea2ed3191bb928d80d759f8e0e5fab6fb56f591e
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route bounded incidents through accountable owner tools and independent postcheck

## Parent Feature

[feat_048_002](../../features/2_active/feat_048_002_execute_and_independently_verify_the_bounded_owner_agent_repair_journey.md)

## Depends on

- task_048_002_001

## Acceptance criteria

- Connect watchdog queue, audit investigation outbox, parent supervision, tier role catalogs, approved validation profiles, owner repair and publication. Emit durable detected/admitted/assigned/executing/validating/publishing/verifying/resolved/waiting receipts bound to actor, capability, permitted inputs and authority revision. Select only owner-approved command/coverage/finite-budget validation profiles; preflight feasibility. Keep human/credential/comment/scope/installation gates closed. Gate audit/manual/periodic paid commissions by F1 original incident budget; route missing capability or policy owner once to executable handoff or precise wait. Watchdog fresh postcheck alone resolves the original obligation; provider finished or push does not.
- Architecture: reconcile cascade/DESIGN.md (proposed REQ-CASCADE-RECOVERY-002 only when real), cascade/watchdog/DESIGN.md, cascade/epic/DESIGN.md, cascade/feature/DESIGN.md, cascade/task/DESIGN.md and War Room design if projection changes. Update cascade-watchdog-code, cascade-teams-code and affected epic/feature/task/dashboard code views and component relationships; context/containers justified. Include normal and unavailable-owner/restart flows, persistence and isolation limits; validate model/contract/render/navigation/source links.

## Diagram-impact acceptance

| Level / view | Required source-linked reconciliation |
|---|---|
| Landscape `cascade-landscape`, context `cascade-context` | Check actual owner, operator, provider and forge relationships against the diff; record a concrete no-change reason if unchanged. |
| Container `cascade-containers` | Show the existing worker/tool processes and tracking-root F1 sidecar; explain native shell and process limits without implying OS isolation. |
| Component `cascade-supervisor-components`, `cascade-team-components`; affected CLI/War Room components | Show Watchdog queue/audit, Task budget admission, scoped owner tools, publication and independent postcheck with one owning design per contract. |
| Code `cascade-watchdog-code`, `cascade-teams-code`, affected `cascade-epic-code`, `cascade-feature-code`, `cascade-task-code` and projection views only if interfaces change | Reconcile `dispatch_audit_recovery`, `request_investigation`, `replay_pending_investigations`, `reconcile_parent_lifecycle_incident`, `verify_incident_postcheck` and changed tier symbols with real declaration kinds and pinned source in model.dsl, views.dsl, workspace.contract.json. |
| Behavior in `cascade/watchdog/DESIGN.md`, `cascade/DESIGN.md` and affected child designs | Trace admitted repair to real owner, approved profile, durable stage, publication and fresh postcheck; trace missing owner, exhaustion and restart. State persistence, authority and non-isolation limits. Verify source contract, local render, Context→Containers→Components→Code, Level up, deep links and source opening; record actual checks/gaps. |

## Files likely touched

cascade/watchdog/{audit_investigation.py,audit_recovery.py,incident_postcheck.py}; cascade/{epic,feature,task} scoped tools; cascade/{team_review_recovery.py,review_validation.py}; owning DESIGN.md files; architecture model.dsl/views.dsl/workspace.contract.json.

## Implementation notes

Connect watchdog queue, audit investigation outbox, parent supervision, tier role catalogs, approved validation profiles, owner repair and publication. Emit durable detected/admitted/assigned/executing/validating/publishing/verifying/resolved/waiting receipts bound to actor, capability, permitted inputs and authority revision. Select only owner-approved command/coverage/finite-budget validation profiles; preflight feasibility. Keep human/credential/comment/scope/installation gates closed. Gate audit/manual/periodic paid commissions by F1 original incident budget; route missing capability or policy owner once to executable handoff or precise wait. Watchdog fresh postcheck alone resolves the original obligation; provider finished or push does not. Architecture: reconcile cascade/DESIGN.md (proposed REQ-CASCADE-RECOVERY-002 only when real), cascade/watchdog/DESIGN.md, cascade/epic/DESIGN.md, cascade/feature/DESIGN.md, cascade/task/DESIGN.md and War Room design if projection changes. Update cascade-watchdog-code, cascade-teams-code and affected epic/feature/task/dashboard code views and component relationships; context/containers justified. Include normal and unavailable-owner/restart flows, persistence and isolation limits; validate model/contract/render/navigation/source links.

## Skills

_(none)_

## Test plan

Run scoped queue/tool integration for approved and refused profiles, absent owner, exhausted audit replay, unrelated work and fresh postcheck. Verify changed architecture source, render and browser navigation.

## Out of scope

Dependency installation, live deployment, and F3/F4 operational or CI work.
