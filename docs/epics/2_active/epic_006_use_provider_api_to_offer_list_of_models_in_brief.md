---
id: epic_006
title: Use provider api to offer list of models in brief
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
created: '2026-10-21'
updated: '2026-10-24'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Use provider api to offer list of models in brief

## Intent

When creating a brief, there is a drop-down for provider, but the models for the Epic Manager and  architects are simple text boxes. If these models are not valid, it will create issues downstream. Can we instead pull a list of valid models from the provider, and populate a drop-down of models that can be used? This could potentially be done asyncronously every so often with the available providers (if we aren't signed in or a provider is not installed, ignore). I also think we should pick the feature and task defaults here.
Also, providers that are not currently available/installed should not be offered as an option.

### Success criteria

Creating a feature brief offers a drop-down of available models.
The provider drop-down only contains available providers.
The available models are obtained from the actual provider api.
The models are chosen for the full agent stack (epic, feature, task)

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

- 2026-10-21 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
