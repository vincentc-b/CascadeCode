---
id: task_049_002_003
title: Give authored replies stable checkpoint identity
tier: task
status: completed
parent: feat_049_002
children: []
depends_on:
- task_049_002_001
owners:
- swe
skills: []
parent_rev: ac9ddcf32cd67965da38682847f59e183f78b1d7
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Give authored replies stable checkpoint identity

## Parent Feature

[feat_049_002](../../features/2_active/feat_049_002_persist_recovery_milestones_and_bounded_transcript_history.md)

## Depends on

- task_049_002_001

## Acceptance criteria

carry checkpoint lineage and persisted message ordinal or durable ID through kickoff direct append and explicit backfill; same message dedupes across crash/restart, separate identical replies survive. Preserve authored final summaries, sanitization and human messages. Convert every append and failed human-ingest remove/rewrite to the shared graph fence/index/intent path. Legacy ambiguous author/body matches stay explicitly legacy_unknown. Backfill is writer/supervisor work, never GET; no extra paid role turn. Cover interruption after checkpoint commit, after JSONL fsync and after index commit, two processes, distinct same-text replies, rollback/rewrite incarnation and legacy unknown occurrence. Reconcile cascade/war_room/DESIGN.md, cascade/workspace/DESIGN.md, Epic/Feature checkpoint owner designs and cascade-dashboard-code, cascade-workspace-code, cascade-teams-code with real source symbols and normal/failure flow.

## Files likely touched

cascade/war_room/planning_transcript.py and chat_store.py; cascade/workspace/kickoff.py; Epic/Feature checkpoint identity; tests/war_room/; owning designs and architecture source.

## Implementation notes

Follow the saved feature storage/API contract and completed producer fixtures. Record design review and verification evidence in Task closeout.

## Skills

_(none)_

## Test plan

Direct append/backfill restart tests using persisted checkpoint lineage; two writer processes, repeated text as separate messages, human rollback and legacy ambiguity.

## Out of scope

New recovery scheduler, repair authority, paid model turn, unbounded GET scan and unrelated UI redesign.
