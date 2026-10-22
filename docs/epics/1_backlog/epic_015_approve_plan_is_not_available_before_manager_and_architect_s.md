---
id: epic_015
title: Approve plan is not available before manager and architect sign off
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
# Approve plan is not available before manager and architect sign off

## Intent

Currently, when you initially activate a team, the epic goes to "active" and you can immediately sign off the plan. This not desired behavior. I would suggest that the plan approval should be grayed out unless the manager and architect sign off.

### Success criteria

-Upon initial team activation, "Approve plan" is grayed out (not clickable)
-Manager and architect need to sign off on the plan. Once signed, the "Approve plan" becomes clickable
-There should be a "planning in progress" with some sort of churning indicator when the team is actively working so we know not to look at the plan before they are ready. Maybe "view plan" can turn green when then need feedback
-Manager and architect should not sign off if there are open questions.

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
