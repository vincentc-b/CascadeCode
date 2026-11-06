---
id: feat_039_001
title: Dependency manifests, evidence, and planning gates
tier: feature
status: backlog
parent: epic_039
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
reasoning:
  feature_lead: high
  feature_architect: high
---
# Dependency manifests, evidence, and planning gates

## Parent Epic

epic_039

## Scope

Implement slice A of epic_039. Add durable revisioned dependency manifests (including explicit none required), append-only check attempts tied to actual environment identity, and immutable evidence snapshots bound to planning sign-off. Enforce current readiness at ordinary feature mint, sign-off, and plan approval using existing lifecycle/tracking-repository primitives. Missing, stale, unknown-environment, or unresolved-feasibility evidence blocks. Invalidate only affected dependency authority; preserve existing whole-plan revision sign-off rules. Existing epics require a manifest at their next planning action without restarting or cancelling accepted work. Keep software dependencies distinct from work-item depends_on. Acceptance: integration tests for absent/empty manifests, matching/mismatching environments, stale attempt completion and revisions, selective invalidation, and all guarded entry points. Define schemas and public transition contracts needed by slice B. No installation runner or new work-item tier in this slice.

## Data structures

TBD.

## API contracts

TBD.

## Logic flow

```mermaid
flowchart TD
  A[Start] --> B[End]
```

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

None.

## Decision log

None yet.
