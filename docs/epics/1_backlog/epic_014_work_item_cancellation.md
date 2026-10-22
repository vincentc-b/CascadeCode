---
id: epic_014
title: Work item cancellation
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
created: '2026-10-22'
updated: '2026-10-22'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Work item cancellation

## Intent

Currently, epics in the backlog can only go away if they are implemented. We need a way to cancel them. Same for features although this is trickier as it would require the parent epic to pause if not cancelled and do something about it. Perhaps cancelling a feature needs a prompt then to get user input on why it is cancelled and what the epic team should do about it. If a feature is cancelled in flight, the work done so far should be cleaned up (clean up branch and worktree to avoid pollution)

### Success criteria

-Work items (epics, features, tasks) can be cancelled
-Cancelling gives feedback to parent work items
-Cancelling results in no git pollution such as dangling branches or worktrees

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

To be refined by the Epic Team during planning.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
