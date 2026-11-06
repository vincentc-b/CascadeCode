---
id: feat_036_001
title: Resolve the optional tracking repository
tier: feature
status: backlog
parent: epic_036
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
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
reasoning:
  feature_lead: high
  feature_architect: high
approved_at: '2026-11-06T04:01:40.619856+00:00'
---
# Resolve the optional tracking repository

## Parent Epic

epic_036

## Scope

## Intent

Establish the repository-role model and optional tracking-repository configuration without changing default behavior.

## Acceptance criteria

- TOML and YAML accept one equivalent optional tracking-repository reference.
- Omission aliases tracking to target and preserves existing compatibility behavior.
- Local references resolve relative to the config location; remote references resolve to a deterministic managed checkout.
- Existing checkouts and clone preparation are validated idempotently.
- Git uses existing user configuration and credentials; Cascade does not prompt for or store credentials.
- Invalid paths, unsupported references, clone failures, and authentication failures produce actionable, redacted diagnostics.
- Resolved target and tracking contexts are explicit for downstream services.

## Scope constraints

Honor the epic contract and non-goals. Exact config-key naming, managed-checkout location, and synchronization mechanics may be selected here.

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
