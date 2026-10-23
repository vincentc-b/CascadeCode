---
id: epic_020
title: Make late-minted features visibly approvable
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
created: '2026-10-23'
updated: '2026-10-23'
provider: cursor
models:
  epic_manager: claude-opus-5-5
  epic_architect: claude-opus-5-5
---
# Make late-minted features visibly approvable

## Intent

A feature minted after its epic plan was approved correctly remains unapproved, but the War Room provides no feature-level approval control or clear waiting reason. Operators therefore see a dependency-ready backlog feature that appears stuck and must use an undocumented API to continue. Provide a complete human approval path for these features without weakening the existing approval boundary.

### Success criteria

- An unapproved backlog feature has a clear "Awaiting feature approval" state and a human-only approval action in the War Room.
- The action uses the existing durable, idempotent feature approval operation and shows pending, success, and actionable failure feedback.
- After approval, an otherwise eligible feature is scheduled automatically; an ineligible feature remains in backlog with its actual dependency, sibling, review, or merge blocker visible.
- The approval HTTP request persists approval and returns without waiting for a feature-planning model turn; kickoff runs through the normal deferred/background path.
- A browser/API integration test covers an epic approved with its initial children, a feature minted afterward, the visible approval action, one approval, and exactly one dispatch.
- Existing behavior remains explicit: approving an epic plan approves only the children present at that moment, and later features are never silently approved.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Preserve per-feature approved_at as durable authority and preserve the current snapshot semantics for epic-plan approval. Only a human may grant the missing approval. Reuse /api/approve_feature and canonical dispatch/reconciliation rather than adding a second approval store or bypass. Coordinate labels/readiness presentation with epic_015, but do not make this work depend on auto-approval or broaden epic_015's planner sign-off scope. Re-approval and refreshes must not duplicate worktrees, queue events, or model turns.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-23 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
