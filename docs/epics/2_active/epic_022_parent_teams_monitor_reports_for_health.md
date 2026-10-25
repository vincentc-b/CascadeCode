---
id: epic_022
title: Parent teams monitor reports for health
tier: epic
status: active
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-23'
updated: '2026-10-25'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Parent teams monitor reports for health

## Intent

Prevent blocked work from becoming invisible. Every supervising team must regularly inspect the health of its direct reports, attempt an appropriate recovery when a report needs help, and surface an unresolved child blockage in the supervisor’s own state so the condition propagates up the work hierarchy.

### Success criteria

- While a supervisory team is active, it periodically inspects the current state of each direct report (epics inspect features; features inspect tasks).
- Healthy, completed, cancelled, or otherwise non-actionable reports do not trigger recovery work.
- When a report is stuck or blocked, the supervisor receives enough current context to diagnose it and makes a bounded recovery attempt using existing, role-authorized operations.
- A successful recovery is reflected in the report’s persisted state and the supervisor continues normal monitoring.
- If the supervisor cannot recover the report, it persists its own blocked/stuck state with a reference to the affected report and a concise reason, making the problem visible to its own parent.
- Monitoring is idempotent: repeated checks do not create duplicate recovery actions, duplicate escalation records, or repeated state transitions for the same unchanged condition.
- Automated tests cover the end-to-end paths for healthy reports, successful recovery, unresolved blockage propagation, and recovery after the child condition clears.

## Scope

### In scope

- Supervisory relationships already represented by the Cascade epic → feature → task hierarchy.
- Periodic health checks during the existing team/orchestrator lifecycle.
- Recognition of report states that require intervention.
- A bounded remediation attempt using existing state-transition, messaging, retry, or reassignment capabilities available to the supervisor.
- Upward propagation of an unresolved blockage through existing persisted work/team status and reason fields.
- Clearing or superseding propagated blockage when the underlying report recovers, without erasing unrelated blockers.

### Out of scope

- A new general-purpose scheduler, workflow engine, or incident-management subsystem.
- Unlimited autonomous retries or bypassing existing role permissions.
- New dashboards, notifications, paging integrations, or historical analytics.
- Redefining the full work-state taxonomy.
- Automatically resolving product decisions or external dependencies that require human authority.

## Macro-architecture

1. **Observe:** Hook a lightweight health sweep into the existing periodic supervisor/team loop. At each eligible interval, load the supervisor’s direct reports through the canonical work graph and read their persisted status plus blocker context.
2. **Classify:** Map existing report states into three outcomes: no action, remediation eligible, or unresolved/propagating. Keep this mapping centralized so epic and feature supervisors behave consistently.
3. **Remediate:** For remediation-eligible reports, invoke one bounded, role-authorized recovery action through existing orchestration commands. Record the child identity and observed state/version so the same unchanged incident is not acted on repeatedly.
4. **Propagate:** If recovery cannot be performed or does not clear the condition, transition the supervisor through the canonical state API to the repository’s existing blocked/stuck equivalent. Persist structured provenance containing the child work ID and reason. Ancestor supervisors then detect that state through the same mechanism.
5. **Reconcile:** On later sweeps, clear only monitoring-derived blocker provenance whose child condition has recovered. Preserve independently created blockers and avoid reopening terminal work.

Monitoring must use persisted state as the source of truth. In-memory observations may optimize a sweep but must not become a second authoritative health model.

## Cross-module constraints

- Use the existing work graph, status enum, transition validation, and persistence paths; do not write status files directly or add a parallel hierarchy.
- Respect role and ownership boundaries. A supervisor may only take recovery actions already authorized for that role.
- The monitor must not mutate completed, cancelled, or otherwise terminal supervisors or reports.
- Polling cadence must be configurable through the existing runtime configuration pattern, with a conservative default and no busy loop.
- Concurrent sweeps and manual intervention must be safe. Re-read or compare state/version before mutation, and treat an already-applied transition as success.
- Recovery attempts must be bounded per unchanged child incident. A changed child state/version may begin a new attempt.
- Propagated blocker data must identify the originating direct report and remain machine-readable while still producing a concise human-readable reason.
- Clearing propagated state must be provenance-aware: remove the monitoring-derived cause only when it is no longer true, and never clear unrelated manual or sibling blockers.
- Failures to read or persist state must be observable through existing logging/error channels and must not be misreported as successful recovery.
- Tests should favor the supervisor-loop/state-store integration boundary; add lower-level unit tests only for classification or reconciliation logic not adequately covered there.

