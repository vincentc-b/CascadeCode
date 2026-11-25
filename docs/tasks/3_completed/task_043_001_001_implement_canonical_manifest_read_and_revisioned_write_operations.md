---
id: task_043_001_001
title: Implement canonical manifest read and revisioned write operations
tier: task
status: completed
parent: feat_043_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: f5c6bc7da4ff2f06344db500e9a7ffae1f3557b5
created: '2026-11-07'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Implement canonical manifest read and revisioned write operations

## Parent Feature

[feat_043_001](../../features/2_active/feat_043_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the Epic-scoped read/write service over `cascade.epic.dependency_manifests` without a new sidecar format. Read returns the canonical snapshot and revision, or explicit missing/revision 0. Write accepts only an exact public request shape and a non-negative integer `expected_revision` (reject bool, absent, negative, fractional, string). Validate raw current-schema identity keys for the top-level target, every dependency target, and non-null actual environment before legacy defaults; accept null actual environment, independent entry targets, explicit `none_required=true` with empty dependencies, and valid canonical entries. Reject malformed/incomplete/duplicate declarations before mutation. Under the canonical `dependency_state_lock`, check revision before content equality; current identical content is a no-op, stale replay fails, and changed content appends through the canonical writer. Return JSON-safe persisted snapshot, `manifest_revision`, and fresh canonical software/bootstrap and plan-readiness projections under that same lock. No install or approval action. Add focused service-level tests only where needed; leave full planning-dispatcher tests to the final task.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.

## Final direct delivery · 2026-11-08

Status: completed. Implementation through `a37f05ff` and preceding commits supersedes the earlier partial-completion audit. The operator explicitly requested implementation directly on main because the affected tool could not reliably implement its own repairs. No acceptance criteria are waived.

This existing child plan is satisfied by the Epic 43 implementation delivered directly on main. Its scope, requirements and accepted history are preserved; completion records the operator-authorized direct delivery, not a fabricated Task merge or forge review. The Epic 43 final-delivery section maps the acceptance evidence.

Validation: the combined affected acceptance suite passed 164 tests; additional targeted crash, failure, and cross-process checks passed. This records scoped acceptance, not a claim that every unrelated repository test passes.
