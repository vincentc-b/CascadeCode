---
id: epic_038
title: Make planning dependency status authoritative
tier: epic
status: active
parent: null
children:
- feat_038_001
- feat_038_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Make planning dependency status authoritative

## Intent

Planning agents must evaluate `depends_on` through Cascade's authoritative merged-board and lifecycle state, not by attempting to read another team's scoped specification. A denied content read must remain an authorization boundary and must never be interpreted as an incomplete or unaccepted dependency. Fix planning context, status reporting, and tests so activation, planning, sign-off, and operator-facing explanations agree on whether dependencies are satisfied.

### Success criteria

1. Epic and feature planning receives a minimal, read-only dependency-status projection for every declared dependency: work ID, tier, canonical lifecycle status/column, completion evidence, and a stable status-unavailable reason when authoritative state cannot be read.
2. The projection is derived from the same merged-board/lifecycle rules used by dispatch and activation. A completed item in `3_completed` satisfies the dependency even when the caller is not authorized to read its plan body.
3. Content authorization remains unchanged. Dependency status does not expose another team's plan, comments, prompts, secrets, or arbitrary repository files.
4. Planning agents and generated summaries distinguish `content_access_denied`, `dependency_unmet`, and `dependency_status_unavailable`; they never convert one into another or add a false blocker.
5. Plan readiness, feature minting guidance, War Room status, and planning transcripts report the same current dependency result. Historical messages remain historical and do not masquerade as live status.
6. A dependency that changes during a planning turn is rechecked at the sign-off/approval/minting boundary; stale evidence cannot authorize downstream work.
7. Regression coverage includes: completed dependency with unreadable spec, readable but incomplete dependency, missing dependency, tracking-repository dependency, and a dependency completing while its dependent epic is active.
8. The epic_034/epic_036 sequence is captured as a regression fixture: epic_036 completion is recognized without granting epic_034 access to epic_036's spec.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Reuse the canonical merged-board and lifecycle predicates rather than introducing a second dependency database or parsing chat prose. Preserve fail-closed behavior when authoritative status truly cannot be established. Do not broaden scoped document access. Keep stable machine-readable blocker codes separate from human explanations.

## Core dependencies

To be identified during epic planning.

## Feature breakdown
- feat_038_002
- feat_038_001

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-06 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
