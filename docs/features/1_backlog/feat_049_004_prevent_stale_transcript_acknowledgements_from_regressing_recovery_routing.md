---
id: feat_049_004
title: Prevent stale transcript acknowledgements from regressing recovery routing
tier: feature
status: backlog
parent: epic_049
children: []
depends_on:
- feat_049_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-11-26'
updated: '2026-11-26'
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
---
# Prevent stale transcript acknowledgements from regressing recovery routing

## Parent Epic

epic_049

## Scope

Repair the existing stale-acknowledgement acceptance gap only.

## Intent

Repair the stale transcript acknowledgement race found during post-merge review of completed feat_049_002 at 7f7df0e8fe125fa7178dacb8ce47b2bb3c4553fe. This implements the existing Epic durability and truthful-routing contract; it adds no product scope.

## Evidence and ownership

In reply to feat_049_002:feat_049_002:postmerge_stale_private_ack_20261126. cascade/recovery_progress/publisher.py::_record_transcript_milestone currently updates incarnation/append_sequence for matching receipt/entry/graph/message identity without establishing freshness. publish_committed_transition and drain_recovery_progress call it after the transcript graph fence is released. Feature review reproduced publish -> rewrite unrelated role row -> republish -> delayed saved private ack reverting the stored incarnation. The public-wrapper-only delayed-ack test does not cover this path. Treat completed lifecycle as distinct from acceptance.

## Acceptance criteria

1. Prevent stale acknowledgement downgrade through every mapping writer, including fast path, bounded drain/replay and public wrapper. Preserve receipt_id, entry_id, graph_id and message_id conflict rejection. Incarnation identifiers and append sequences alone are not a cross-incarnation ordering proof.
2. Establish a race-safe freshness protocol against authoritative transcript state or an enforceable durable ordering mechanism. Validate the entire check-to-write interval: merely refreshing an acknowledgement before releasing a graph fence is insufficient if a newer acknowledgement can commit before the old writer. Preserve safe lock ordering, bounded writer work and recovery admission independence.
3. Add deterministic regression coverage that delays a real fast-path or drain acknowledgement, rewrites or moves the room, commits the current mapping, then resumes the old private-path writer. Current routing must survive, receipt/message IDs stay stable, and exactly one milestone line remains. Exercise restart/replay, genuine identity conflict, and unavailable/pending authoritative evidence without fabricated routing or cursor advancement that loses delivery.
4. Run focused milestone/publisher/store tests and the affected source-contract checks. Provide exact integrated revision, fixture paths and measured results to the parent and Feature 3. Reconcile the final route/header/error/detail handoff from Feature 2; no route redesign is authorized.
5. Reconcile owning designs, native Code views and source contract with the actual repair. Document normal update, delayed acknowledgement and restart/failure behavior; retain current-design prose and one owner per requirement/decision. Verify actual Explore to Code, Level up, deep links and representative pinned source for affected nodes; preserve render bounds and warm artifact reuse.

## Diagram-impact inventory

| Level/view | Required treatment |
|---|---|
| Landscape/context: cascade-landscape, cascade-context | No new actor or external system is proposed; confirm against final diff. |
| Containers: cascade-containers | Existing publisher SQLite and transcript JSONL/index boundaries remain; no new service/store is authorized. |
| Components: cascade-supervisor-components, cascade-war-room-components | Retain publisher/transcript ownership; reconcile synchronization and calls if changed. |
| Code: cascade-watchdog-code, cascade-dashboard-code; cascade-workspace-code if move boundary changes | Update real source symbols, relationships, declaration kinds and contract for mapping freshness, receipt append/drain and any changed move/rewrite boundary. Preserve integrated resume_transcript_room_move node and retirement relationship. |
| Behavior: cascade/watchdog/DESIGN.md, cascade/war_room/DESIGN.md, cascade/workspace/DESIGN.md and recovery-progress owner | Trace source-lock release, graph fence, publisher transaction, delayed ack, restart and failure. Resolve the existing recovery-progress directory ownership gap if it remains in the affected design scope; do not duplicate design ownership. |

## Sequencing and scope

Depends on completed feat_049_002. Feature 3 acceptance and Epic completion remain withheld until this correction is integrated and verified. Use supported child planning/execution; do not reopen completed records or edit other teams' worktrees. Keep completed Task 1/5 board-record correction and Epic architecture publication recovery tracked separately. No new dependencies, installs, scheduler, model turns, raw tool streaming, or unrelated refactoring.

## Data structures

Preserve public v1 receipt, entry and acknowledgement identity fields. Feature planning must specify any internal freshness token or transaction precondition and its persistence/restart semantics before dispatch.

## API contracts

Keep progress/transcript routes and read budgets unchanged. Every acknowledgement writer must enforce the same stale-update rule.

## Logic flow

Planned correction: committed receipt -> fenced durable transcript acknowledgement -> race-safe publisher mapping -> immutable progress aliases. Delayed or unavailable evidence preserves the current mapping or pending delivery. Feature planning owns the concrete transaction/lock and failure protocol.

## Task breakdown

_(empty — Feature Team mints tasks after dispatch)_

## Risks & upward questions

Graph-fence release precedes publisher mapping, and incarnation IDs are opaque. Avoid lock inversion and a freshness-check/write race. Final API fixtures, producer design ownership and completed Task-record corrections remain explicit upstream gaps.

## Decision log

None yet.
