---
id: epic_036
title: Split target and tracking repos
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
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Split target and tracking repos

## Intent

Currently, the epic/feature/task documentation lives in the same repo as is being worked on. I think there is a better model where we don't over-burden and pollute our development environment with all this documentation. Instead, the war room leverages a separate git repository for this, essentially decoupling the cascade code development environment from the project being worked on. I don't think this should be a requirement, but an option.

### Success criteria

-Optionally, users can specify a repository for the epic/feature/task documentation to go to
-This repository is defined in the cascade top-level config (toml or yaml)
-If not specified, the path defaults to cascade or something like that. For the current repo, this is "cascade"
-The repo should not require authentication past either an ssh key setup, or something like that. You don't want cascade to require credentials.

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

- 2026-11-05 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
