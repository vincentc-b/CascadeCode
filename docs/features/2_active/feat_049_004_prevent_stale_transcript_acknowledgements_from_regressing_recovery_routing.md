---
id: feat_049_004
title: Prevent stale transcript acknowledgements from regressing recovery routing
tier: feature
status: active
parent: epic_049
children:
- task_049_004_001
- task_049_004_002
- task_049_004_003
depends_on:
- feat_049_002
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
approved_at: '2026-11-26T02:07:49.014961+00:00'
---
# Prevent stale transcript acknowledgements from regressing recovery routing

## Parent Epic

epic_049

## Scope

Repair the existing stale-acknowledgement and nonadvancing malformed detail-cursor acceptance gaps only; preserve the existing public routes and budgets.

## Intent

Repair the stale transcript acknowledgement race found during post-merge review of completed feat_049_002 at 7f7df0e8fe125fa7178dacb8ce47b2bb3c4553fe. This implements the existing Epic durability and truthful-routing contract; it adds no product scope.

## Evidence and ownership

In reply to feat_049_002:feat_049_002:postmerge_stale_private_ack_20261126. cascade/recovery_progress/publisher.py::_record_transcript_milestone currently updates incarnation/append_sequence for matching receipt/entry/graph/message identity without establishing freshness. publish_committed_transition and drain_recovery_progress call it after the transcript graph fence is released. Feature review reproduced publish -> rewrite unrelated role row -> republish -> delayed saved private ack reverting the stored incarnation. The public-wrapper-only delayed-ack test does not cover this path. Treat completed lifecycle as distinct from acceptance.

## Candidate repair and delivery handoff

In reply to feat_049_002:feat_049_002:postmerge_detail_cursor_gap_20261126 and feat_049_002:feat_049_002:postmerge_repair_ecd390f4_20261126. Candidate commit `ecd390f4d1819d72bc65e2ea4960000a48e50a67` on the completed Feature 2 branch, based on `7f7df0e8fe125fa7178dacb8ce47b2bb3c4553fe`, contains the private-helper refresh, UTF-8 boundary rejection, focused regressions and Watchdog/War Room design updates. Evidence: `docs/feature_artifacts/feat_049_002_postmerge_review.md` at that commit. The owner reports 27 focused tests (10k/browser deselected), Ruff and diff checks; these are reported results, not renewed Epic verification or accepted delivery.

Final Feature 2 architect handoff `feat_049_002:feat_049_002:architect_final_postmerge_review_e986ceb1` adds evidence commit `e986ceb19d69de834ef9074ce8b35d66dd81bd4b` at the same artifact path. It reports 29 passing focused milestone/transcript API/C4 source tests, validation of 234 elements, 280 relationships and 24 views, and passing Ruff/diff checks. This commit changes only the review artifact; the candidate implementation remains `ecd390f4`. Earlier Task 4 renderer/Chromium results concern the unchanged model; no post-repair browser rerun is reported. Carry this evidence through corrective delivery, retaining the integrated race, source-relationship and navigation acceptance below. Neither commit is in the Epic integration ancestry reviewed at `134969e6`.

Use this candidate through the supported corrective child delivery path; inspect its applicability to the integrated baseline and reuse the repair instead of duplicating implementation. It is not an ancestor of the Epic integration HEAD reviewed at `dc8d6a6c`. Do not treat a completed Feature record or candidate commit as delivered acceptance, reopen completed records, or manually replace supervisor merge bookkeeping.

The candidate refreshes differing existing routing under a publisher transaction via `chat_store.transcript_source_acknowledgement`. Its new regression invokes the private helper sequentially after rewrite. It does not itself supply the required deterministic real fast-path/drain interleaving, public check-to-write race, first mapping insertion, move/restart/pending matrix, or post-repair navigation evidence. Verify these and the lock ordering/bounds of the source acknowledgement helper (which can repair/import/publish transcript data), preserving the acceptance below.

