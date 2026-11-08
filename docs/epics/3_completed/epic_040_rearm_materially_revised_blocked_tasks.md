---
id: epic_040
title: Rearm materially revised blocked Tasks
tier: epic
status: completed
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-07'
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
# Rearm materially revised blocked Tasks

## Intent

Let an owning Feature Team safely continue a blocked child Task after the parent materially revises its contract to remove a deterministic scope or sandbox blocker. Preserve the failed attempts and worktree evidence, create a new bounded recovery generation tied to the revised Task revision, and avoid unchanged retries that cannot succeed.

### Success criteria

1. Detect Task contracts whose only requested deliverables are under Task-denied paths before dispatch, and return a structured scope blocker to the Feature Team.
2. Classify Task-tool write-denied and commit-path refusals as deterministic scope or permission blockers rather than retryable infrastructure.
3. When revise_task materially changes a blocked Task, record the old and new Task revisions and permit exactly one supervised dispatch generation for the new contract without erasing prior attempt history.
4. Reject duplicate revision and dispatch requests idempotently across restarts and concurrent parent or supervisor actions.
5. Recheck Task ownership, status, execution lease, worktree cleanliness, parent revision, allowed paths, and dependency readiness under the normal dispatch lock before starting the revised Task.
6. Surface the selected recovery, revision evidence, attempt history, and current outcome to the parent team and War Room.
7. Cover the task_037_001_001 scenario: an original docs/features-only contract fails once, the Feature Team records the prose contract and revises the Task to an authorized source/test deliverable, and one new execution completes without widening Task guards or manually editing execution state.

## Macro-architecture

Implemented through the existing supervised lifecycle, durable recovery actions, owned worktrees, and validation gates. See final delivery below.

## Cross-module constraints

Build on revise_task, recovery_status, retry_task, dispatch_task, Task execution leases, direct-report blockage projection, and existing Task path guards. Do not reset attempt history, grant broader filesystem access, mark a Task complete without a deliverable commit, or allow a parent to mutate another team's Task. A changed Task body or metadata must not itself be enough: the supervised operation must compare durable revisions and recheck all dispatch invariants.

## Core dependencies

Uses existing project infrastructure; no new external package or installation.

## Feature breakdown

Delivered directly on main under the operator request. No synthetic child plans or review records are created.

## Open questions

None outstanding for this brief; the earlier audit gaps are resolved by the final delivery below.

## Decision log

- 2026-11-07 · Human · Brief approved through merge request review.

## Amendment log

_(none)_

## Implementation audit · 2026-11-08

Status: open; partial implementation in `b55abca2`. The prior blanket completion claim is withdrawn. No acceptance criteria are waived.

- Revision history, guarded-path classification, lifecycle serialization, and one-generation dispatch are implemented.
- A changed body hash currently counts as material revision. Criterion 3 and the cross-module constraint still require proving that the revised contract addresses the blocker; cosmetic edits must not independently authorize recovery.
- Criterion 5 still needs an explicit safe-worktree dispatch check and negative coverage.
- Criterion 7 still needs the complete scope-blocker → authorized revision → successful delivery acceptance sequence; the current regression proves dispatch and preserved history only.

## Final direct delivery · 2026-11-08

Status: completed. Implementation through `a37f05ff` and preceding commits supersedes the earlier partial-completion audit. The operator explicitly requested implementation directly on main because the affected tool could not reliably implement its own repairs. No acceptance criteria are waived.

All acceptance criteria are implemented. Contract revision records now include normalized deliverable evidence, not just a changed body hash. Scope failures require changed authorized deliverables; cosmetic edits and external credential refusals do not buy another attempt. Prepared revision intent precedes the document commit, so restart can recover an interrupted write without duplicate dispatch. Normal dispatch rechecks ownership, lease, dependencies, parent pin and the existing branch/worktree. Scoped unfinished source work is preserved for the owning Task; protected-path changes remain refused with actionable evidence. The Task guards are unchanged.

Acceptance crosses a real denied planning-file write, deterministic failure, parent-owned prose revision, one supervised Task turn, source/test commits, exact-head validation, and one normal merge. Separate cases prove duplicate/concurrent retry refusal, failure-history retention, root-level source deliverables, external-permission refusal, dirty scoped-work preservation, protected-path refusal, and fresh-process recovery after interruption between the document and receipt writes. See `tests/test_task_recovery_generations_regressions.py` and `tests/feature/test_recovery.py`.

Validation: the combined affected acceptance suite passed 164 tests; additional targeted crash, failure, and cross-process checks passed. This records scoped acceptance, not a claim that every unrelated repository test passes.
