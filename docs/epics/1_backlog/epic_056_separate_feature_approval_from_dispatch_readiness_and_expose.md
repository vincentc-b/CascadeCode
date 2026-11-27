---
id: epic_056
title: Separate Feature approval from dispatch readiness and expose refusal reasons
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
# Separate Feature approval from dispatch readiness and expose refusal reasons

## Intent

An operator attempting to approve feat_051_006 while its prerequisite feat_051_005 was still running received HTTP 409 dependency_unmet; the card reverted to Needs approval with no persistent actionable explanation. Epic 020 originally promised a durable approval independent of dependency, sibling, review and merge dispatch blockers. Restore the explicit distinction so a human can authorize reviewed future work without starting it prematurely, and so rejected or ambiguous actions are always visible. Coordinate with Epic 045 readiness explanations and Epic 039 dependency gates; no duplicate approval or execution authority.

### Success criteria

1. Distinguish human plan approval from dispatch readiness: permit explicit durable approval of the current reviewed Feature plan while an ordinary declared predecessor is incomplete, while preserving all independently required human review, dependency-manifest/software installation, provider selection and architecture approval gates. If a prerequisite is genuinely required to authorize approval rather than dispatch, refuse explicitly with the exact reason; never silently record acceptance of an unreviewed plan.
2. Keep approved work in backlog with its exact dependency, sibling, integration or review blockers. Re-evaluate only through the existing Watchdog/Boss dispatch path; never start planning or Tasks before their canonical prerequisites are met. When predecessors complete, dispatch exactly once without a second approval click. Preserve revision-bound approval evidence, idempotence, changed-plan invalidation and concurrency fences.
3. Align the board and plan-page controls with the authoritative approval boundary. Show immediate pending state, retain disabled state across polls, and distinguish approved-awaiting-prerequisite, explicit refusal and unconfirmed transport outcome. Display typed refusal explanations and blocker work IDs on the affected row, not merely in chat status, without reloading.
4. Reproduce feat_051_006 depending on active feat_051_005: approve once, verify persisted evidence across refresh/restart, prove no premature dispatch, then complete and verify the predecessor and observe exactly one dispatch. Cover late-minted approved/unapproved children, incomplete/unknown/cancelled dependencies, stale reviewed revisions, provider and architecture refusals, repeated clicks/polls, transport failure and unrelated blockers. Use production API and isolated real Git plus browser tests; retain existing approval and recovery gates.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse approvals.py, planning_action_dependencies.py, dependency_evaluation.py, Feature readiness evidence and War Room lifecycle controls. Coordinate with Epic 020, 039, 045 and 051. Separate ordinary work-item sequencing from approval-specific dependency safety only after tracing exact authority; no automatic human approvals, no gate bypass, no additional scheduler or ledger. Update owning DESIGN.md and affected C4 views, and exercise exact reviewed revision and dispatch behavior. Filing this brief authorizes no implementation or deployment.

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
