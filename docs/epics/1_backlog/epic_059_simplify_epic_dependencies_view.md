---
id: epic_059
title: Simplify epic dependencies view
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
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6.2-sol
  epic_architect: gpt-6.2-sol
  feature_lead: gpt-6.1-sol
  feature_architect: gpt-6-sol
  swe: gpt-6.2-sol
reasoning:
  epic_manager: xhigh
  epic_architect: xhigh
  feature_lead: high
  feature_architect: high
  swe: low
---
# Simplify epic dependencies view

## Intent

Currently, when an epic is planned it seems to show all dependencies and lots of details for each. I would like to re-work this and simplify such that only newly-required dependencies are displayed, the package licence(s), any associated datasets - basically a legal and security overview of that dependency.

### Success criteria

-An epic that needs no new dependencies doesn't display any
-new dependencies only are shown, and their dependencies they pull in (basically delta of fully resolved requirements.txt for python)
-each package licenses are listed

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

- 2026-11-27 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
