---
id: epic_003
title: Short-horizon and standalone work
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
created: '2026-10-18'
updated: '2026-10-21'
---

# Short-horizon and standalone work

## Intent

Small, short-horizon work such as a focused bug fix, documentation correction, or infrastructure task should not always require a full multi-feature epic planning cycle. Operators need an explicit lightweight path for tracking and dispatching that work while preserving the existing epic → feature → task hierarchy as the default for larger product work.

### Success criteria

- Operators can deliberately create and track short-horizon work on the board without first planning a multi-feature epic.
- Short-horizon work uses the existing dispatch authorization, worktree isolation, and War Room visibility.
- The normal epic → feature → task workflow remains unchanged for long-horizon product work.
- Parentage, merge targets, completion, and cleanup semantics are explicit rather than inferred from missing metadata.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

- Preserve the existing dispatch law; planning agents must not gain self-dispatch authority.
- Keep short-horizon work explicit and distinguishable from malformed or orphaned work documents.
- Define branch targets and lifecycle behavior before standalone work can be dispatched.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- What is the smallest work unit that may stand alone?
- Should standalone work use nullable parentage or an explicit workspace container?
- What branch and review path should standalone work use?

## Decision log

- 2026-10-21 · Human · Returned the proposal to a backlog brief; implementation architecture and feature decomposition are deferred until activation.

## Amendment log

_(none)_
