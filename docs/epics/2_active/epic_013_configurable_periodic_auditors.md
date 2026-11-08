---
id: epic_013
title: Configurable periodic health audits and recovery
tier: epic
status: active
parent: null
children:
- feat_013_001
- feat_013_002
- feat_013_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-11-08'
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
# Configurable periodic health audits and recovery

## Intent
Run a periodic, configurable health audit across Cascade Tasks, Features, and Epics. The auditor evaluates authoritative lifecycle, execution, Git/worktree, dependency, approval, queue, review, and recovery state. Healthy work produces no mutation, event, chat turn, or notification. Unhealthy work is repaired through the same guarded lifecycle capabilities used by its owning team. The auditor agent receives the least privilege necessary to resolve proven incidents, preserves active work and human approval boundaries, and escalates only when safe automated recovery cannot be established.

### Success criteria
1. Add a documented `[automation.health_audit]` section to `cascade.toml`. Auditing is enabled by default with `interval = "30m"`; operators can change the interval or disable it explicitly. Parse duration values strictly, enforce safe minimum/maximum bounds, and preserve backward compatibility for existing configuration.
2. Run at most one audit per workspace at a time. Use monotonic scheduling, bounded jitter, restart-safe last-run state, and coalescing so restarts or slow audits do not create a catch-up storm.
3. Inspect every nonterminal Task, Feature, and Epic through canonical board and lifecycle projections. Also inspect recently completed work when reconciliation, pending review, publication, or cleanup state can still be incomplete.
4. Task health covers owner lease/heartbeat, execution phase, checkpoint, pinned inputs, branch/worktree state, dirty changes, test/validation evidence, dependency readiness, pending merge index, durable merge action, retry state, parent blockage, and completed-document rollup.
5. Feature health covers planning-team liveness, task graph consistency, dependency and approval state, task integration, review publication/merge state, stale parent revisions, blocked comments, completion rollup, and dispatchable work that is making no progress.
6. Epic health covers planning-team liveness, authoritative dependencies, sign-offs and plan approval, feature graph/sequence, integration branch/worktree, review/closeout state, return/cancellation transitions, and discrepancies between trunk pointers and integration copies.
7. A healthy audit is silent and write-free: no model turn, queue event, toast, chat message, timestamp rewrite, Git commit, or external API call solely to say that health is good. Metrics may be updated only through an explicitly documented low-cost observability path that cannot trigger work.
8. Derive stable, deduplicated incident identities from work ID, observed generation/revision, and failure class. Recheck under the appropriate lifecycle lock immediately before repair; if the incident disappeared, perform no mutation.
9. Grant the auditor a named, scoped recovery role with the capabilities needed for proven repairs. It may requeue a validated delivery missing from the pending index, reclaim a stale execution lease, resume an orphaned turn from pinned state, retry transient durable actions, reconcile lifecycle documents, restore safe dispatch, complete idempotent rollups, and invoke existing team-owned conflict recovery.
10. Auditor authority never bypasses human plan/feature approval, comment gates, credentials, license acceptance, provider changes, destructive Git decisions, system dependency installation, or ambiguous semantic conflict resolution. Those cases become durable human/team incidents with exact evidence and a resume action.
11. Prefer deterministic code-level checks and repairs. Start an auditor agent only when an unhealthy incident requires bounded diagnosis or an authorized recovery plan. Supply the incident evidence and only the tools/paths relevant to that work item; do not grant arbitrary repository mutation.
12. Repairs are idempotent, attempt-bounded, and crash/restart safe. Persist attempt history, classification, owning team, evidence, next retry/cooldown, and final outcome. Repeated audits converge without duplicating merges, dispatches, reviews, agent turns, or notifications.
13. Use hierarchical escalation: a Task incident first routes to its Feature Team, a Feature incident to its Epic Team, and an Epic/system incident to the human or Boss as appropriate. The auditor may perform a safe repair directly but records which owning team would otherwise be accountable.
14. Expose last audit time, next due time, duration, counts by tier/outcome, and active incidents in the War Room. Provide a guarded human “Run health audit now” action without changing the configured schedule.
15. Prevent audit self-harm: cap work per pass, avoid holding global locks during providers/network/Git operations, respect canonical lock ordering, and surface an auditor failure without blocking unrelated delivery.
16. Regression-test the `task_038_002_002` failure: a validated Task whose merge action is `retryable` but whose ID vanished from `pending-task-merges.json` must be detected, requeued through the canonical merge path, merged exactly once, rolled up to completed, and release dependent work.
17. Cover stale-but-live owners, missing checkpoints, dirty worktrees, merge conflicts, busy targets, stale validation evidence, approval/comment gates, orphaned Feature/Epic planning turns, split-repository state, concurrent manual recovery, disabled audits, invalid intervals, restart timing, and an entirely healthy workspace.
18. Schedule health audits independently from the ordinary watchdog maintenance chain. A slow forge fetch, review poll, Git operation, or model turn cannot indefinitely delay the next audit. Bound every subprocess and network operation with explicit timeout, cancellation, and durable retry evidence.
19. Treat recovery capability as executable authority, not a label. At startup and per incident, prove the selected operation is registered, authorized for the concrete owning work ID, can reach the required worktree/action, and has a durable request/acknowledgement/result path. Missing capability is an actionable system incident, not investigating.
20. Make remediation and recovery ledgers generation-aware. claimed, error, refused, deferred, unsafe, and prior no-op rows receive bounded retry/cooldown semantics and are re-evaluated when leases, branch heads, queue membership, evidence, document revision, parent blockage, or capability availability changes. Only terminal success for the same authoritative generation is permanently suppressing.
21. Detect active Features and Epics with no live planning owner, no pending queue input, no open/pending review, dispatchable children making no progress, or completed local integration work not published for review. Provide concrete Feature-parent and Epic-parent recovery actions rather than classifying them healthy_or_not_actionable.
22. Validate repair adapters with real end-to-end mutations in isolated repositories: route to the concrete owner, wake it, acknowledge, modify only the owned branch, run work-defined supervised checks, publish replacement evidence, clear only matching derived blockers, resume the original action, and reach terminal completion exactly once. Event-only and mocked-callback tests do not satisfy recovery acceptance.
23. Verify recovery identity fields by type and authority. Work IDs, document revisions, commit SHAs, branch names, and incident generations are not interchangeable; specifically cover the orphan-resume regression where a Task parent revision was passed as its Feature ID.
24. Incorporate the executable capabilities delivered by the stale-delivery and child-ownership recovery epics rather than duplicating them. Until a required capability exists, escalate that precise missing capability and retain the incident for later automatic re-evaluation.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Extend the existing supervisor health projection, direct-report health sweep, durable action recovery, orphan-delivery recovery, lifecycle locks, and reconciliation commands instead of adding a parallel scheduler or status database. Treat board metadata, durable actions, execution leases, registered worktrees, and forge review state as authoritative according to their existing ownership boundaries. Separate observation from mutation and require a locked recheck before every repair. Agent rights must be capability-based, incident-scoped, auditable, and no broader than the owning team’s safe recovery authority. Preserve user changes, dirty worktrees, accepted history, and human decisions. Run observation in a supervisor-owned lane independent of ordinary advancement/review polling, with bounded I/O and no global lock held across network, provider, test, or Git subprocesses. A recovery adapter is eligible only when its concrete operation and owner routing are registered and testable.