The additional detail reproduction used an oversized emoji body and caller-edited cursor offset inside a multibyte character; it returned HTTP 200 with an empty chunk and identical next offset. Candidate rejection must return typed `400 invalid_request`; all successful incomplete chunks must advance positively. This is a correction to the existing bounded pagination contract, not a route redesign.

## Acceptance criteria

1. Prevent stale acknowledgement downgrade through every mapping writer, including fast path, bounded drain/replay and public wrapper. Preserve receipt_id, entry_id, graph_id and message_id conflict rejection. Incarnation identifiers and append sequences alone are not a cross-incarnation ordering proof.
2. Establish a race-safe freshness protocol against authoritative transcript state or an enforceable durable ordering mechanism. Validate the entire check-to-write interval: merely refreshing an acknowledgement before releasing a graph fence is insufficient if a newer acknowledgement can commit before the old writer. Preserve safe lock ordering, bounded writer work and recovery admission independence.
3. Add deterministic regression coverage that delays a real fast-path or drain acknowledgement, rewrites or moves the room, commits the current mapping, then resumes the old private-path writer. Current routing must survive, receipt/message IDs stay stable, and exactly one milestone line remains. Exercise restart/replay, genuine identity conflict, and unavailable/pending authoritative evidence without fabricated routing or cursor advancement that loses delivery.
4. Run focused milestone/publisher/store tests and the affected source-contract checks. Provide exact integrated revision, fixture paths and measured results to the parent and Feature 3. Reconcile the final route/header/error/detail handoff from Feature 2; no route redesign is authorized.
5. Reconcile owning designs, native Code views and source contract with the actual repair. Document normal update, delayed acknowledgement and restart/failure behavior; retain current-design prose and one owner per requirement/decision. Verify actual Explore to Code, Level up, deep links and representative pinned source for affected nodes; preserve render bounds and warm artifact reuse.

6. Deliver the UTF-8 detail cursor correction from the candidate (or an equivalent reviewed implementation) with a loopback malformed-boundary regression, normal multibyte reconstruction and positive continuation progress. Preserve typed errors, immutable cursor identity, read-only behavior and existing byte/read budgets. Include the final detail route fixtures in the Feature 3 handoff.

## Diagram-impact inventory

| Level/view | Source/owner and required treatment | Task verification |
|---|---|---|
| Landscape/context: `cascade-landscape`, `cascade-context` | Root `DESIGN.md`: no new actor/external dependency; compare final diff and retain views if true. | Task 3 records evidence-based no-change. |
| Containers: `cascade-containers` | `cascade/DESIGN.md`: publisher SQLite and transcript JSONL/index stay within existing Python runtime/storage boundaries; inspect persistence and failure behavior. | Task 3 checks source and view agreement; change only if actual boundary changes. |
| Components: `cascade-supervisor-components`, `cascade-war-room-components` | `cascade/watchdog/DESIGN.md` and `cascade/war_room/DESIGN.md`: publisher owns mapping, transcript library owns authoritative source/fence; reconcile calls and owner boundaries. | Tasks 1 and 3 trace normal, delayed, move and restart paths. |
| Code: `cascade-watchdog-code`, `cascade-dashboard-code`; `cascade-workspace-code` if move behavior changes | `publisher.py` mapping helper, `publish_committed_transition`, `drain_recovery_progress`, public wrapper; `chat_store.py` fence/current source lookup; `transcript_pages.read_transcript_detail`; move/rewrite symbols if changed. Update `model.dsl`, `views.dsl`, `workspace.contract.json` together with real source links, kinds and relationships. Retain `resume_transcript_room_move` and retirement link. | Task 3 validates source contract, local render, Explore → Code, Level up, deep links, pinned source, warm reuse and render bounds. |
| Supplementary behavior | `cascade/watchdog/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/workspace/DESIGN.md`, and the recovery-progress owner: show graph fence through publisher commit, pending evidence, restart/replay, and typed invalid UTF-8 detail cursor. | Tasks 1–3 review exact source paths, one owner per requirement/decision and current-design prose; task 3 records changes or concrete no-change reasons in closeout. |

## Sequencing and scope

