---
id: epic_051
title: Keep feature teams accountable through review merge and repair
tier: epic
status: active
parent: null
children:
- feat_051_001
- feat_051_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-25'
updated: '2026-11-26'
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
# Keep feature teams accountable through review merge and repair

## Intent

A Feature Team owns delivery until its existing integration merge request is verified merged into the owning Epic, not merely until Tasks finish or a PR opens. Epic 048 exposed the gap: feat_048_001 was marked completed while PR #251 remained open with a failing Recovery contract check. Epic recover_feature returned pending_feature_result/durable_result=false; its queued messages could not wake the completed Feature because queue delivery accepts only active teams or teams with a pending durable recovery action. The Feature was unable to initiate the repair it was asked to perform, and downstream task_048_004_003 repeatedly failed the same test. Make review ownership actionable through the ordinary team lifecycle, including existing conflict checks and review-health monitoring, without requiring a human to edit branches or bypass CI.

### Success criteria

1. Distinguish implementation complete, review pending, repair requested/in progress, verified merged, and terminal close/cancel states. Keep the same Feature owner, branch, PR, checkpoints and worktree available while review is open; only retire after independently verified merge into the intended target (or supported terminal disposition). Idle review-pending teams must be wakeable, not continuously burning model tokens.
2. Extend the existing review-health supervision path to observe fresh source/target heads, mergeability/conflicts, required CI check failures/pending/unknown, and actionable review feedback. Route conflicts and fixable red checks to the owning Feature Team; distinguish expected pending checks, transient forge outages, and human-only approvals. A failing required check cannot be deemed healthy or bypassed.
3. Accept scoped human and direct-parent fix requests against an open Feature review even if implementation is recorded complete. Admit a durable request/repair generation before scheduling a wakeup; the owning Feature may use its normal guarded Task mint/dispatch and review publication tools. Keep original review identity and repair history, scope and approval boundaries, budget, claims, and one writer. Return typed acknowledgement, admission, execution, refusal and verified outcome, not merely queued success. A completed legacy Feature with an unmerged PR must have a supported reconciliation route.
4. Deduplicate repeated observations and requests, fence stale heads and concurrent workers, preserve recovery/CI evidence across restart, and retry only on appropriate evidence within finite budget. Avoid redispatch loops on downstream tasks whose only blocker is unchanged upstream CI. Reconcile the exact corrected head, required checks and merge disposition independently; preserve review comments and do not force-merge or override protections.
5. War Room exposes the open PR URL, accountable team, review/check status, repair request and next prerequisite; distinguish awaiting review from inactive/terminal. Use existing review state and transcript mechanisms; do not wake teams from a GET/UI poll.
6. Acceptance: reproduce the PR #251 scenario with an implementation-complete Feature and open red CI, parent fix request, durable admitted task/repair on the existing branch, check rerun green, verified merge and only then retirement. Exercise conflict/target movement, review feedback, stale/duplicate requests, restart between admission and wakeup, concurrent repair, missing forge data, required human approval, cancellation and legacy completed-but-open review. Use real temporary Git repositories and normal production adapters, with scripted forge/check transport where required. Prove no extra PR, no approval bypass, no paid turns on unchanged idle checks, and no downstream rerun storm.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Build on current review_health, tracking/forge snapshots, team_supervision/recover_feature, workspace kickoff and queue delivery, Feature repair/closeout, existing durable action and incident budgets, and Watchdog independent postchecks. Coordinate with Epic 048's recovery contracts and Epic 049's visibility work; do not duplicate schedulers, ledgers or review UI. Preserve exact review/branch authority and the human merge policy; no live deployment or installation is authorized by filing the brief. Keep the brief in backlog for normal approval. Reconcile owning DESIGN.md and affected architecture views with implemented behavior.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_051_002
- feat_051_001

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-25 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
