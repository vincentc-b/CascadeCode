---
id: epic_030
title: Return an unstarted Epic to backlog
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
created: '2026-10-31'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
---
# Return an unstarted Epic to backlog

## Intent

An Epic can be activated before its pinned provider proves usable. `epic_028` is active with Cursor, but planning cannot proceed because Cursor is not authenticated. Give the operator a safe, human-only Return to backlog action so an Epic that has done no substantive work can be edited through the existing reviewed backlog-brief flow and activated again with corrected provider and model choices.

### Success criteria

- Show Return to backlog on an active Epic only when no plan has been approved, no child work or review exists, and no substantive plan changes would be lost. Explain each refusal on the Epic row. Include a provider-blocked Epic with only failed startup attempts as an eligible case.
- On request, quiesce any in-flight Epic turns, acquire the lifecycle lock, and recheck eligibility before changing state. Make the transition durable and restart-safe, with a single audit event. Repeated requests must return the same outcome without duplicate branches, checkpoints, or events.
- Restore a valid backlog brief with the same Epic ID and approved source content, remove the active pointer from board view, and make the existing backlog brief editor available. Preserve or safely archive the former integration branch, worktree, transcript, and failure evidence; refuse if dirty work or unmerged commits would be discarded. Do not reset or switch the operator trunk.
- After the provider/model edit MR merges and the backlog refreshes, a later activation starts from the revised approved brief with fresh role pins. It must not resume a stale checkpoint that still selects Cursor.
- End-to-end tests cover `epic_028`'s missing-credential shape, a concurrent/repeated rollback, a restart between steps, refusal after planning or child work, the reviewed provider edit, and successful reactivation with Codex.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Human approval remains required for changing an approved brief: reuse the existing MR-backed backlog edit path rather than editing active plan metadata in place. Preserve IDs, comments, and history. Do not cancel completed or reviewed work, delete dirty artifacts, force-push, or bypass provider and lifecycle gates. Define the exact safe eligibility predicate and use it in both the API and War Room control.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-31 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