Depends on completed feat_049_002. Feature 3 acceptance and Epic completion remain withheld until this correction is integrated and verified. Use supported child planning/execution; do not reopen completed records or edit other teams' worktrees. Keep completed Task 1/5 board-record correction and Epic architecture publication recovery tracked separately. No new dependencies, installs, scheduler, model turns, raw tool streaming, or unrelated refactoring.

## Data structures

Preserve the public v1 receipt, entry, graph, message and acknowledgement identity fields. Use the existing transcript graph OS fence as the freshness transaction precondition; do not infer ordering from opaque incarnation IDs or append sequences and do not add a new public token. The writer-only transcript index remains authoritative for the current source key, message ID, incarnation and sequence; the disposable publisher SQLite table retains the accepted mapping. Both already persist across process restart. A mapping is publishable only after its source key and immutable identity are verified from that index while the graph fence remains held through the publisher SQLite commit. A missing source, pending move/rewrite/append or unverifiable owner leaves the mapping unchanged or delivery pending for bounded replay.

## API contracts

Keep progress/transcript routes and read budgets unchanged. Reject malformed detail offsets inside a UTF-8 character with typed 400 invalid_request; successful incomplete reads must advance. Every acknowledgement writer must enforce the same stale-update rule.


## Logic flow

After a committed receipt is appended/deduplicated, each mapping writer acquires the existing publisher process lock and SQLite write transaction, then the stable graph fence. Under that fence it reads the current source-key acknowledgement, rejects receipt/entry/graph/message conflicts, inserts or refreshes only current routing, updates entry references where needed, and commits the publisher transaction before releasing the graph fence. The public wrapper must not rely on its pre-transaction lookup. The same protocol applies to first insertion, fast path and bounded drain. No path may hold the graph fence while acquiring the publisher lock or transaction; inspect room-move owner callbacks and all writer call sites for this order. Source lookup inside this critical section must avoid unbounded import/repair/publication; pending evidence defers mapping and retains replay eligibility. A delayed acknowledgement therefore observes current routing or remains pending; restart replays committed receipts using the existing source-key and SQLite state. Progress GET remains projection-only and recovery admission independent of transcript success.

## Task breakdown

1. `task_049_004_001` — Make publisher mapping atomic with authoritative transcript routing. Reuse the integrated candidate, close the check-to-commit window for fast path, drain and public wrapper, and cover deterministic delayed acknowledgement, first insertion, identity conflict, move/rewrite, restart and pending evidence.
2. `task_049_004_002` — Verify UTF-8 detail cursor refusal and positive continuation. Add loopback malformed-boundary and multibyte continuation regressions and final route/header/error/detail fixtures. This task has no dependency on Task 1.
3. `task_049_004_003` — Reconcile design, C4 navigation and integrated handoff after Tasks 1 and 2. Validate the final source contract, render and browser navigation; record exact revision, measured checks, fixtures, design review and parent/Feature 3 handoff.

## Risks & upward questions

Graph-fence release precedes publisher mapping, and incarnation IDs are opaque. Avoid lock inversion and a freshness-check/write race. Final API fixtures, producer design ownership and completed Task-record corrections remain explicit upstream gaps.

## Decision log

- `dec_001` · 2026-11-26 · Feature Lead · **Routing freshness protocol**
  Chose Hold the transcript graph fence from authoritative source-key lookup through publisher SQLite commit for every mapping writer; use publisher transaction before graph fence in a consistent lock order.
  Rationale: The source index is durable and already fences rewrite, move and append. Keeping that fence through commit closes the cross-store check-to-write race without inventing ordering for opaque incarnations. Unverifiable source state stays pending for replay.
  Honors: REQ-WATCHDOG-PROGRESS-001; REQ-WARROOM-TRANSCRIPT-002/003/004; DEC-WARROOM-TRANSCRIPT-003; feat_049_004 acceptance 1–3.

## Closeout

Completed child work: `task_049_004_001` (Make publisher mapping atomic with authoritative transcript routing), `task_049_004_002` (Verify UTF-8 detail cursor refusal and positive continuation), `task_049_004_003` (Reconcile design, C4 navigation and integrated handoff).
