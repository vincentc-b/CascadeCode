---
id: epic_013
title: Configurable periodic auditors
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
# Configurable periodic auditors

## Intent

Every so often, perhaps in wall time or number of features merged, this may be configurable with the cascade toml, a team of agents is launched to look for issues in the repo. An angent first maps out common logic paths and important modules, and another agent verifies if there are any issues/bugs in that path. Another agent might look for re-factor opportunities to unify code, simplify if needed. The goal is not to fix, but to file briefs to fix found issues. As always, the agents don't want to correct very minor nits, we want impact from any finding so some sort of skill/guidance may be required.

### Success criteria

A team of agents launches periodically to evaluate the repository holistically.
The frequency can be set in yaml, either as calendar time or number of merged features.
The number and instruction for each agent is set and easily configurable. It should allow for dependencies in runs (i.e. list important paths, investigate function of paths), but some agents might be standalone (i.e. make sure design doc is up-to-date).

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
