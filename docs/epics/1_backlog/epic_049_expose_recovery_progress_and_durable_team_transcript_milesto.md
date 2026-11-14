---
id: epic_049
title: Expose recovery progress and durable team transcript milestones
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
created: '2026-11-14'
updated: '2026-11-14'
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
# Expose recovery progress and durable team transcript milestones

## Intent

Let an operator see whether recovery has only been requested, has been acknowledged, is actively executing, is waiting on a prerequisite, or has finished. Show this on the War Room board and the owning team's Historical transcript without requiring inspection of runtime JSON or inference from old team summaries.

Observed on 2026-11-14: epic_044's implementation review, https://github.com/vincentc-b/CascadeCode/pull/243, conflicted with main. Recovery action resolution:v1:8bacbfcc9a7211006229507469fdc5acee119cee28d8e41dc0a356cdb60a1404 was queued at 03:58:01 UTC, acknowledged at 03:58:10, and claimed as running at 04:02:25. The board continued to say Recovery investigating because its projection keys off routing_marker.status == enqueued. The Historical transcript still ended at 03:41 with an older no-recovery-needed summary. The running attempt was visible only in the durable action ledger.

Current code mirrors role responses into chat after graph invocation returns; it does not expose live recovery milestones. A queued handoff, a live owner turn, a claimed repair attempt and verified resolution are distinct facts. Historical assertions must remain dated history rather than appear to describe current health.

### Success criteria

1. Project current recovery progress from existing durable action, handoff, attempt and claim evidence. Distinguish requested/queued, acknowledged, executing, waiting/blocked, failed/exhausted and verified completion where supported. Show the owner, action/review link, last transition time, attempt number and next safe step. A routing marker alone must never claim active execution; admission marked mutation_ready is authorization, not proof of a mutation.
2. Make running status truthful: require valid execution/owner evidence, handle expired claims and dead workers, and distinguish a live investigating team turn from an executing repair attempt. Report stale or unavailable evidence explicitly. Waiting states explain the actual prerequisite and responsible owner; do not infer a human gate from elapsed time alone.
3. Append safe, concise, durable system milestones to the owning team's Historical transcript as transitions occur, without waiting for the entire manager/architect turn to finish. Include queued, acknowledged, attempt started, meaningful stage changes when durably available, waiting/failure, publication and verified completion. Identify the recovery action and review and use event occurrence times. Keep final manager/architect summaries and clearly distinguish system recovery events from authored role messages.
4. Keep a current recovery summary visible beside the Historical transcript and on the board. Both views must agree on action identity and state; preserve or link concurrent incidents without silently hiding a newer blocker. A historical no-recovery-needed message must not override current evidence. Link current recovery to relevant transcript milestones and the review.
5. Survive refresh, navigation and worker/service restart. Coalesce repeated observations; one material transition produces one milestone despite repeated polling, duplicate delivery or concurrent workers. Preserve attempt/generation identity and order, avoid duplicate final role summaries, and reconcile missed milestones from durable evidence with provenance. Legacy records lacking timestamps must be labeled honestly rather than assigned fabricated historical times.
6. Keep UI reads bounded and read-only. Reuse existing projections and durable stores; do not trigger recovery, Git/provider probes, full-history scans or writes from GET/poll paths. Progress updates must not depend on model-generated commentary and must not create extra paid agent turns. Define bounded history/pagination behavior using the existing transcript conventions.
7. Add meaningful API and browser regressions for queued-but-idle recovery, acknowledgement, a long-running turn with a live repair attempt, waiting for checks or publication, dead/expired owner evidence, failure/retry, changed generations and independently verified completion. Exercise repeated refresh, concurrent delivery and restart; prove no duplicate milestones, no invented progress and no repair side effects from reads.
8. Reproduce the epic_044 timeline in a deterministic fixture and validate the operational UI through supported entry points. During a long-running recovery, the board and current summary must show the supported live state, and the transcript must display its start milestone before the role's final reply. Document remaining limits instead of claiming live tool-output streaming or successful recovery from a claimed attempt alone.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

Use the normal Epic/Feature/Task planning and review workflow. Filing this brief authorizes no implementation or activation. Keep it in backlog for normal approval.

Reuse cascade/war_room/recovery_incident.py, planning_transcript.py, chat_store.py, sidecar_routes.py, board/chat UI, workspace kickoff and existing action recovery/claim/handoff records. Investigate these boundaries before choosing implementation. Do not introduce a parallel recovery scheduler or ledger, change repair authority or bypass review/validation gates. The work is visibility, not a change to recovery execution policy.

Coordinate with epic_044 health audit presentation and epic_048 self recovery evidence/verification requirements; inspect their accepted changes before planning to avoid duplicate work. Do not require waiting for unrelated broad recovery work if existing durable records support this scoped visibility improvement. Any formal dependency must be established during planning.

Preserve transcript/history, stable action identities and raw recovery evidence. Do not expose credentials, provider prompts, private reasoning or unbounded subprocess output. Show only safe operational facts and summaries. Existing human approvals, ownership, leases and exact-generation verification remain authoritative.

Use Codex and retain the explicit role model/reasoning selections for descendants. Do not change workspace-wide settings.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-14 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
