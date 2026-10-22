---
id: epic_009
title: Support openai flex mode for cost optimization
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
# Support openai flex mode for cost optimization

## Intent

OpenAI has a "--flex" flag that increases response latency but reduces the token cost by half. I think we should over, as part of the provider selection, flex mode when openai is selected - as long as it is available. Similar features by other providers should also be supported.

### Success criteria

When creating a brief and openai (codex) is selected, a checkbox appears when flex mode can be selected. It is on by default.

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
