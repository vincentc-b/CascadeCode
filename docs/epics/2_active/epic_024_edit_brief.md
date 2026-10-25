---
id: epic_024
title: Edit brief
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
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-luna
reasoning:
  epic_manager: high
  epic_architect: high
---
# Edit brief

## Intent

I want the option to edit a brief in the backlog, including its agent assignment, reasoning, etc. This should result in a new PR that modifies the brief. Of course, it is expected that the board then updates with the new plan.

### Success criteria

-Brief as edit button
-Editing a brief means all fields can be edited.
-A new PR is created to modify the brief.

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

- 2026-10-25 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
