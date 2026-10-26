---
id: feat_009_002
title: Brief editor flex-mode control
tier: feature
status: backlog
parent: epic_009
children: []
depends_on:
- feat_009_001
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  feature_lead: gpt-5.6-sol
  feature_architect: gpt-5.6-sol
---
# Brief editor flex-mode control

## Parent Epic

epic_009

## Scope

# Brief editor flex-mode control

## Intent

Expose flex mode in provider selection when the selected provider supports it.

## Acceptance criteria

- A checkbox appears for a flex-capable Codex/OpenAI selection and is checked by default for a new brief.
- Changing to a provider without the capability hides the control and clears/normalizes the enabled value.
- Returning to a capable provider uses the form's current normalized value; saving and reopening preserves explicit opt-out.
- Submission uses the same brief field consumed by provider execution.
- A focused UI/system test covers visibility, default-on, opt-out persistence, and provider switching.

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
