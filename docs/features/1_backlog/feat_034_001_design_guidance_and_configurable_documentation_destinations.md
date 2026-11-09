---
id: feat_034_001
title: Design guidance and configurable documentation destinations
tier: feature
status: backlog
parent: epic_034
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
  swe: medium
approved_at: '2026-11-09T18:25:31.065104+00:00'
---
# Design guidance and configurable documentation destinations

## Parent Epic

epic_034

## Scope

Delivery slice A of epic_034; success criteria 1–2 and document-boundary constraints. epic_036 is the completed parent prerequisite.

Provide a concise design skill informed by /home/ubuntu/dev/automatik/skills and a DESIGN.md template with matching table of contents: requirements, decisions/rationale, interfaces, architecture links, and verification evidence. Preserve and reconcile the existing root design. Each requirement/decision has one owning design; parents summarize shared contracts and link to child detail. Meaningful directories own distinct behavior/state/interfaces; trivial/generated directories name their covering parent.

Extend RepositoryContext and target cascade.toml with [architecture] destination = "target" | "tracking", default target. Tracking requires epic_036's configured tracking repository. Resolve reads, proposals, links, reviews, and replay consistently. Target designs live at <code-directory>/DESIGN.md; tracking designs at design/<immutable-target-repository-key>/<code-directory>/DESIGN.md. Editable models/fragments live at architecture/<target-repository-key>/ in the selected destination. Persist stable target-directory mappings and ownership; never derive identity anew from a basename.

Acceptance: defaults, target and tracking modes, invalid combinations, root preservation, one-home references, and stable mapping after configuration changes. Existing review units must retain their fixed destination. Include focused integration checks and documentation closeout. Reuse existing configuration/routing services; no separate document service UI.

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