## Core dependencies

- Canonical work hierarchy traversal for direct children.
- Existing persisted work/team state model, blocker reason/provenance, and validated transition API.
- Existing supervisor execution loop or periodic tick facility.
- Existing role-authorized remediation primitives (for example retry/resume, message, reassignment, or escalation where supported).
- Existing integration-test fixtures for multi-level epic/feature/task graphs.

Before implementation, the feature lead must confirm the exact status names and transition rules already present in the repository. This is integration discovery, not permission to introduce a new taxonomy.

## Feature breakdown

1. **Supervisor health observation and bounded remediation**
   - Integrate configurable periodic direct-report inspection into the existing supervisor lifecycle.
   - Centralize state classification and invoke at most one eligible, role-authorized recovery action per unchanged child incident.
   - Persist or reuse minimal attempt identity needed for idempotency.
   - Demonstrate healthy/no-op, eligible recovery, terminal-report exclusion, and repeat-sweep behavior in integration tests.

2. **Unresolved blockage propagation and reconciliation**
   - When remediation is unavailable or unsuccessful, persist the supervisor’s canonical blocked/stuck state with child provenance.
   - Apply the same behavior at feature and epic levels so a task blockage can become visible through the hierarchy.
   - Reconcile monitoring-derived blockage after child recovery while retaining unrelated causes.
   - Demonstrate multi-level propagation, concurrent/manual-state safety, and recovery clearing in integration tests.

Feature 2 depends on Feature 1.

## Acceptance scenarios

- Given an active supervisor whose direct reports are healthy, repeated sweeps produce no state changes or recovery actions.
- Given a stuck direct report with an eligible recovery, one recovery action is attempted; subsequent sweeps do not duplicate it while the observed incident is unchanged.
- Given a recovery that clears the child condition, the child and supervisor remain or return to their appropriate active states.
- Given a stuck direct report that cannot be recovered, the supervisor becomes canonically blocked/stuck with the child ID and reason recorded.
- Given a blocked feature caused by a task, the epic supervisor observes the feature and propagates the unresolved condition using the same rules.
- Given a monitoring-derived supervisor blocker whose child later recovers, a subsequent sweep removes that cause; unrelated blocker causes remain intact.
- Given concurrent manual recovery or a terminal transition, the monitor does not overwrite the newer state or resurrect terminal work.
- Given a transient read/write failure, the monitor reports the failure through existing observability and retries only on a later scheduled sweep.

## Risks and mitigations

- **State-model mismatch:** Confirm existing statuses and legal transitions before coding; adapt the classifier rather than adding synonyms.
- **Retry storms:** Key bounded attempts to child identity plus observed state/version, and use a conservative configurable interval.
- **Incorrect unblock:** Store monitoring provenance and reconcile only that cause.
- **Races with humans or workers:** Use canonical transition validation and optimistic state/version checks.
- **Hierarchy-wide churn:** Inspect direct reports only; propagation through parent state keeps each sweep local and bounded.
- **Over-automation:** Limit remediation to existing authorized operations and escalate decisions requiring human authority.

## Open questions

- What are the repository’s canonical names for the intervention-required and supervisor-propagated states, and which transitions are currently legal?
- Which existing recovery primitives are safe for automatic use by each supervisor role?
- Does the current blocker representation support multiple provenance-aware causes; if not, what is the smallest compatible representation that prevents clearing unrelated blockers?

These are implementation-discovery questions for Feature 1 and must be resolved in its plan before state mutations are coded; they do not expand epic scope.

## Decision log

- 2026-10-23 · Human · Brief approved through merge request review.

- `dec_001` · 2026-10-25 · Epic Manager · **Macro-architecture**
  Chose Each supervisor inspects direct reports only; unresolved health propagates upward through the supervisor’s canonical persisted state..
  Rationale: This keeps every sweep local and bounded while naturally covering task → feature → epic chains without recursive graph scans.
  Honors: Success criteria requiring periodic hierarchical monitoring and parent state reflection..
## Amendment log

_(none)_
