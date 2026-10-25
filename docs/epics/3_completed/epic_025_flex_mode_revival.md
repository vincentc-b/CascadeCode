---
id: epic_025
title: Flex mode revival
tier: epic
status: cancelled
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
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-terra
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: medium
  feature_architect: medium
  swe: high
cancellation_reason: duplicate
cancelled_at: '2026-10-25T23:15:33.004649+00:00'
cancellation_step: complete
---
# Flex mode revival

## Intent

Since the brief UI was updated to pull models from APIs and enable reasoning selection, we see to have lost the "flex mode" option which is important for cost savings.

### Success criteria

-Add a flex mode toggle. This probably shouldn't be part of the brief, but a top-level item/toggle in the war room like "stacked PRs"
-When selected and when the feature is available, model requests are made with flex mode or their provider equivalence

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
