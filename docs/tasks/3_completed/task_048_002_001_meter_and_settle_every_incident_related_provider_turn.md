---
id: task_048_002_001
title: Meter and settle every incident-related provider turn
tier: task
status: completed
parent: feat_048_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e63a83fd810526e9ecb56b5df23c5c9d2759d809
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Meter and settle every incident-related provider turn

## Parent Feature

[feat_048_002](../../features/2_active/feat_048_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement F2 provider-boundary admission against the Task-owned incident budget. Reserve paid turn and worst-case model runtime before every owner, audit, briefing, parent or replacement-action provider launch; carry one original incident/claim identity through nested MCP work. Normalize physical invocation receipts across Codex, Claude, Cursor and test transport with provider/model/invocation ID, known/estimated/unavailable input/output/cached usage, cancellation/output bound and exact-once restart settlement. Do not invent token totals or bills. Verify competing callers, unknown usage, provider switch and interruption with real adapter calls. Architecture: update cascade/agent/DESIGN.md (proposed REQ-AGENT-RECOVERY-001/DEC-AGENT-RECOVERY-001 only when real), cascade/task/DESIGN.md and affected tier designs; reconcile cascade-agent-code, cascade-task-code and affected epic/feature code views plus supervisor/team components in model.dsl, views.dsl, workspace.contract.json; context/containers unchanged only with source-backed reason. Verify source contract, local render, context→container→component→Code navigation, Level up, deep link and pinned source.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
