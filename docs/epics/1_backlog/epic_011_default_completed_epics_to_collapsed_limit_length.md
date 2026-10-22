---
id: epic_011
title: default "completed" epics to collapsed, limit length
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
# default "completed" epics to collapsed, limit length

## Intent

As we get more work done, the list of completed epics is getting long. I would limit the size of the list to the last 10 completed (completed work is not that useful in the war room), and perhaps leave a link to the repository page where the completed epics live so that interested parties can go browse them if needed

### Success criteria

Completed epics board defaults to collapsed.
Completed epics board limits to "N" entries, configurable in the project cascade yaml.
A link to the repository is left available for people who want to go back farther.

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
