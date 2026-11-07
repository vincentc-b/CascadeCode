---
id: epic_040
title: Rearm materially revised blocked Tasks
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
created: '2026-11-07'
updated: '2026-11-07'
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

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Build on revise_task, recovery_status, retry_task, dispatch_task, Task execution leases, direct-report blockage projection, and existing Task path guards. Do not reset attempt history, grant broader filesystem access, mark a Task complete without a deliverable commit, or allow a parent to mutate another team's Task. A changed Task body or metadata must not itself be enough: the supervised operation must compare durable revisions and recheck all dispatch invariants.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-07 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
