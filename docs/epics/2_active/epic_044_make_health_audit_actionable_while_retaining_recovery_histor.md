---
id: epic_044
title: Make health audit actionable while retaining recovery history
tier: epic
status: active
parent: null
children:
- feat_044_001
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-10'
updated: '2026-11-10'
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
# Make health audit actionable while retaining recovery history

## Intent

Make the War Room Health audit explain what needs attention now, what has not been verified, and what happened previously. Preserve useful forensic history without presenting historical failed attempts or dashboard read-budget exhaustion as a wall of current failures.

### Observed problem and reproduction

On 2026-11-10, GET /api/health/audit returned 46 unavailable-evidence entries and zero active incidents: one TimeoutExpired, 39 entries saying the lifecycle recheck exceeded its bounded budget, and six entries lacking incident identity. These counts are a diagnostic snapshot, not constants to encode.

The first entry was action_recovery:epic_012:health_reservation:c872441723104722b4a56909. Its durable record describes a November 9 publication attempt rejected with PermissionError: dirty Epic worktree requires its owner. The dashboard warning is a failure to establish its CURRENT state, not a new publication failure. Do not assume that historical failure is still active or resolved.

cascade/war_room/audit_status.py scans non-success incident records from executions.json, orphan_delivery_recoveries.json and remediation_dispositions.json. It reprojects current lifecycle evidence inline under a shared two-second budget, starting at the same ledger order each response. The first historical item can consume the budget; subsequent records generate separate warnings. project_audit_observation rebuilds merged board/worktree evidence. cascade/war_room/static/war_room.js polls the route every five seconds while visible, repeating expensive work and noise. Six older remediation incident records in this snapshot lack the work_id/authoritative_generation/failure_class identity expected by the projection. Diagnose their actual schema before proposing migration.

### What must be retained

Keep durable recovery attempts, outcomes, timestamps, owners, original evidence, incident/generation identities, refusal/error reasons, requests and acknowledgements, repair references, and relevant agent investigation findings. They support forensic diagnosis, accountability, and detection of recurring bugs. Preserve genuine current failures and incomplete audit coverage. Keep existing deterministic recovery and broad owner-agent investigations; this work improves observation, prioritization and presentation, not their authority.

### Desired operator experience

Current problems: compact, actionable entries backed by current evidence, identifying affected work, owner, impact, last check, and next action. Audit coverage: a concise summary of stale, pending or failed verification, with expandable details. History: collapsed by default, searchable/filterable and paginated, showing previous failures and recovery attempts with clear timestamps and lifecycle labels. Do not call an unverified item resolved, and do not call a previous failure current without fresh evidence.

### Success criteria

1. Define an explicit projection contract separating current verified incidents, verification pending/unavailable/stale, and historical attempts. Document how an incident becomes current, superseded, resolved or unknown. Age alone, completed parent status, a delivered message, an adapter acknowledgement or an agent saying reported_fixed is not resolution evidence. Completed work may still have publication or integration obligations.
2. Remove expensive lifecycle/Git/worktree/provider probes from the dashboard GET path. Serve bounded, read-only snapshots with observation time, evidence generation, freshness and verification status. Missing state must render as unknown/pending and must not create or mutate audit records merely because the dashboard is viewed. Retain correct product/tracking root routing.
3. Run bounded reassessment in the background with persistent fair rotation, prioritizing ongoing work without permanently starving historical unresolved work. One slow or malformed item must not consume all checks or block other owners. Share read-only board evidence within a pass where safe. Persist pending coverage across restarts, coalesce duplicate work, and prevent overlapping polls or multiple browsers from creating repeated scans or recovery actions. Honor configured cadence and manual audit semantics.
4. Keep authoritative fresh-generation checks at every repair/admission boundary. A cached UI snapshot must never authorize recovery or permit an obsolete-generation repair. Changed, deleted, retired or rerouted work must become explicitly pending/unknown or be reclassified using authoritative evidence; it must not disappear as implicitly healthy.
5. Replace the wall of repeated budget warnings with one coverage summary containing counts, scope, last attempted/successful verification and next scheduled attempt. Expand details on demand, grouping repeated work IDs or failure causes while retaining links to individual records and exact identities. Distinguish actual evidence corruption, scan timeout and work deferred because the pass budget was exhausted.
6. When verification is incomplete, label an empty current-incident list as no VERIFIED current incidents plus incomplete coverage, rather than implying a clean bill of health. A genuine newly verified blocker must remain prominent even when many historical records cannot be checked.
7. Provide collapsed, bounded/paginated history with filters for work ID, owner, outcome and time as appropriate. Show when a failure occurred versus when it was last checked. Preserve raw durable history and stable references; no deletion/reset merely to reduce warning counts. Any later retention/compaction policy requires a separate explicit decision.
8. Handle legacy remediation incident schemas deliberately. Reconstruct identity only from unambiguous durable evidence and preserve the original record with provenance if migration is chosen. Otherwise classify the record as historical/unverifiable with a clear explanation, grouped in history or coverage, rather than emitting a misleading active incident or repeated generic warning. Malformed records must not prevent readable records from rendering.
9. Integrate existing agent investigation findings and follow-up state without presenting request delivery or reported_fixed as verified resolution. Give agents actionable suspicious evidence, but coalesce recurring dashboard/coverage failures so a five-second UI poll cannot create an agent-message storm. Preserve owner coordination, human installation/approval gates and existing repair/review workflows.
10. Add regressions reproducing the observed pattern with multiple historical failures, a slow first item, a new current blocker later in the set, repeated generations for one work item, legacy incomplete records and completed work with outstanding publication. Prove fair eventual reassessment, useful results after one timeout, truthful zero-incident wording, stable history retention and no repeated repair side effects.
11. Test repeated concurrent GETs, multiple browser refreshes, worker restart, manual audit, stale/corrupt/missing snapshots and split tracking/product roots. Assert the GET path invokes no lifecycle/Git/provider probes, performs bounded reads and does not mutate runtime state. Check accessible, readable UI states and expanded details. Define and demonstrate response/work budgets on a representative large historical ledger rather than only a tiny fixture.
12. Validate in the live War Room: the current historical-warning wall is replaced by a coverage summary and retained expandable history; ongoing work remains visible; repeated refreshes do not re-run full history checks; fresh authoritative incidents still trigger the existing recovery/investigation paths. Record evidence and limitations without claiming unverified historical problems were fixed.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use Codex as this epic's default provider and carry its explicit role model/reasoning settings to descendants. Do not change the workspace-wide provider default as part of this brief.

Implement through the normal Epic/Feature/Task team and review workflow. Keep this brief in backlog until normal approval/activation. Do not implement feature requirements as part of filing it.

Preserve ledger evidence and worktree contents. Do not clear blocked work, bypass approval gates, weaken fresh-generation repair checks, or mark old records successful to improve dashboard appearance. Do not include credentials, raw provider prompts or hidden reasoning in snapshots, UI or investigation reports. Maintain bounded regular-file reads and safe handling of malformed runtime data.

Likely code areas: cascade/war_room/audit_status.py; static/audit_status_ui.js and war_room.js; cascade/watchdog/audit.py, audit_lane.py, audit_agent_lane.py and audit_investigation.py; existing recovery stores and tests/war_room and tests/watchdog. Reuse existing scheduler and durable investigation machinery where suitable. Document requirements interpretation, schema compatibility, freshness choices, budgets and validation in design records and commit messages.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_044_001

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-10 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
