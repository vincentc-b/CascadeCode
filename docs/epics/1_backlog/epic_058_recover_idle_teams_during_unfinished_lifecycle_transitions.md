---
id: epic_058
title: Recover idle teams during unfinished lifecycle transitions
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
# Recover idle teams during unfinished lifecycle transitions

## Intent

Epic 056 minted its initial two Features and the Epic Architect signed the final plan revision, but the Epic Manager never returned for final review. The team was idle, its queue drained, and Approve plan disabled for missing_epic_manager_sign_off. The health audit classified the Epic as awaiting human approval even though the human could not approve it. A manual team ping was required. Detect and recover incomplete internal handoffs automatically without waking teams legitimately waiting on users, dependencies or external reviews. Extend the existing lifecycle recovery machinery rather than introduce another scheduler.

### Success criteria

1. Configure a lightweight lifecycle-progress sweep, defaulting to a 15-minute check interval and 30-minute inactivity threshold N. Use durable meaningful progress (role turn completion, canonical revision/sign-off change, queue acknowledgement, lifecycle/action receipt, delivery progress), not poll timestamps, incidental log chatter or file touches. Persist sufficient evidence across restarts and clock changes; unknown activity is not proof of inactivity. Expose effective settings. Keep checks bounded and read-only until an actionable candidate is admitted. Make this sweep available independently of the optional expensive health audit, sharing its existing supervision and recovery authority.
2. Classify active Epics in unfinished internal transitions (initial planning/sign-off, child handoff, rollup/closeout and other supported owner recovery states) separately from stable external waits. Distinguish ready-for-human-approval from missing current Manager/Architect sign-offs; do not let generic plan_approval or child not_approved gates mask internal obligations. Initial scope is Epic owners, with reusable evidence logic for Feature recovery. Treat live or legitimately long-running owners, pending queue delivery, unresolved human decisions, provider/dependency/setup blockers, pending external reviews/checks and approved-but-prerequisite-blocked work as waits, not blind-ping candidates.
3. After the threshold, revalidate the same actionable generation and use the existing durable Epic-owner recovery route to nudge the accountable team with the exact outstanding obligation (e.g. Manager review and independent sign-off of the final Architect revision). Preserve worktree, checkpoint and role identity. Do not auto-sign, approve, dispatch, bypass gates, terminate live owners or impersonate the operator. Require one admitted nudge per unchanged generation, no overlapping writers, durable deduplication across sweeps/restarts, bounded retries/backoff and incident-wide budgets. Independently verify progress against the original obligation; accepted ping is not completion. Escalate persistent failure or ambiguous evidence with the next actionable reason rather than creating a paid-turn loop.
4. Surface last meaningful progress, inactivity age, classification, blocker/required role, last nudge/outcome, next check and actionable escalation in existing War Room recovery/status UI. Keep legitimate waits distinct from stalled internal transitions; no model calls or mutation on refresh. Preserve human plan and feature approval boundaries.
5. Reproduce Epic 056 through production paths: Architect signs final revision, Manager absent, both initial Features unapproved, queue drained and human approval disabled. Advance an injected clock to 30 minutes, sweep every 15 minutes, admit exactly one nudge, exercise the real role/queue handoff (script provider response if necessary), record the Manager's own sign-off, verify both current sign-offs and Approve plan becomes available; no Feature starts until explicit human bulk approval. Cover live long turns, legitimate human/dependency/provider/review waits, unknown activity, changed revision, duplicate/concurrent sweeps, restart between admission and delivery, failed/no-progress nudges and independent postcheck. Prove zero unnecessary model turns and no gate bypass. Use isolated real Git, canonical orchestration and focused browser/API tests.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse existing supervisor/watchdog polling, Epic 013 parent-owner recovery and audit classification, Epic 044 actionable status, Epic 048 generation/incident budgets and independent outcome verification, Epic 049 durable milestones and Epic 015 revision-bound sign-offs. Coordinate with Epic 056 approval separation and Epic 050 periodic project agents; this is built-in lifecycle liveness, not project maintenance. Trace the generic hard-gate ordering in cascade/watchdog/audit.py, existing Epic recovery admission, queue/writer fences and role turns. Keep costly audit cadence and lightweight deterministic sweep independently controllable; no additional persistence authority, separate scheduler, recurring free-form chat, automatic approval or deployment. Update owning DESIGN.md and affected C4 views. Filing this brief authorizes planning review only.

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
