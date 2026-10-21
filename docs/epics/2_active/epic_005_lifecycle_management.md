---
id: epic_005
title: Lifecycle management
tier: epic
status: active
parent: null
children:
- feat_001
- feat_002
- feat_003
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-21'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Lifecycle management

## Intent

Right now, there are a few awkward bits. in a feature's lifecycle.
Feature implementation begins when the epic is approved. I think we can have a per-feature approval, but we need to ensure that a feature is not dispatched for implementation if it depends on previous features that were not implemented. Approving the epic would approve all the features, which then means they could process.
Now, when a feature's tasks complete the plan is moved to "completed" and the MR is open. If this is the last feature of an epic, the epic should be moved to completed too unless the feature has discovered issues and suggested a follow-up feature to the parent epic. There should be a dashboard with "open MRs" so we can easily go review them without necessarily going to the plans or teams.

### Success criteria

Feature an epic transitions to completed are automatic based on their content completion. It would be great to have some sort of sandbox project w/ a playwrite script or something like that to demonstrate the behavior.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

To be refined by the Epic Team during planning.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_003
- feat_002
- feat_001

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
