---
id: feat_044_003
title: Present actionable health coverage and retained recovery history
tier: feature
status: completed
parent: epic_044
children:
- task_044_003_001
- task_044_003_002
- task_044_003_003
- task_044_003_004
depends_on:
- feat_044_002
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: aab5dd4e76caa8dd770c619c64baa34600050dea
created: '2026-11-10'
updated: '2026-11-14'
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
approved_at: '2026-11-14T02:09:03.932907+00:00'
---
# Present actionable health coverage and retained recovery history

## Parent Epic

[epic_044](../../epics/2_active/epic_044_make_health_audit_actionable_while_retaining_recovery_histor.md) requires separate verified current incidents, incomplete verification coverage, and retained historical attempts. The supervisor publishes bounded evidence; the War Room reads it. Fresh authoritative checks at repair and admission boundaries remain mandatory. This feature owns criteria 5–7, 9 and integrated acceptance in 10–12.

## Scope

In: prominent current blockers with owner, failure/impact, verification time and next action; one coverage summary with expandable, grouped details; collapsed paginated/filterable history; distinct investigation follow-up states; bounded single-flight browser refresh; focused cross-boundary and live validation evidence.

Out: changing repair authority or scheduler, migrating or deleting raw recovery history, new frontend framework/service, claiming a request or reported fix is verified resolution. The existing Python and Node toolchain is sufficient.

## Data structures

- `AuditSummary` rows from schema 2 carry `source_ref {store,row_key,incident_history_ordinal?}`, `work_id`, `owner`, `authoritative_generation`, `failure_class`, `occurred_at`, `last_attempted_at`, `last_verified_at`, `verification_status`, `reason`, `fresh_until`, `next_attempt_at`, `detail_truncated` and bounded `provenance`. A source reference identifies a retained record; it is displayed as evidence, never constructed into an arbitrary URL/path.
- The status response has `snapshot {state,reason?,epoch?,observed_at?,fresh_until?}`, a first `current` page, `coverage` aggregates, `sections`, receipt/failure metadata and compatibility aliases. The UI uses schema-2 fields as its authority. `current.complete=false` or `next_cursor` means additional current rows exist and must be signaled.
- A compact follow-up view exposes bounded investigation case identity, work/owner, request/delivery/acknowledgement state, latest report outcome/finding/reference, update/check times, and next reassessment. It has independent `state`/`observed_at` metadata and an explicit incomplete/unavailable state. These are coordination facts; only current projection rows prove incidents or resolution.
- Browser state consists of the displayed snapshot epoch, current/coverage/history page cursors, applied history filters, disclosure state, and one in-flight request token per surface. A new epoch or filter invalidates older page responses.

## API contracts

- `GET /api/health/audit` reads a bounded current page and aggregate coverage from the published projection. It may include a bounded follow-up summary, but must not enumerate investigation cases, recovery ledgers, board/worktrees, Git or providers on the GET path. Missing, stale, corrupt or wrong-root evidence is `pending` with a reason. It does not schedule an audit, recovery or agent turn.
- `GET /api/health/audit/coverage` and `GET /api/health/audit/history` accept `cursor`, `limit` (default 50, max 100), exact `work_id`, `owner`, `status`, and UTC occurrence bounds `from`/`to`. A ready page returns `header` and `page {epoch,rows,next_cursor,complete,reason,read_bytes}`. A changed epoch returns a restart response; malformed filters return 400. The UI retains filters for each cursor and restarts from page one on 409.
- `POST /api/health/audit` remains the authenticated manual admission control. The UI displays `admitted` or `coalesced` as pending completion. No GET or page/disclosure operation calls POST.
- Consumer limits remain at most 1 MiB source bytes, 256 KiB serialized response and 100 rows per request. Source rows carry bounded snippets and stable references rather than loading oversized records in the browser. The producer retains at most 100 candidates and 60 seconds per pass, with at most two seconds per candidate. Tests enforce structural limits; a representative 10,000-attempt benchmark records measured GET p95 and work/byte counts.
- Routing resolves product and tracking identities from the configured roots. A follow-up summary is read from the appropriate published runtime location without treating a tracking-root case path as a product-root status endpoint.

## Logic flow

```mermaid
sequenceDiagram
  participant A as Audit/agent lanes
  participant P as Published evidence
  participant H as War Room GET
  participant U as Browser
  A->>P: Publish current, coverage, history and bounded follow-up
  U->>H: Poll current status (single flight)
  H->>P: Read bounded projection and follow-up
  P-->>H: Epoch, freshness, rows, aggregates
  H-->>U: Verified incidents + coverage/follow-up state
  U->>H: Open coverage/history; request filtered page
  H->>P: Read epoch-pinned page
  H-->>U: Rows + next_cursor or restart
  Note over U,H: Viewing never starts reassessment or repair
```

Current blockers appear before coverage and history. If there are zero verified current rows but current pagination or verification coverage is incomplete, the label is "No VERIFIED current incidents; coverage incomplete." Coverage shows one aggregate summary and loads grouped details only on disclosure. History stays collapsed until requested, renders occurrence and check times separately, and never equates historical error or reported_fixed with current failure or verified resolution.

## Task breakdown

| Task | Purpose | Depends on |
| --- | --- | --- |
| task_044_003_001 | Publish bounded read-only investigation follow-up summaries. | None |
| task_044_003_002 | Render verified blockers, coverage and follow-up states. | task_044_003_001 |
| task_044_003_003 | Add on-demand paginated history and single-flight refresh. | task_044_003_002 |
| task_044_003_004 | Prove integrated behavior and budgets; reconcile durable War Room design. | task_044_003_001, task_044_003_002, task_044_003_003 |

## Risks & upward questions

The existing status route exposes empty investigation aliases; the follow-up view must be published outside GET and treated as non-authoritative. Existing history filters use verification status rather than a raw attempt outcome, so labels must say exactly what is filtered. A future outcome-index contract would require a separate scoped decision. Current/coverage/history snapshots may change while a disclosure is open; epoch changes cause a clear restart. Normal approved deployment is required before the feature can claim live War Room validation. If unavailable at closeout, retain an explicit gap; do not mark historical records resolved.

## Decision log

- `dec_001` · 2026-11-14 · Feature Lead · **API contracts**
  Chose Use published schema-2 current/coverage/history projections and a bounded, independently timestamped follow-up summary; treat only fresh authoritative current rows as verified incidents or resolution..
  Rationale: The interim status route omits investigation findings, while case-file scanning on each browser poll would repeat the original cost. Keeping follow-up state separate prevents delivery, acknowledgement and reported_fixed from becoming false resolution evidence.
  Honors: epic_044 success criteria 1, 2, 4, 9; read-only GET and fresh-generation repair boundaries..

- `dec_002` · 2026-11-14 · Feature Lead · **Logic flow**
  Chose Load coverage and history details only when disclosed, paginate by epoch-bound cursors, and use one in-flight browser request per surface..
  Rationale: This preserves bounded responses and readable current blockers when old history is large, while preventing slow responses and repeated five-second polls from replacing newer evidence.
  Honors: epic_044 success criteria 5–7, 10–12; 50/100-row, 1 MiB/256 KiB budgets and accessible controls..

## Closeout

Completed child work: `task_044_003_001` (Publish bounded audit investigation follow-up summaries), `task_044_003_002` (Render verified blockers and grouped coverage in Health audit), `task_044_003_003` (Add paginated audit history and single-flight refresh), `task_044_003_004` (Verify integrated audit experience and reconcile War Room design).
