---
id: feat_049_005
title: Bound transcript acknowledgement work under contention
tier: feature
status: completed
parent: epic_049
children:
- task_049_005_001
- task_049_005_002
depends_on:
- feat_049_004
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 032809336f3fcf3810c7270c28195da9c85a3bf6
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
approved_at: '2026-11-26T03:31:07.657185+00:00'
---
# Bound transcript acknowledgement work under contention

## Parent Epic

epic_049

## Intent and evidence

Close the existing writer-budget acceptance gap in completed feat_049_004 at a3d4a42b3df92a553206c300c42142600183eaef. Epic Architect source review recorded the gap in canonical Epic revision 03ce7eb0: fenced_transcript_source_acknowledgement uses blocking thread/OS graph locks and _connect_index with schema initialization and a 30-second SQLite timeout. This can block the supervisor beyond the selected 250 ms fast-path and one-second drain budgets. Completed lifecycle and the reported 69/77 passing suites do not establish contention bounds. Preserve the atomic routing and UTF-8 repairs; no product scope expansion.

## Scope

1. Propagate a shared remaining monotonic deadline through fast-path, public mapping and drain/replay paths. Bound publisher/thread lock, graph thread/OS fence and SQLite lock acquisition/work under contention; no independent timeout may reset the total budget. Inspect append/dedup and mapping call paths so a preceding blocking acquisition cannot defeat the same budget. Document baseline source mutation cost separately; do not promise a hard bound on an uninterruptible filesystem operation.
2. The fenced source lookup must read an existing index without schema initialization, import, repair or publication. Missing/incompatible index, unfinished intent, unavailable ownership or exhausted budget returns pending and leaves authoritative work eligible for replay.
3. Preserve publisher-before-graph lock order and graph fence through mapping SQLite commit for first insertion and all updates. Preserve immutable receipt/entry/graph/message conflict rejection, current incarnation/sequence, and no stale-ack downgrade across rewrite/move/restart.
4. Add deterministic contention regressions for thread lock, a second process holding the OS graph fence, and SQLite contention. Verify bounded return using measured elapsed time with justified test tolerance; no lost receipt, duplicate milestone, fabricated mapping or cursor advancement beyond pending delivery. Release contention and prove a subsequent drain completes exactly once. Retain private/public real interleaving and malformed UTF-8 positive-continuation regressions.
5. Run focused publisher/milestone/store/API and source-contract checks; supply exact integrated revision, test names, commands, measured timings and limits. Extend existing integration tests rather than redundant mock-only coverage.
6. Reconcile cascade/recovery_progress/DESIGN.md (including REQ-RECOVERY-PROGRESS-004), cascade/war_room/DESIGN.md and affected Watchdog/package/Workspace links with source. Keep one owner and current-design prose. Preserve native Code navigation and source contracts; never rewrite accepted publication snapshots.

## Data structures

Retain existing receipt/message identities, transcript index and publisher mapping. Carry a monotonic deadline internally; do not add public ordering tokens.

## API contracts

Keep public progress/transcript/detail routes, typed errors and budgets unchanged. Timeout or unverifiable source keeps delivery pending for replay.

## Logic flow

Acquire locks and SQLite using the remaining shared budget; read the existing source index under graph fence; commit current mapping before releasing the fence. On contention or unfinished evidence, unwind safely and retain replay eligibility. Later drain retries the same durable source key.

## Diagram-impact inventory

| Level/view | Owner and required review | Verification |
|---|---|---|
| cascade-landscape / cascade-context | Root design; existing actors/dependencies | Final-diff no-change reason unless boundaries change. |
| cascade-containers | Package/root designs; existing publisher SQLite and transcript storage | Confirm runtime/persistence boundaries; no new service or isolation claim. |
| cascade-supervisor-components / cascade-war-room-components | Recovery Progress, Watchdog and War Room designs | Trace publisher/fence/lookup ownership and timeout-to-pending interface. |
| cascade-watchdog-code / cascade-dashboard-code; cascade-workspace-code if affected | Publisher mapping/fast path/drain, graph fence, index lookup, move/rewrite callers | Update model.dsl, views.dsl and workspace.contract.json together for real symbols/kinds/relationships. Validate source contract and pinned render; actual Explore to Code, Level up, deep links and pinned source; stale symbol/ownership checks and warm artifact reuse. |
| Supplementary behavior | Recovery Progress and War Room owners | Normal atomic mapping, deadline exhaustion, pending replay and restart sequence; verify against real contention fixtures. |

## Sequencing and boundaries

Depends on completed feat_049_004. Feature 3 may continue independent consumer work against pinned fixtures; its final integrated acceptance and Epic completion require this correction and revalidation on the repaired baseline. No UI workaround, new route, dependency installation, scheduler, paid turn or unrelated storage rewrite. Do not reopen completed records or edit another team's worktree. Completed board-record corrections and architecture publication recovery remain separate.

## Task breakdown

1. `task_049_005_001` — Implement one remaining monotonic deadline across append, publisher locks/transactions, graph fences and existing-index lookup; preserve pending/replay and add measured thread, second-process flock and SQLite contention regressions.
2. `task_049_005_002` (depends on 001) — Reconcile owning designs and all-level C4/Code inventory against integrated code; validate source contract, render, pinned browser navigation, focused regressions and exact handoff evidence for Epic and Feature 3.

## Risks & upward questions

Filesystem stalls are not hard real-time bounded; document exact measured contention guarantees. Preserve lock order and deadline accounting across append and mapping. Completed-record correction and architecture publication recovery remain upstream.

## Decision log

- `dec_001` · 2026-11-26 · Feature Lead · **Task breakdown**
  Chose Sequence bounded publisher and transcript contention work before integrated design and architecture verification in two tasks..
  Rationale: The lock and SQLite changes share one recovery invariant and require joint contention tests; revision-pinned C4 and design verification must use the final implementation. A dependent verification task keeps the product change focused and gives the final acceptance gate an exact integrated revision.
  Honors: Shared deadline, replay safety, source-linked architecture, measured acceptance, and minimal task count..

## Closeout

Completed child work: `task_049_005_001` (Bound transcript milestone locks and replay under one deadline), `task_049_005_002` (Reconcile contention design, native Code views and integrated evidence).
