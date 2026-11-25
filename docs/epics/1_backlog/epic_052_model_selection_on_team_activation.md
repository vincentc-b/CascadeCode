---
id: epic_052
title: model selection on team activation
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
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  epic_manager: codex-auto-review
  epic_architect: codex-auto-review
  feature_lead: codex-auto-review
  feature_architect: codex-auto-review
  swe: gpt-5.6-sol
---
# model selection on team activation

## Intent

Currently, the models for teams (epic/feature/task) are selected during the brief. I think we should have "generic" guidance that is provider agnostic at this stage, because briefs can stay in a backlog for a long time before being picked up, models and providers are subject to change. A better model would be to specify the model size (small, medium, large) and reasoning guidance (low, medium, high, xhigh) and when activating a team and the provider is known/selected, this is mapped to an actual model and reasoning combination. Flex mode is selected then but can remain also in the brief.

### Success criteria

-Brief provider drop-down is no longer present
-Brief requests model size and reasoning effort per team
-Brief requests flex mode, default on
-When activating a team, a pop-up appears to select the model
-Pop-up defaults are mapped from the brief, and default provider mapping
-The current drop-downs in the brief are re-located to the activation phase.
-Flex mode is also selectable (if available for the provider/model combination)

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

- 2026-11-25 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