## Core dependencies

Build on the existing supervisor health projection, direct-report health sweep, orphan-delivery recovery, durable action recovery, lifecycle locks, board reconciliation, War Room recovery surfaces, and `cascade.toml` automation configuration. Consume the executable capabilities delivered by the stale Task delivery and parent-owned child recovery epics.

## Feature breakdown
- feat_013_003
- feat_013_002
- feat_013_001

The Epic Team will create and sequence feature plans here. Treat the task/feature/epic health model, independent scheduler, generation-aware incident ledger, and capability boundary as shared foundations before adding repair adapters or UI controls.

## Open questions

- Which existing recovery capabilities are complete enough to expose directly to the auditor, and which require a fail-closed human escalation until repaired?
- What bounded recent-completion window best catches incomplete rollups without rescanning the full completed board every pass?
- Which repair adapters must land before the auditor can be enabled by default without producing non-actionable incidents?

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-11-06 · Human amendment · Make the auditor a configurable health-and-recovery loop for Tasks, Features, and Epics; default to every 30 minutes, remain silent when healthy, and grant incident-scoped repair capabilities when unhealthy.
- 2026-11-07 · Human amendment · Require independent bounded scheduling, executable owner-scoped capabilities, generation-aware retries, and end-to-end proof of actual recovery mutations.

## Amendment log

- 2026-11-06 · Reframed periodic auditors from advisory repository analysis into authoritative lifecycle health detection and bounded recovery. Added the lost merge-queue entry from `task_038_002_002` as a required regression scenario.
- 2026-11-07 · Strengthened the auditor after repeated manual recovery of Tasks 037_002_004, 037_002_005, 037_003_002, and 037_003_005. Added independent execution, retryable negative outcomes, concrete ownership/capability checks, all-tier no-progress detection, and real mutation acceptance tests. Removed duplicated generated brief sections.
